"""Concrete, locally fenced Git command adapter for disposable targets.

The trusted composition supplies the issuer key, signed grant file and repository;
the mission supplies no executable, ref destination, credential or transport.
Not a live GitHub or native model adapter. No product acceptance is inferred.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
from contextlib import contextmanager

from .authority import AuthorityError
from .command_registry import propose_command
from .dispatch_preflight import ContractJournal, FixtureDispatchAdapter
from .execution_routing import select_execution_route
from .git_candidate import observe_git_candidate
from .mission_contract import canonical_json, contract_digest, digest_json
from .ownership import sanitize_worker_env


def grant_mac(key, grant):
    return hmac.new(key, canonical_json(grant).encode("utf-8"), hashlib.sha256).hexdigest()


class LocalGitCommandAdapter(FixtureDispatchAdapter):
    """Single concrete DIRECT route. Local ref and receipt ref change atomically."""

    def __init__(self, *, repository, grant_file, issuer_key, trusted_verifiers):
        if type(issuer_key) is not bytes or len(issuer_key) < 32:
            raise AuthorityError("LOCAL_ISSUER_KEY_REQUIRED")
        self.repo = Path(repository).resolve(strict=True)
        self.grant_file = Path(grant_file).resolve(strict=True)
        self.key = issuer_key
        self.verifiers = frozenset(trusted_verifiers)
        st = self.repo.stat()
        self.identity = {"path": str(self.repo), "device": st.st_dev, "inode": st.st_ino}
        self._check_repo()

    def _git(self, *args, data=None):
        env = {k: v for k, v in sanitize_worker_env().items()
               if not k.upper().startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT="0")
        return subprocess.run(["git", "--no-replace-objects", *args], cwd=self.repo,
                              env=env, input=data, capture_output=True, check=True,
                              timeout=20).stdout

    def _check_repo(self):
        st = self.repo.stat()
        if (self.repo.is_symlink() or
                (st.st_dev, st.st_ino) != (self.identity["device"], self.identity["inode"]) or
                self._git("rev-parse", "--is-bare-repository").strip() != b"true" or
                self._git("remote").strip()):
            raise AuthorityError("LOCAL_DISPOSABLE_REPOSITORY_REQUIRED")
        # No hooks are installed or bypassed. A configured external hooks path is
        # outside this bounded adapter's capability.
        if any(p.name not in {"."} and not p.name.endswith(".sample")
               for p in (self.repo / "hooks").iterdir()):
            raise AuthorityError("LOCAL_REPOSITORY_HOOKS_UNQUALIFIED")
        result = self._git("config", "--local", "--list").decode("utf-8").lower()
        if any(line.startswith(("core.hookspath=", "include.", "includeif.", "remote."))
               for line in result.splitlines()):
            raise AuthorityError("LOCAL_REPOSITORY_CONFIGURATION_UNQUALIFIED")

    def resolve_grant(self, packet, digest, now):
        try:
            envelope = json.loads(self.grant_file.read_bytes())
            grant = envelope["grant"]
            if (set(envelope) != {"grant", "mac"} or type(grant) is not dict or
                    not hmac.compare_digest(grant_mac(self.key, grant), envelope["mac"])):
                return None
            verifier = FixtureDispatchAdapter(grants={digest: grant},
                trusted_verifiers=self.verifiers, observe=None, handler=None)
            resolved = verifier.resolve_grant(packet, digest, now)
            if not resolved:
                return None
            scope = grant["local_command"]
            required = {"version": 1, "resource": self.identity, "repo_id": packet["repo_id"],
                        "repo_name": packet["repo_name"], "branch": packet["permitted_branch"],
                        "base": packet["base_sha"], "run_id": packet["run_id"],
                        "contract_sha256": digest, "stage": "AUTHORIZED"}
            if any(scope.get(k) != v for k, v in required.items()):
                return None
            if set(scope) != set(required) | {"alias", "candidate", "tree", "paths"}:
                return None
            if scope["alias"] != "/forge.write" or not re.fullmatch(
                    r"[A-Za-z0-9_-]+(?:[./][A-Za-z0-9_-]+)*", scope["branch"]):
                return None
            if packet["cognition"]["mode"] != "OMITTED" or packet["authority"]["brain_required"]:
                return None
            if (set(packet["allowed_operations"]) != {"READ", "WRITE_OWNED"} or
                    type(scope["paths"]) is not list or
                    not all(type(p) is str for p in scope["paths"]) or
                    len(set(scope["paths"])) != len(scope["paths"]) or
                    set(scope["paths"]) != set(packet["owned_paths"])):
                return None
            return resolved
        except (OSError, ValueError, KeyError, TypeError, AttributeError, AuthorityError):
            return None

    def _grant(self, packet):
        grant = self.resolve_grant(packet, contract_digest(packet), dt.datetime.now(dt.timezone.utc))
        if not grant:
            raise AuthorityError("LOCAL_COMMAND_GRANT_UNRESOLVED")
        return grant

    def binding(self, packet):
        scope = self._grant(packet)["local_command"]
        return {"kind": "LOCAL_GIT_CAS", "resource": self.identity,
                "repo_id": scope["repo_id"], "repo_name": scope["repo_name"],
                "branch": scope["branch"], "base": scope["base"],
                "candidate": scope["candidate"], "tree": scope["tree"],
                "paths": scope["paths"], "alias": scope["alias"]}

    def command(self, packet, stage):
        grant = self._grant(packet)
        scope = grant["local_command"]
        proposal = propose_command(scope["alias"], observed_role=grant["formal_role"],
                                   observed_stage=stage)
        if (scope["stage"] != stage or proposal["status"] != "PROPOSED" or
                proposal["effect"] != "SOURCE_WRITE" or proposal["next_stage"] != "ACTIVE"):
            raise AuthorityError("LOCAL_COMMAND_TRANSITION_DENIED")
        return proposal

    def _ref(self, scope):
        return "refs/heads/" + scope["branch"]

    def _pending_ref(self, scope):
        return "refs/forge/pending/" + hashlib.sha256(scope["branch"].encode()).hexdigest()

    def _receipt_ref(self, scope):
        # Logical resource+base, not mission/nonce/candidate, and in the same
        # Git ref transaction as the effect. Different journals cannot repeat it.
        return "refs/forge/effects/" + digest_json({
            "branch": scope["branch"], "base": scope["base"]})

    def _candidate(self, packet, scope):
        self._check_repo()
        return observe_git_candidate(self.repo, packet, scope["base"], scope["candidate"],
                                     scope["tree"], scope["paths"])

    def observe(self, packet):
        grant = self._grant(packet)
        scope = grant["local_command"]
        self._candidate(packet, scope)
        if self._git("for-each-ref", "--format=%(refname)", self._pending_ref(scope)).strip():
            raise AuthorityError("RESOURCE_EFFECT_UNRECONCILED")
        if self._git("rev-parse", "--verify", self._ref(scope)).decode().strip() != scope["base"]:
            raise AuthorityError("LOCAL_REF_DRIFT")
        sources = {}
        for source in packet["source_authorities"]:
            if (source["repository_id"], source["repository_name"], source["commit_sha"]) != (
                    packet["repo_id"], packet["repo_name"], packet["base_sha"]):
                raise AuthorityError("LOCAL_SOURCE_UNAVAILABLE")
            for path in source["scope"]:
                self._git("cat-file", "-t", source["commit_sha"] + ":" + path)
            sources[source["source_id"]] = {k: source[k] for k in
                ("repository_id", "repository_name", "commit_sha")}
        # Read every selected skill from an exact local source; no claim of
        # model-context consumption or independent profile eligibility.
        skills = packet["selected_skills"]
        skill_reads = {}
        for path in skills["files"]:
            raw = self._git("cat-file", "blob", skills["skill_source_sha"] + ":" + path)
            skill_reads[path] = hashlib.sha256(raw).hexdigest()
        oracles = {}
        for oracle in packet["oracles"]:
            source = sources[oracle["source_id"]]
            blob = self._git("rev-parse", source["commit_sha"] + ":" + oracle["path"]).decode().strip()
            raw = self._git("cat-file", "blob", blob)
            if blob != oracle["blob_sha"] or oracle["fixture_sha256"] is not None:
                raise AuthorityError("LOCAL_ORACLE_SOURCE_DRIFT")
            oracles[oracle["oracle_id"]] = {**{k: oracle[k] for k in
                ("source_id", "path", "blob_sha", "fixture_sha256")},
                "observed_sha256": hashlib.sha256(raw).hexdigest()}
        target = {k: packet[k] for k in ("repo_id", "repo_name", "base_sha",
                                       "permitted_branch", "delivery_destination")}
        if target["delivery_destination"] != "fixture-only":
            raise AuthorityError("LOCAL_DISPOSABLE_DESTINATION_REQUIRED")
        probe = digest_json({"target": target, "oracles": oracles,
                             "sources": sources, "skills": skill_reads, "scope": scope})
        now = dt.datetime.now(dt.timezone.utc)
        caps = {}
        for cap in packet["required_capabilities"]:
            if cap["environment"] != "fixture" or cap["independence_required"]:
                continue
            if cap["operation"] == "READ":
                paths = sorted({p for s in packet["source_authorities"] for p in s["scope"]})
            elif cap["operation"] == "WRITE_OWNED":
                paths = scope["paths"]
            else:
                continue
            cid = cap["capability_id"]
            caps[cid] = {"contract_sha256": contract_digest(packet), "revision": packet["revision"],
                "mission_id": packet["mission_id"], "worker_id": grant["worker_id"],
                "actor_id": grant["actor_id"], "host_id": grant["host_id"], "capability_id": cid,
                "environment": "fixture", "operation": cap["operation"], "scope": paths,
                "status": "AVAILABLE", "independent": False, "probe_ref": "local-git-object-observation",
                "probe_sha256": probe, "observed_at_utc": now.isoformat(),
                "valid_until_utc": min(now + dt.timedelta(seconds=30),
                                      dt.datetime.fromisoformat(grant["valid_until_utc"])).isoformat()}
        route = select_execution_route(risk_class=packet["risk_class"], task_kind="DETERMINISTIC",
            private_material=False, previous_effect_unknown=False,
            observations={"DIRECT": {"observed": True, "authorized": True,
                "scope_match": True, "data_boundary_match": True}})
        if route.get("route") != "DIRECT":
            raise AuthorityError("LOCAL_ROUTE_NOT_ELIGIBLE")
        return {"target": target, "sources": sources, "oracles": oracles,
                "capabilities": caps, "skill_reads": skill_reads, "route": "DIRECT"}

    @contextmanager
    def lock(self):
        # Host-exclusive disposable root, POSIX only. The same lock covers
        # invocation and recovery; Git's ref transaction is the actual CAS.
        import fcntl
        self._check_repo()
        fd = os.open(self.repo / "forge-effect.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _receipt(self, packet, reservation, grant):
        return {"format": "forge-local-git-effect/v1", "reservation_id": reservation,
                "contract_sha256": contract_digest(packet), "run_id": packet["run_id"],
                "actor_id": grant["actor_id"], "grant_sha256": digest_json(grant),
                "binding": self.binding(packet), "route": "DIRECT",
                "effect": "LOCAL_GIT_REF_CAS", "acceptance": "NOT_EVALUATED"}

    def invoke(self, packet, *, before_invoke, reservation_id, journal):
        if type(journal) is not ContractJournal:
            raise AuthorityError("CANONICAL_RESERVATION_REQUIRED")
        with self.lock():
            journal.authorize_local_invocation(packet, reservation_id, self)
            self.observe(packet)
            grant = self._grant(packet)
            scope = grant["local_command"]
            receipt = self._receipt(packet, reservation_id, grant)
            raw = canonical_json({"receipt": receipt, "mac": grant_mac(self.key, receipt)}).encode()
            # Only the canonical journal can open the invocation boundary.
            journal.authorize_local_invocation(packet, reservation_id, self)
            before_invoke()
            blob = self._git("hash-object", "-w", "--stdin", data=raw).decode().strip()
            journal.authorize_local_invocation(packet, reservation_id, self)
            # The branch-wide durable claim is shared across journal processes.
            # It remains until canonical completion or positive reconciliation.
            self._git("update-ref", "--stdin", data=("start\nverify "+self._ref(scope)+" "+scope["base"]+
                      "\ncreate "+self._pending_ref(scope)+" "+blob+"\nprepare\ncommit\n").encode("ascii"))
            journal.authorize_local_invocation(packet, reservation_id, self)
            transaction = ("start\nverify "+self._pending_ref(scope)+" "+blob+"\nupdate " + self._ref(scope) + " " + scope["candidate"] +
                           " " + scope["base"] + "\ncreate " + self._receipt_ref(scope) +
                           " " + blob + "\nprepare\ncommit\n").encode("ascii")
            self._git("update-ref", "--stdin", data=transaction)
            return {"receipt": receipt, "receipt_blob": blob}

    def verify_result(self, packet, result, reservation_id):
        grant = self._grant(packet)
        scope = grant["local_command"]
        self._candidate(packet, scope)
        expected = self._receipt(packet, reservation_id, grant)
        blob = self._git("rev-parse", "--verify", self._receipt_ref(scope)).decode().strip()
        raw = self._git("cat-file", "blob", blob)
        if (raw != canonical_json({"receipt": expected, "mac": grant_mac(self.key, expected)}).encode() or
                result != {"receipt": expected, "receipt_blob": blob}):
            raise AuthorityError("LOCAL_EFFECT_RECEIPT_MISMATCH")
        if self._git("rev-parse", "--verify", self._ref(scope)).decode().strip() != scope["candidate"]:
            raise AuthorityError("LOCAL_EFFECT_HEAD_DRIFT")

    def release_completed_claim(self, packet, reservation_id, result, journal):
        # Do not clear the resource fence on a receipt alone: canonical
        # completion/reconciliation must already be durable.
        with self.lock():
            if type(journal) is not ContractJournal:
                raise AuthorityError("CANONICAL_RESERVATION_REQUIRED")
            attempt=journal.inspect_attempt(canonical_json(packet),reservation_id)
            if attempt["status"] not in {"COMPLETED","RECONCILED"} or attempt["result"]!=result:
                raise AuthorityError("CANONICAL_COMPLETION_REQUIRED")
            self.verify_result(packet, result, reservation_id)
            scope = self._grant(packet)["local_command"]
            pending = self._pending_ref(scope)
            if self._git("for-each-ref", "--format=%(refname)", pending).strip():
                self._git("update-ref", "-d", pending, result["receipt_blob"])

    def recover_result(self, packet, reservation_id):
        # Positive receipt only. Head equality alone never establishes provenance;
        # missing receipt or changed grant stays UNKNOWN (no automatic retry).
        grant = self._grant(packet)
        scope = grant["local_command"]
        receipt = self._receipt(packet, reservation_id, grant)
        blob = self._git("rev-parse", "--verify", self._receipt_ref(scope)).decode().strip()
        result = {"receipt": receipt, "receipt_blob": blob}
        self.verify_result(packet, result, reservation_id)
        return result
