"""F08 — Workspace sandbox, git worktree manager, canonical path/symlink/hardlink guard, and lease manager."""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from .authority import AuthorityError, is_valid_git_sha
from .policy import (
    PolicyViolationError,
    assert_paths_within_ownership,
    is_prohibited_branch,
    normalize_rel_path,
    path_matches_prefix,
)

SENSITIVE_ENV_PREFIXES = (
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "ANTIGRAVITY_CSRF_TOKEN",
    "AWS_",
    "AZURE_",
    "GCP_",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "SECRET_",
    "PRIVATE_KEY",
    "COMPOSER_AUTH",
    "NPM_AUTH",
    "NUGET_AUTH",
)

SENSITIVE_ENV_SUBSTRINGS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CREDENTIAL",
    "API_KEY",
    "PRIVATE_KEY",
    "COMPOSER_AUTH",
    "NPM_AUTH",
    "NUGET_AUTH",
)

_PAT_ENV_RE = re.compile(r"(?:^|_)PAT(?:_|$)")


class LeaseConflictError(PolicyViolationError):
    """Raised when a path/module/behavior lease collides, expires, or fails compare-and-set."""


def parse_git_raw_z_diff(raw_stdout: str) -> tuple[list[str], list[tuple[str, str, str]]]:
    """
    Parse `git diff --no-renames --raw -z` output.
    Returns (paths, forbidden_mode_entries) where forbidden_mode_entries holds
    (path, old_mode, new_mode) for any symlink (120000) or gitlink/submodule (160000) mode.
    """
    if not raw_stdout:
        return [], []
    tokens = raw_stdout.split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()
    paths: list[str] = []
    forbidden_modes: list[tuple[str, str, str]] = []
    idx = 0
    while idx < len(tokens):
        meta = tokens[idx]
        if not meta.startswith(":"):
            raise AuthorityError(f"Unexpected git --raw -z metadata header: {meta!r}")
        fields = meta[1:].split(" ")
        if len(fields) < 5:
            raise AuthorityError(f"Malformed git --raw -z metadata header: {meta!r}")
        old_mode, new_mode, status = fields[0], fields[1], fields[4]
        status_code = status[0] if status else ""
        if status_code in ("R", "C"):
            if idx + 2 >= len(tokens):
                raise AuthorityError("Truncated rename/copy record in git --raw -z output.")
            entry_paths = [tokens[idx + 1], tokens[idx + 2]]
            idx += 3
        else:
            if idx + 1 >= len(tokens):
                raise AuthorityError("Truncated path record in git --raw -z output.")
            entry_paths = [tokens[idx + 1]]
            idx += 2
        for p in entry_paths:
            paths.append(p)
            if old_mode in ("120000", "160000") or new_mode in ("120000", "160000"):
                forbidden_modes.append((p, old_mode, new_mode))
    return paths, forbidden_modes


