"""F08 — Workspace sandbox, git worktree manager, canonical path/symlink/hardlink guard, and lease manager."""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from .authority import AuthorityError
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
)


class LeaseConflictError(PolicyViolationError):
    """Raised when a path/module/behavior lease collides, expires, or fails compare-and-set."""


def sanitize_worker_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build a minimal subprocess environment stripping broker tokens and secrets."""
    source = base_env if base_env is not None else dict(os.environ)
    clean: dict[str, str] = {}
    for k, v in source.items():
        upper = k.upper()
        if any(upper == pref or upper.startswith(pref) for pref in SENSITIVE_ENV_PREFIXES):
            continue
        if "TOKEN" in upper or "SECRET" in upper or "PASSWORD" in upper or "CREDENTIAL" in upper:
            continue
        clean[k] = v
    clean["GIT_TERMINAL_PROMPT"] = "0"
    return clean


def assert_canonical_path_inside_worktree(worktree_root: Path, target_path: Path) -> Path:
    """Reject symlink escapes, hardlink escapes, and relative path traversals outside worktree_root."""
    root_resolved = worktree_root.resolve()

    # Check every ancestor from target down to worktree_root for symlinks (including broken/dangling symlinks)
    current = target_path
    while True:
        if current.is_symlink():
            raise PolicyViolationError(f"Symlink prohibited inside worker sandbox: {current}")
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
        now = now_epoch if now_epoch is not None else dt.datetime.now(dt.timezone.utc).timestamp()
        repo = packet["repo_name"]
        mid = packet["mission_id"]

        targets: list[tuple[str, str]] = []
        for p in packet.get("owned_paths", []):
            targets.append(("PATH", normalize_rel_path(p)))
        for m in packet.get("owned_modules", []):
            targets.append(("MODULE", m.strip()))
        for b in packet.get("owned_behaviors", []):
            targets.append(("BEHAVIOR", b.strip()))

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
        """Inspect all tracked and untracked files in worktree; reject symlinks, hardlinks, or out-of-scope edits."""
        for item in wt_path.rglob("*"):
            if ".git" in item.parts:
                continue
            assert_canonical_path_inside_worktree(wt_path, item)

        diff_p = subprocess.run(
            ["git", "diff", "--name-only", base_sha],
            cwd=wt_path,
            capture_output=True,
            text=True,
            check=False,
        )
        untracked_p = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=wt_path,
            capture_output=True,
            text=True,
            check=False,
        )
        changed = sorted(
            {
                line.strip()
                for line in (diff_p.stdout.splitlines() + untracked_p.stdout.splitlines())
                if line.strip()
            }
        )
        if changed:
            assert_paths_within_ownership(packet, changed)
        return changed

    def remove_worktree(self, wt_path: Path) -> None:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt_path)], cwd=self.source_repo, capture_output=True)
        if wt_path.exists():
            shutil.rmtree(wt_path, ignore_errors=True)
