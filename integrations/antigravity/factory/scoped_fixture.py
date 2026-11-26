"""Actual bounded Git effects in a disposable test repository, never native authority.

No path, executable, replacement data or remote comes from mission ingress.
Only the fixed local operation is supported. No acceptance or delivery is claimed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

from .authority import AuthorityError
from .dispatch_preflight import FixtureDispatchAdapter, _PreInvocationBlocked
from .mission_contract import contract_digest, digest_json
from .ownership import LeaseManager, assert_canonical_path_inside_worktree, parse_git_raw_z_diff, sanitize_worker_env
from .policy import assert_paths_within_ownership, path_matches_prefix


class ScopedGitFixtureAdapter(FixtureDispatchAdapter):
    """Composition-only adapter for a single, private, disposable Git repository."""

    repo_id = 42
    repo_name = "fixture/repository"
    branch = "feat/read-contract"
    destination = "fixture-only"
    owned_file = "docs/owned.txt"

    def __init__(self, *, grants, trusted_verifiers):
        super().__init__(grants=grants, trusted_verifiers=trusted_verifiers,
                         observe=self._observe_git, handler=None)
        self._temporary = tempfile.TemporaryDirectory(prefix="forge-scoped-fixture-")
        self.root = Path(self._temporary.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self._git("init", "-q", "-b", self.branch)
        (self.repo / "docs").mkdir()
        (self.repo / "docs/contract.md").write_bytes(b"pinned acceptance source\n")
        (self.repo / self.owned_file).write_bytes(b"before\n")
        self._git("add", "--", "docs")
        self._git("-c", "user.name=Forge Fixture", "-c", "user.email=fixture@example.invalid",
                  "commit", "-qm", "Disposable fixture")
        self.base_sha = self._git("rev-parse", "HEAD")
        self.oracle_blob_sha = self._git("rev-parse", "HEAD:docs/contract.md")
        self.leases = LeaseManager(self.root / "leases.sqlite")

    def configure_fixture_grants(self, grants, trusted_verifiers):
        # Trusted test composition only; never called by dispatcher ingress.
        from copy import deepcopy
        self._grants = deepcopy(grants)
        self._trusted_verifiers = frozenset(trusted_verifiers)

    def close(self):
        self._temporary.cleanup()

    def _git(self, *args):
        env = {k: v for k, v in sanitize_worker_env().items() if not k.upper().startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
        try:
            result = subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull,
                                     "-c", "core.autocrlf=false", *args], cwd=self.repo,
                                    env=env, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            raise AuthorityError("Disposable Git capability unavailable.") from exc
        if result.returncode:
            raise AuthorityError("Disposable Git observation failed.")
        return result.stdout.strip()

    def _assert_clean_target(self, packet):
        if (self.repo.is_symlink() or self.repo.resolve().parent != self.root
                or Path(self._git("rev-parse", "--show-toplevel")).resolve() != self.repo
                or self._git("rev-parse", "HEAD") != self.base_sha
                or self._git("symbolic-ref", "--short", "HEAD") != self.branch
                or self._git("remote")
                or self._git("status", "--porcelain", "--untracked-files=all", "--ignored")):
            raise AuthorityError("Disposable fixture target drift or dirty worktree.")
        if (packet["repo_id"], packet["repo_name"], packet["base_sha"], packet["permitted_branch"],
                packet["delivery_destination"]) != (self.repo_id, self.repo_name, self.base_sha, self.branch, self.destination):
            raise AuthorityError("Disposable fixture target mismatch.")
        if packet["cognition"]["mode"] == "INHERITED":
            raise AuthorityError("Inherited cognition not qualified in disposable fixture.")
        if "WRITE_OWNED" in packet["allowed_operations"]:
            assert_paths_within_ownership(packet, [self.owned_file])
            if packet["owned_paths"] != [self.owned_file]:
                raise AuthorityError("Only the fixed fixture file may be owned.")
        target = assert_canonical_path_inside_worktree(self.repo, self.repo / self.owned_file)
        if not target.is_file() or target.is_symlink() or target.stat().st_nlink != 1:
            raise AuthorityError("Fixture target must be a regular unlinked file.")
        if target.read_bytes() != b"before\n":
            raise AuthorityError("Fixture baseline bytes changed.")

    def _observe_git(self, packet):
        self._assert_clean_target(packet)
        grant = self.resolve_grant(packet, contract_digest(packet), dt.datetime.now(dt.timezone.utc))
        if not grant:
            raise AuthorityError("Fixture grant unavailable.")
        sources = {}
        for source in packet["source_authorities"]:
            if (source["repository_id"], source["repository_name"], source["commit_sha"]) != (
                    self.repo_id, self.repo_name, self.base_sha):
                raise AuthorityError("Source is outside disposable fixture.")
            if any(not path_matches_prefix(path, "docs") for path in source["scope"]):
                raise AuthorityError("Source scope exceeds fixture.")
            for path in source["scope"]:
                self._git("cat-file", "-t", self.base_sha + ":" + path)
            sources[source["source_id"]] = {"repository_id": self.repo_id, "repository_name": self.repo_name,
                                            "commit_sha": self._git("rev-parse", "HEAD")}
        oracles = {}
        for oracle in packet["oracles"]:
            if oracle["path"] != "docs/contract.md" or oracle["fixture_sha256"] is not None:
                raise AuthorityError("Only the pinned source oracle is supported.")
            oracles[oracle["oracle_id"]] = {"source_id": oracle["source_id"], "path": "docs/contract.md",
                "blob_sha": self._git("rev-parse", self.base_sha + ":docs/contract.md"), "fixture_sha256": None}
        target = {"repo_id": self.repo_id, "repo_name": self.repo_name, "base_sha": self.base_sha,
                  "permitted_branch": self.branch, "delivery_destination": self.destination}
        probe = digest_json({"target": target, "sources": sources, "oracles": oracles})
        now = dt.datetime.now(dt.timezone.utc)
        caps = {}
        for cap in packet["required_capabilities"]:
            operation = cap["operation"]
            if (operation not in {"READ", "WRITE_OWNED"} or cap["environment"] != "fixture"
                    or cap["independence_required"]):
                continue
            scope = ["docs"] if operation == "READ" else [self.owned_file]
            cid = cap["capability_id"]
            caps[cid] = {"contract_sha256": contract_digest(packet), "revision": packet["revision"],
                         "mission_id": packet["mission_id"], "worker_id": grant["worker_id"],
                         "actor_id": grant["actor_id"], "host_id": grant["host_id"], "capability_id": cid,
                         "environment": "fixture", "operation": operation, "scope": scope,
                         "status": "AVAILABLE", "independent": False, "probe_ref": "disposable-git-observation",
                         "probe_sha256": probe, "observed_at_utc": now.isoformat(),
                         "valid_until_utc": (now + dt.timedelta(seconds=30)).isoformat()}
        return {"target": target, "sources": sources, "oracles": oracles, "capabilities": caps}

    def verify_result(self, packet, result):
        """Re-observe the fixed effect before durable completion; no claimed diff is sufficient."""
        if result.get("acceptance") != "NOT_EVALUATED":
            raise AuthorityError("Fixture cannot supply acceptance.")
        if "WRITE_OWNED" not in packet["allowed_operations"]:
            self._assert_clean_target(packet)
            if result.get("effect") != "READ_ONLY" or result.get("observed", {}).get("target", {}).get("base_sha") != self.base_sha:
                raise AuthorityError("Read receipt does not bind actual fixture.")
            return
        if (self.repo.is_symlink() or Path(self._git("rev-parse", "--show-toplevel")).resolve() != self.repo
                or self._git("rev-parse", "HEAD") != self.base_sha
                or self._git("symbolic-ref", "--short", "HEAD") != self.branch
                or self._git("remote")):
            raise AuthorityError("Fixture identity changed before completion.")
        target = assert_canonical_path_inside_worktree(self.repo, self.repo / self.owned_file)
        raw = self._git("diff", "--raw", "-z", "--no-renames", self.base_sha)
        changed, forbidden = parse_git_raw_z_diff(raw)
        others = self._git("ls-files", "--others", "-z")
        if (forbidden or others or changed != [self.owned_file] or target.read_bytes() != b"after\n"
                or result != {"effect": "LOCAL_FIXTURE_WRITE_OBSERVED", "changed_paths": changed,
                    "base_sha": self.base_sha, "oracle_blob_sha": self.oracle_blob_sha,
                    "before_sha256": hashlib.sha256(b"before\n").hexdigest(),
                    "after_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "acceptance": "NOT_EVALUATED"}):
            raise AuthorityError("Fixture result does not match observed effects.")

    def invoke(self, packet, *, before_invoke):
        # Re-observe the actual source and target, not a caller observation.
        try:
            observation = self._observe_git(packet)
            grant = self.resolve_grant(packet, contract_digest(packet), dt.datetime.now(dt.timezone.utc))
            if not grant:
                raise AuthorityError("Fixture grant expired.")
            if "WRITE_OWNED" not in packet["allowed_operations"]:
                before_invoke()
                return {"effect": "READ_ONLY", "observed": observation, "acceptance": "NOT_EVALUATED"}
            worker = grant["worker_id"]
            acquired = self.leases.acquire_leases(packet, worker, ttl_seconds=30)
        except (AuthorityError, OSError, subprocess.SubprocessError) as exc:
            raise _PreInvocationBlocked("FIXTURE_PREREQUISITE_CHANGED") from exc
        entered = False
        try:
            with self.leases.hold_owned_paths(packet, worker, acquired, [self.owned_file]):
                self._assert_clean_target(packet)
                target = self.repo / self.owned_file
                before_invoke()
                entered = True
                target.write_bytes(b"after\n")
                raw = self._git("diff", "--raw", "-z", "--no-renames", self.base_sha)
                changed, forbidden = parse_git_raw_z_diff(raw)
                if changed != [self.owned_file] or forbidden or target.read_bytes() != b"after\n":
                    raise AuthorityError("Observed fixture effects exceed bounded operation.")
                result = {"effect": "LOCAL_FIXTURE_WRITE_OBSERVED", "changed_paths": changed,
                          "base_sha": self.base_sha, "oracle_blob_sha": self.oracle_blob_sha,
                          "before_sha256": hashlib.sha256(b"before\n").hexdigest(),
                          "after_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                          "acceptance": "NOT_EVALUATED"}
            self.leases.release_worker_leases(packet["mission_id"], worker)
            return result
        except (AuthorityError, OSError, subprocess.SubprocessError) as exc:
            if not entered:
                self.leases.release_worker_leases(packet["mission_id"], worker)
                raise _PreInvocationBlocked("FIXTURE_OWNERSHIP_OR_TARGET_CHANGED") from exc
            # Keep the uncertain attempt and lease for explicit operator reconciliation.
            raise