def sanitize_worker_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build a minimal subprocess environment stripping broker tokens, PATs, API/private keys, and auth secrets."""
    source = base_env if base_env is not None else dict(os.environ)
    clean: dict[str, str] = {}
    for k, v in source.items():
        upper = k.upper()
        if any(upper == pref or upper.startswith(pref) for pref in SENSITIVE_ENV_PREFIXES):
            continue
        if any(sub in upper for sub in SENSITIVE_ENV_SUBSTRINGS):
            continue
        if _PAT_ENV_RE.search(upper):
            continue
        clean[k] = v
    clean["GIT_TERMINAL_PROMPT"] = "0"
    return clean


def assert_canonical_path_inside_worktree(worktree_root: Path, target_path: Path) -> Path:
    """Reject symlink escapes, NTFS directory junctions, hardlinks, and path traversals outside worktree_root."""
    root_resolved = worktree_root.resolve()
    is_junction = getattr(os.path, "isjunction", None)

    # Check every ancestor from target down to worktree_root for symlinks (including broken/dangling) and junctions
    current = target_path
    while True:
        if current.is_symlink():
            raise PolicyViolationError(f"Symlink prohibited inside worker sandbox: {current}")
        if is_junction is not None and is_junction(current):
            raise PolicyViolationError(f"Directory junction prohibited inside worker sandbox: {current}")
        if current == worktree_root or current.parent == current:
            break
        current = current.parent

    resolved = target_path.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PolicyViolationError(f"Canonical path {resolved} escapes worktree root {root_resolved}") from exc

    if resolved.exists() and resolved.is_file():
        st = resolved.stat()
        if st.st_nlink > 1:
            raise PolicyViolationError(f"Hardlinked file (st_nlink={st.st_nlink}) prohibited in worker sandbox: {resolved}")

    return resolved


class LeaseManager:
    """SQLite WAL lease coordinator keyed on repo + path/module/behavior with TTL, heartbeat, and CAS."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leases (
                    lease_id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    target_kind TEXT NOT NULL,
                    target_value TEXT NOT NULL,
                    mission_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    expires_at_epoch REAL NOT NULL,
                    released INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            conn.execute("COMMIT;")
        finally:
            conn.close()

    def acquire_leases(
        self,
        packet: dict[str, Any],
        worker_id: str,
        *,
        ttl_seconds: float = 300.0,
        now_epoch: float | None = None,
    ) -> list[dict[str, Any]]:
        if ttl_seconds <= 0:
            raise LeaseConflictError(f"ttl_seconds must be positive, got {ttl_seconds}")
        now = now_epoch if now_epoch is not None else dt.datetime.now(dt.timezone.utc).timestamp()
        repo = packet["repo_name"]
        mid = packet["mission_id"]

        targets: list[tuple[str, str]] = []
        for p in packet.get("owned_paths", []):
            targets.append(("PATH", normalize_rel_path(p)))
        for m in packet.get("owned_modules", []):
            cleaned_m = str(m).strip().lower()
            if cleaned_m:
                targets.append(("MODULE", cleaned_m))
        for b in packet.get("owned_behaviors", []):
            cleaned_b = str(b).strip().lower()
            if cleaned_b:
                targets.append(("BEHAVIOR", cleaned_b))

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            active_rows = conn.execute(
                "SELECT * FROM leases WHERE repo_name = ? AND released = 0 AND expires_at_epoch > ?",
                (repo, now),
            ).fetchall()

            for kind, val in targets:
                for row in active_rows:
                    if row["mission_id"] == mid and row["worker_id"] == worker_id:
                        continue
                    if row["target_kind"] != kind:
                        continue
                    if kind == "PATH":
                        if path_matches_prefix(val, row["target_value"]) or path_matches_prefix(row["target_value"], val):
                            raise LeaseConflictError(
                                f"Lease collision on {repo} PATH {val!r} with active lease {row['target_value']!r} "
                                f"held by {row['mission_id']}/{row['worker_id']}"
                            )
                    elif val == row["target_value"]:
                        raise LeaseConflictError(
                            f"Lease collision on {repo} {kind} {val!r} held by {row['mission_id']}/{row['worker_id']}"
                        )

            acquired: list[dict[str, Any]] = []
            expires = now + ttl_seconds
            for kind, val in targets:
                lease_id = f"{repo}:{kind}:{val}"
                existing = conn.execute("SELECT * FROM leases WHERE lease_id = ?", (lease_id,)).fetchone()
                if existing is None:
                    version = 1
                    conn.execute(
                        """
                        INSERT INTO leases (lease_id, repo_name, target_kind, target_value, mission_id, worker_id, version, expires_at_epoch, released)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                        (lease_id, repo, kind, val, mid, worker_id, version, expires),
                    )
                else:
                    version = existing["version"] + 1
                    cur = conn.execute(
                        """
                        UPDATE leases
                        SET mission_id = ?, worker_id = ?, version = ?, expires_at_epoch = ?, released = 0
                        WHERE lease_id = ? AND version = ?
                        """,
                        (mid, worker_id, version, expires, lease_id, existing["version"]),
                    )
                    if cur.rowcount != 1:
                        raise LeaseConflictError(f"CAS lease conflict on {lease_id}")
                acquired.append({"lease_id": lease_id, "version": version, "expires_at_epoch": expires})

            conn.execute("COMMIT;")
            return acquired
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def heartbeat(
        self,
        lease_id: str,
        *,
        worker_id: str,
        expected_version: int,
        ttl_seconds: float = 300.0,
        now_epoch: float | None = None,
    ) -> dict[str, Any]:
        now = now_epoch if now_epoch is not None else dt.datetime.now(dt.timezone.utc).timestamp()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute("SELECT * FROM leases WHERE lease_id = ?", (lease_id,)).fetchone()
            if row is None or row["released"] == 1:
                raise LeaseConflictError(f"Cannot heartbeat inactive lease: {lease_id}")
            if row["worker_id"] != worker_id:
                raise LeaseConflictError(f"Lease {lease_id} is owned by {row['worker_id']}, not {worker_id}")
            if row["version"] != expected_version:
                raise LeaseConflictError(f"Lease CAS version mismatch on {lease_id}: expected {expected_version}, found {row['version']}")
            if row["expires_at_epoch"] <= now:
                raise LeaseConflictError(f"Lease {lease_id} has expired and requires explicit reconciliation.")

            new_version = expected_version + 1
            new_expires = now + ttl_seconds
            conn.execute(
                "UPDATE leases SET version = ?, expires_at_epoch = ? WHERE lease_id = ? AND version = ?",
                (new_version, new_expires, lease_id, expected_version),
            )
            conn.execute("COMMIT;")
            return {"lease_id": lease_id, "version": new_version, "expires_at_epoch": new_expires}
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def release_worker_leases(self, mission_id: str, worker_id: str) -> int:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.execute(
                "UPDATE leases SET released = 1, version = version + 1 WHERE mission_id = ? AND worker_id = ? AND released = 0",
                (mission_id, worker_id),
            )
            conn.execute("COMMIT;")
            return cur.rowcount
        finally:
            conn.close()


class WorktreeSandbox:
    """Manages isolated Git worktrees for parallel or sequential writers with LF preservation and ownership checks."""

    def __init__(self, source_repo: Path, sandbox_root: Path) -> None:
        self.source_repo = source_repo.resolve()
        self.sandbox_root = sandbox_root.resolve()
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    def create_worktree(self, branch_name: str, base_sha: str, worktree_name: str) -> Path:
        if not is_valid_git_sha(base_sha):
            raise AuthorityError(f"Invalid or all-zero base_sha forbidden in create_worktree: {base_sha!r}")
        if is_prohibited_branch(branch_name):
            raise PolicyViolationError(f"Worktree cannot be created on prohibited branch {branch_name!r}.")
        if (
            not isinstance(worktree_name, str)
            or not worktree_name.strip()
            or worktree_name in (".", "..")
            or any(sep in worktree_name for sep in ("/", "\\", ":", "\x00"))
        ):
            raise PolicyViolationError(f"worktree_name must be a single safe directory segment, got {worktree_name!r}")

        wt_path = (self.sandbox_root / worktree_name).resolve()
        try:
            wt_path.relative_to(self.sandbox_root)
        except ValueError as exc:
            raise PolicyViolationError(f"worktree_name {worktree_name!r} escapes sandbox_root {self.sandbox_root}") from exc
        if wt_path == self.sandbox_root:
            raise PolicyViolationError("worktree_name cannot resolve to sandbox_root itself.")

        if wt_path.exists():
            subprocess.run(["git", "worktree", "remove", "--force", str(wt_path)], cwd=self.source_repo, capture_output=True)
            if wt_path.exists():
                shutil.rmtree(wt_path, ignore_errors=True)

        p = subprocess.run(
            ["git", "worktree", "add", "-B", branch_name, str(wt_path), base_sha],
            cwd=self.source_repo,
            capture_output=True,
            text=True,
            env=sanitize_worker_env(),
        )
        if p.returncode != 0:
            raise AuthorityError(f"git worktree add failed: {p.stderr.strip()}")

        subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=wt_path, capture_output=True, check=False)
        return wt_path

    def inspect_and_validate_worktree(
        self,
        wt_path: Path,
        packet: dict[str, Any],
        *,
        base_sha: str,
    ) -> list[str]:
        """Inspect all tracked, staged, and untracked files in worktree; reject symlinks, gitlinks, junctions, hardlinks, nested .git, or out-of-scope edits."""
        if not is_valid_git_sha(base_sha):
            raise AuthorityError(f"Invalid or all-zero base_sha forbidden in inspect_and_validate_worktree: {base_sha!r}")

        for item in wt_path.rglob("*"):
            rel_parts = item.relative_to(wt_path).parts
            if rel_parts and rel_parts[0] == ".git":
                continue
            if any(part.lower() == ".git" for part in rel_parts):
                raise PolicyViolationError(f"Nested .git metadata prohibited inside worker sandbox: {item}")
            assert_canonical_path_inside_worktree(wt_path, item)

        diff_wt = subprocess.run(
            ["git", "-c", "core.quotepath=false", "diff", "--no-renames", "--raw", "-z", base_sha],
            cwd=wt_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if diff_wt.returncode != 0:
            raise AuthorityError(
                f"Failed to inspect working-tree git diff against base_sha={base_sha!r} in {wt_path}: {diff_wt.stderr.strip()}"
            )

        diff_cached = subprocess.run(
            ["git", "-c", "core.quotepath=false", "diff", "--cached", "--no-renames", "--raw", "-z", base_sha],
            cwd=wt_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if diff_cached.returncode != 0:
            raise AuthorityError(
                f"Failed to inspect staged git diff against base_sha={base_sha!r} in {wt_path}: {diff_cached.stderr.strip()}"
            )

        untracked_p = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=wt_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if untracked_p.returncode != 0:
            raise AuthorityError(
                f"Failed to inspect untracked files in {wt_path}: {untracked_p.stderr.strip()}"
            )

        wt_paths, wt_forbidden = parse_git_raw_z_diff(diff_wt.stdout)
        cached_paths, cached_forbidden = parse_git_raw_z_diff(diff_cached.stdout)
        forbidden_modes = wt_forbidden + cached_forbidden
        if forbidden_modes:
            raise PolicyViolationError(
                f"Forbidden symlink (120000) or gitlink (160000) entry detected in worktree diff: {forbidden_modes}"
            )

        untracked_entries = [entry for entry in untracked_p.stdout.split("\0") if entry]
        changed = sorted(set(wt_paths + cached_paths + untracked_entries))
        if changed:
            assert_paths_within_ownership(packet, changed)
        return changed

    def remove_worktree(self, wt_path: Path) -> None:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt_path)], cwd=self.source_repo, capture_output=True)
        if wt_path.exists():
            shutil.rmtree(wt_path, ignore_errors=True)
