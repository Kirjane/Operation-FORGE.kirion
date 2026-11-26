"""Durable, fixture-only preflight on the FactoryJournal event-chain foundation.

No live adapter is shipped. A fixture adapter is trusted test composition, not a
sandbox for arbitrary Python code, and is never constructed from a mission packet.
Keep the old journal frozen under operator custody; no implicit live migration.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import uuid
from contextlib import closing, contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from .authority import AuthorityError
from .mission_contract import canonical_json, contract_digest, digest_json, parse_mission_packet, revision_changes
from .policy import normalize_rel_path, path_matches_prefix
from .scheduler import (FactoryJournal, SchedulerError, GENESIS_EVENT_HASH, _compute_event_chain_hash,
                        enforce_wave_budget, storage_catalog)
import hashlib


def _timestamp(value: Any) -> dt.datetime:
    if not isinstance(value, str):
        raise AuthorityError("Missing UTC timestamp")
    try:
        observed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if observed.utcoffset() != dt.timedelta(0):
            raise ValueError("UTC required")
        return observed
    except ValueError as exc:
        raise AuthorityError("Invalid UTC timestamp") from exc


def _fresh(record: dict[str, Any], now: dt.datetime) -> bool:
    try:
        return _timestamp(record["observed_at_utc"]) <= now < _timestamp(record["valid_until_utc"])
    except (KeyError, AuthorityError, TypeError):
        return False


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


class _PreInvocationBlocked(SchedulerError):
    """An explicit freshness or binding denial before the fixture callback."""


_CONTRACT_STORAGE_CATALOG = {
    "contract_heads": "table", "contract_revisions": "table",
    "contract_attempts": "table", "contract_blockers": "table",
    "contract_observations": "table", "journal_events": "table",
    "missions": "view", "dispatches": "view",
}


def _require_contract_storage(conn: sqlite3.Connection) -> None:
    objects = storage_catalog(conn)
    if objects and objects != _CONTRACT_STORAGE_CATALOG:
        raise SchedulerError("Not an isolated contract journal; no automatic migration.")


class FixtureDispatchAdapter:
    """Explicitly non-live fixture authority, observations and test handler.

    Grants are configured independently of packet ingress. No caller packet field,
    name, digest, role or boolean can create a grant. Never expose this adapter
    through a host, CLI or native workflow; injected Python callbacks are test code.
    """

    def __init__(self, *, grants: dict[str, dict[str, Any]], trusted_verifiers: set[str],
                 observe: Callable[[dict[str, Any]], dict[str, Any]],
                 handler: Callable[[dict[str, Any]], dict[str, Any]],
                 reconciliations: dict[str, dict[str, Any]] | None = None):
        self._grants = deepcopy(grants)
        self._trusted_verifiers = frozenset(trusted_verifiers)
        self._observe = observe
        self._handler = handler
        self._reconciliations = deepcopy(reconciliations or {})

    def resolve_grant(self, packet: dict[str, Any], digest: str, now: dt.datetime) -> dict[str, Any] | None:
        grant = deepcopy(self._grants.get(digest))
        if not isinstance(grant, dict) or packet["verifier"] not in self._trusted_verifiers:
            return None
        expected = {key: packet["authority"][key] for key in
                    ("issuer_actor_id", "issuer_role", "directive_ref", "directive_sha256")}
        expected.update(contract_sha256=digest, revision=packet["revision"], verifier=packet["verifier"],
                        persona=packet["assigned_persona"], formal_role=packet["formal_role"])
        if any(type(grant.get(key)) is not type(value) or grant.get(key) != value
               for key, value in expected.items()):
            return None
        if grant.get("revoked") is not False or not _fresh(grant, now):
            return None
        if not all(_nonempty(grant.get(key)) for key in ("worker_id", "actor_id", "host_id")):
            return None
        ordinal = grant.get("attempt_ordinal")
        if type(ordinal) is not int or ordinal < 1:
            return None
        return grant

    def observe(self, packet: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(self._observe(deepcopy(packet)))

    def invoke(self, packet: dict[str, Any], *, before_invoke: Callable[[], None]) -> dict[str, Any]:
        # Copy before the last validity check, not after it. No repository,
        # worktree, native agent or remote executor is passed.
        invocation_packet = deepcopy(packet)
        before_invoke()
        return self._handler(invocation_packet)

    def reconciliation(self, reservation_id: str) -> dict[str, Any] | None:
        return deepcopy(self._reconciliations.get(reservation_id))


def is_supported_fixture_adapter(adapter):
    from .scoped_fixture import ScopedGitFixtureAdapter
    return type(adapter) in (FixtureDispatchAdapter, ScopedGitFixtureAdapter)


def fixture_operations(adapter):
    from .scoped_fixture import ScopedGitFixtureAdapter
    return {"READ", "WRITE_OWNED"} if type(adapter) is ScopedGitFixtureAdapter else {"READ", "REVIEW_READONLY"}


class ContractJournal(FactoryJournal):
    """Existing hash-chain journal with isolated contract storage and a legacy-write fence.

    The legacy tables are read-only empty views. Old public registration, lifecycle
    and dispatch writes cannot address the new contract tables. Old recovery sees no
    mission. A separate historical backup is explicit, never imported as live state.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Inspect an existing file before any WAL pragma or migration.
        if self.db_path.exists():
            with closing(sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
                _require_contract_storage(conn)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = super()._connect()
        conn.execute("PRAGMA synchronous=FULL;")
        return conn

    @contextmanager
    def _transaction(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        # No write pragma before the transactional compatibility check. A
        # concurrent guarded legacy initializer either wins on empty storage or
        # sees the committed contract catalog and is denied. Older unpatched
        # brokers still need operational path segregation and access custody.
        with closing(sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            _require_contract_storage(conn)
            statements = (
                """CREATE TABLE IF NOT EXISTS contract_heads (
                    mission_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    digest TEXT NOT NULL, state TEXT NOT NULL, state_version INTEGER NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS contract_revisions (
                    mission_id TEXT NOT NULL, revision INTEGER NOT NULL, digest TEXT NOT NULL,
                    packet_json TEXT NOT NULL, PRIMARY KEY(mission_id,revision), UNIQUE(digest))""",
                """CREATE TABLE IF NOT EXISTS contract_attempts (
                    mission_id TEXT NOT NULL, revision INTEGER NOT NULL, ordinal INTEGER NOT NULL,
                    digest TEXT NOT NULL, reservation_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL,
                    worker_id TEXT NOT NULL, actor_id TEXT NOT NULL, run_id TEXT NOT NULL,
                    status TEXT NOT NULL, result_json TEXT, PRIMARY KEY(mission_id,revision,ordinal))""",
                """CREATE TABLE IF NOT EXISTS contract_blockers (
                    mission_id TEXT NOT NULL, digest TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    reason TEXT NOT NULL, PRIMARY KEY(mission_id,digest,fingerprint,reason))""",
                """CREATE TABLE IF NOT EXISTS contract_observations (
                    digest TEXT NOT NULL, capability_id TEXT NOT NULL, worker_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL, material_digest TEXT NOT NULL,
                    PRIMARY KEY(digest,capability_id,worker_id))""",
                """CREATE TABLE IF NOT EXISTS journal_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
                    mission_id TEXT NOT NULL, run_id TEXT NOT NULL, stage TEXT NOT NULL,
                    event_type TEXT NOT NULL, state_version INTEGER NOT NULL, payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL, prev_event_sha256 TEXT NOT NULL, created_at_utc TEXT NOT NULL)""",
                """CREATE VIEW IF NOT EXISTS missions AS SELECT '' AS mission_id WHERE 0""",
                """CREATE VIEW IF NOT EXISTS dispatches AS SELECT '' AS dispatch_key WHERE 0""",
            )
            for statement in statements:
                conn.execute(statement)

    def register_mission(self, packet):
        raise SchedulerError("Use raw contract preflight; legacy registration denied.")

    def transition_state(self, *args, **kwargs):
        raise SchedulerError("Direct lifecycle transitions denied in contract storage.")

    def record_idempotent_dispatch(self, *args, **kwargs):
        raise SchedulerError("Post-effect legacy dispatch recording denied.")

    def get_mission(self, mission_id: str) -> dict[str, Any]:
        with self._transaction() as conn:
            row = conn.execute("""SELECT h.*, r.packet_json FROM contract_heads h JOIN contract_revisions r
                ON h.mission_id=r.mission_id AND h.revision=r.revision WHERE h.mission_id=?""",
                (mission_id,)).fetchone()
            if row is None:
                raise SchedulerError("Contract mission not found.")
            return {**dict(row), "packet": json.loads(row["packet_json"])}

    def _event(self, conn, packet, digest, event_type, payload):
        head = conn.execute("SELECT state_version FROM contract_heads WHERE mission_id=?",
                            (packet["mission_id"],)).fetchone()
        self._append_event_in_tx(conn, mission_id=packet["mission_id"], run_id=packet["run_id"],
            stage="CONTRACT_PREFLIGHT", event_type=event_type,
            state_version=head["state_version"] if head else 1,
            payload={"contract_sha256": digest, "revision": packet["revision"], **payload})

    def _assert_chain(self, conn):
        previous = GENESIS_EVENT_HASH
        for row in conn.execute("SELECT * FROM journal_events ORDER BY seq"):
            if (row["prev_event_sha256"] != previous or
                hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest() != row["payload_sha256"]):
                raise SchedulerError("Contract journal hash-chain verification failed.")
            previous = _compute_event_chain_hash(row)

    def _blocked(self, conn, packet, digest, reason, material):
        fingerprint = digest_json({"contract": digest, "reason": reason, "prerequisites": material})
        row = conn.execute("INSERT OR IGNORE INTO contract_blockers VALUES (?,?,?,?)",
                           (packet["mission_id"], digest, fingerprint, reason))
        if row.rowcount:
            conn.execute("""UPDATE contract_heads SET state='BLOCKED',state_version=state_version+1
                WHERE mission_id=? AND digest=? AND state!='BLOCKED' AND NOT EXISTS (
                SELECT 1 FROM contract_attempts WHERE mission_id=? AND status IN ('RESERVED','RUNNING','UNKNOWN'))""",
                (packet["mission_id"], digest, packet["mission_id"]))
            self._event(conn, packet, digest, "DISPATCH_BLOCKED",
                        {"reason": reason, "prerequisite_fingerprint": fingerprint, "fixture_only": True})
        return {"status": "BLOCKED", "reason": reason, "prerequisite_fingerprint": fingerprint,
                "cached": row.rowcount == 0, "fixture_only": True}

    def _bind_revision(self, conn, packet, digest, grant):
        mid, revision = packet["mission_id"], packet["revision"]
        head = conn.execute("SELECT * FROM contract_heads WHERE mission_id=?", (mid,)).fetchone()
        if head and head["revision"] == revision:
            return None if head["digest"] == digest else "CONFLICTING_CONTRACT_REVISION"
        if head is None:
            if revision != 1:
                return "MISSING_PREDECESSOR"
            version = 1
        else:
            if revision != head["revision"] + 1 or packet["previous_contract_sha256"] != head["digest"]:
                return "STALE_OR_UNBOUND_REVISION"
            if conn.execute("""SELECT 1 FROM contract_attempts WHERE mission_id=?
                               AND status IN ('RESERVED','RUNNING','UNKNOWN')""", (mid,)).fetchone():
                return "PRIOR_EFFECT_UNRECONCILED"
            prior = json.loads(conn.execute("SELECT packet_json FROM contract_revisions WHERE digest=?",
                                           (head["digest"],)).fetchone()[0])
            if packet["authority"]["parent_grant_ref"] != prior["authorization_ref"]:
                return "UNBOUND_PARENT_GRANT"
            changes = revision_changes(prior, packet)
            if not changes <= set(prior["authority"]["permitted_revision_fields"]):
                return "UNAUTHORIZED_REVISION_FIELDS"
            if not set(prior["required_gates"]) <= set(packet["required_gates"]):
                return "REVISION_WEAKENS_REQUIRED_GATES"
            version = head["state_version"] + 1
        conn.execute("INSERT INTO contract_revisions VALUES (?,?,?,?)",
                     (mid, revision, digest, canonical_json(packet)))
        conn.execute("""INSERT INTO contract_heads VALUES (?,?,?,'AUTHORIZED',?)
                      ON CONFLICT(mission_id) DO UPDATE SET revision=excluded.revision,
                      digest=excluded.digest,state=excluded.state,state_version=excluded.state_version""",
                     (mid, revision, digest, version))
        self._event(conn, packet, digest, "CONTRACT_AUTHORIZED",
                    {"actor_id": grant["actor_id"], "issuer_actor_id": grant["issuer_actor_id"],
                     "directive_sha256": grant["directive_sha256"], "fixture_only": True})
        return None

    def _prerequisites(self, conn, packet, digest, grant, observed, now):
        """Return only relevant material facts; timestamps and unrelated observations are not identity."""
        failures, material, capability_expiries = [], {}, []
        if not isinstance(observed, dict):
            return ["INVALID_OBSERVATION"], {}, []
        target = {key: packet[key] for key in ("repo_id", "repo_name", "base_sha",
                                               "permitted_branch", "delivery_destination")}
        supplied_target = observed.get("target")
        material["target"] = ({key: supplied_target.get(key) for key in target}
                              if isinstance(supplied_target, dict) else None)
        if canonical_json(material["target"]) != canonical_json(target):
            failures.append("TARGET_MISMATCH")
        sources = {s["source_id"]: {key: s[key] for key in ("repository_id", "repository_name", "commit_sha")}
                   for s in packet["source_authorities"]}
        oracles = {o["oracle_id"]: {key: o[key] for key in ("source_id", "path", "blob_sha", "fixture_sha256")}
                   for o in packet["oracles"]}
        for key, expected in (("sources", sources), ("oracles", oracles)):
            supplied = observed.get(key)
            material[key] = ({name: {field: supplied[name].get(field) for field in fields}
                              if isinstance(supplied.get(name), dict) else None
                              for name, fields in expected.items()} if isinstance(supplied, dict) else None)
            if canonical_json(material[key]) != canonical_json(expected):
                failures.append(key.upper() + "_MISMATCH")
        if packet["cognition"]["mode"] == "INHERITED":
            material["cognition"] = observed.get("cognition")
            if canonical_json(material["cognition"]) != canonical_json(packet["cognition"]):
                failures.append("COGNITION_MISMATCH")
        # Acceptance-bound dependency satisfaction is deferred. A fixture caller
        # cannot assert that an upstream mission was accepted.
        if packet["depends_on"]:
            material["dependencies"] = sorted(packet["depends_on"])
            failures.append("DEPENDENCY_ACCEPTANCE_UNQUALIFIED")
        # A mismatched observation envelope must not advance capability
        # chronology, even when an individual capability appears well formed.
        context_matches = not failures
        capabilities = observed.get("capabilities")
        material["capabilities"] = {}
        for requirement in packet["required_capabilities"]:
            cid = requirement["capability_id"]
            cap = capabilities.get(cid) if isinstance(capabilities, dict) else None
            binding = {"contract_sha256": digest, "revision": packet["revision"],
                       "mission_id": packet["mission_id"], "worker_id": grant["worker_id"],
                       "actor_id": grant["actor_id"], "host_id": grant["host_id"],
                       "capability_id": cid, "environment": requirement["environment"],
                       "operation": requirement["operation"]}
            fact = {"binding": binding, "status": "MISSING"}
            if isinstance(cap, dict):
                fact["status"] = cap.get("status") if cap.get("status") in ("AVAILABLE", "UNAVAILABLE", "UNKNOWN") else "INVALID_STATUS"
                fact["observed_binding"] = {key: cap.get(key) for key in binding}
                fact["scope_covered"] = False
                fact["independent"] = cap.get("independent") is True if requirement["independence_required"] else None
                scope = cap.get("scope")
                if (canonical_json(fact["observed_binding"]) != canonical_json(binding)
                    or not isinstance(scope, list) or not all(isinstance(path, str) for path in scope)):
                    fact["status"] = "MISMATCH"
                else:
                    try:
                        normalized_scope = [normalize_rel_path(prefix) for prefix in scope]
                        fact["scope_covered"] = all(any(path_matches_prefix(path, prefix) for prefix in normalized_scope)
                                                    for path in requirement["scope"])
                        if not fact["scope_covered"]:
                            fact["status"] = "MISMATCH"
                    except AuthorityError:
                        fact["status"] = "MISMATCH"
                if requirement["independence_required"] and cap.get("independent") is not True:
                    fact["status"] = "MISMATCH"
                if not _nonempty(cap.get("probe_ref")) or not _nonempty(cap.get("probe_sha256")) or (
                        len(cap["probe_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in cap["probe_sha256"])
                        or cap["probe_sha256"] == "0" * 64):
                    fact["status"] = "MISMATCH"
                try:
                    at = _timestamp(cap["observed_at_utc"])
                    expiry = _timestamp(cap["valid_until_utc"])
                    chronology_valid = at <= now and at < expiry
                except (KeyError, AuthorityError, TypeError):
                    chronology_valid = False
                if not chronology_valid:
                    fact["status"] = "EXPIRED_OR_INVALID"
                elif (context_matches and fact["status"] in ("AVAILABLE", "UNAVAILABLE", "UNKNOWN")):
                    # Record well-formed trusted observations even when already
                    # expired. Compare UTC instants (not caller timestamp strings).
                    # Expiry and probe provenance bind equal-time evidence but do
                    # not change the material prerequisite fingerprint on renewal.
                    fact_digest = digest_json({"fact": fact, "valid_until_utc": expiry.isoformat(),
                                               "probe_ref": cap["probe_ref"], "probe_sha256": cap["probe_sha256"]})
                    prior = conn.execute("""SELECT observed_at,material_digest FROM contract_observations
                         WHERE digest=? AND capability_id=? AND worker_id=?""",
                         (digest, cid, grant["worker_id"])).fetchone()
                    previous_at = _timestamp(prior["observed_at"]) if prior else None
                    if prior and at < previous_at:
                        fact["status"] = "STALE_OBSERVATION"
                    elif prior and at == previous_at and fact_digest != prior["material_digest"]:
                        # A conflict at the same instant invalidates BOTH claims
                        # until strictly newer trusted evidence is observed.
                        conn.execute("""UPDATE contract_observations SET material_digest='CONFLICT'
                            WHERE digest=? AND capability_id=? AND worker_id=?""",
                            (digest, cid, grant["worker_id"]))
                        fact["status"] = "STALE_OBSERVATION"
                    else:
                        conn.execute("""INSERT INTO contract_observations VALUES (?,?,?,?,?)
                         ON CONFLICT(digest,capability_id,worker_id) DO UPDATE SET
                         observed_at=excluded.observed_at,material_digest=excluded.material_digest""",
                         (digest, cid, grant["worker_id"], at.isoformat(), fact_digest))
                        if now >= expiry:
                            fact["status"] = "EXPIRED_OR_INVALID"
                        elif fact["status"] == "AVAILABLE":
                            capability_expiries.append(expiry)
            material["capabilities"][cid] = fact
            if fact["status"] != "AVAILABLE":
                failures.append("CAPABILITY_" + cid + "_" + str(fact["status"]))
        return sorted(failures), material, capability_expiries

    def block_unavailable_bridge(self, raw: str | bytes) -> dict[str, Any]:
        packet = parse_mission_packet(raw)
        digest = contract_digest(packet)
        with self._transaction() as conn:
            self._assert_chain(conn)
            return self._blocked(conn, packet, digest, "TRUSTED_PREFLIGHT_BRIDGE_UNAVAILABLE", {})

    def reserve_dispatch(self, raw: str | bytes, adapter: FixtureDispatchAdapter) -> dict[str, Any]:
        if not is_supported_fixture_adapter(adapter):
            raise SchedulerError("Trusted fixture boundary unavailable.")
        packet = parse_mission_packet(raw)
        digest = contract_digest(packet)
        mid, revision = packet["mission_id"], packet["revision"]
        with self._transaction() as conn:
            self._assert_chain(conn)
            now = dt.datetime.now(dt.timezone.utc)
            grant = adapter.resolve_grant(packet, digest, now)
            if grant is None:
                return self._blocked(conn, packet, digest, "GRANT_UNRESOLVED", {})
            # This slice cannot perform commands, writes or actual runtime observation.
            if (not set(packet["allowed_operations"]) <= fixture_operations(adapter)
                or any(o["target_profile"] == "REAL" or o["evaluation_kind"] == "COMMAND"
                       for o in packet["oracles"])):
                return self._blocked(conn, packet, digest, "LIVE_EFFECT_UNQUALIFIED", {})
            reason = self._bind_revision(conn, packet, digest, grant)
            if reason:
                return self._blocked(conn, packet, digest, reason, {})
            ordinal = grant["attempt_ordinal"]
            existing = conn.execute("""SELECT * FROM contract_attempts
                    WHERE mission_id=? AND revision=? AND ordinal=?""", (mid, revision, ordinal)).fetchone()
            if existing:
                return {"status": existing["status"], "cached": True, "fixture_only": True}
            # Slot identity never contains worker, run ID, observation or fingerprint.
            prior = conn.execute("""SELECT * FROM contract_attempts WHERE mission_id=?
                     ORDER BY revision DESC, ordinal DESC LIMIT 1""", (mid,)).fetchone()
            if prior and prior["status"] not in ("COMPLETED", "RECONCILED", "NO_EFFECT"):
                return self._blocked(conn, packet, digest, "PRIOR_EFFECT_UNRECONCILED", {})
            next_ordinal = prior["ordinal"] + 1 if prior and prior["revision"] == revision else 1
            maximum = 1 + min(packet["budget"]["max_identical_retries"], packet["budget"]["max_repair_cycles"])
            if ordinal != next_ordinal or ordinal > maximum:
                return self._blocked(conn, packet, digest, "ATTEMPT_NOT_AUTHORIZED_OR_BUDGET_EXHAUSTED", {})
            try:
                observed = adapter.observe(packet)
                now = dt.datetime.now(dt.timezone.utc)
                current_grant = adapter.resolve_grant(packet, digest, now)
                if current_grant is None or digest_json(current_grant) != digest_json(grant):
                    return self._blocked(conn, packet, digest, "GRANT_CHANGED_OR_EXPIRED_AFTER_OBSERVATION", {})
                grant = current_grant
                failures, material, capability_expiries = self._prerequisites(
                    conn, packet, digest, grant, observed, now)
            except (AuthorityError, TypeError, ValueError, KeyError, OSError):
                return self._blocked(conn, packet, digest, "INVALID_OBSERVATION", {})
            if failures:
                return self._blocked(conn, packet, digest, "|".join(failures), material)
            active_packets = [json.loads(row[0]) for row in conn.execute("""
                SELECT DISTINCT r.packet_json FROM contract_attempts a JOIN contract_revisions r
                ON r.mission_id=a.mission_id AND r.revision=a.revision
                WHERE a.status IN ('RESERVED','RUNNING','UNKNOWN')""")]
            try:
                enforce_wave_budget(active_packets + [packet])
            except SchedulerError:
                return self._blocked(conn, packet, digest, "WAVE_BUDGET_BLOCKED",
                                     sorted(contract_digest(item) for item in active_packets))
            # Bound the claim to the earliest independently validated expiry.
            # A slow budget check or transaction must not turn stale evidence
            # into a new reservation. No caller-provided validity override.
            grant_sha256 = digest_json(grant)
            valid_until = min([_timestamp(grant["valid_until_utc"]), *capability_expiries])
            now = dt.datetime.now(dt.timezone.utc)
            current_grant = adapter.resolve_grant(packet, digest, now)
            if current_grant is None or digest_json(current_grant) != grant_sha256:
                return self._blocked(conn, packet, digest, "GRANT_CHANGED_OR_EXPIRED_BEFORE_RESERVATION", {})
            now = dt.datetime.now(dt.timezone.utc)
            if not _fresh(current_grant, now):
                return self._blocked(conn, packet, digest, "GRANT_CHANGED_OR_EXPIRED_BEFORE_RESERVATION", {})
            if now >= valid_until:
                return self._blocked(conn, packet, digest, "CAPABILITY_EXPIRED_BEFORE_RESERVATION", material)
            fingerprint = digest_json({"contract": digest, "prerequisites": material})
            reservation = uuid.uuid4().hex
            conn.execute("""INSERT INTO contract_attempts VALUES (?,?,?,?,?,?,?,?,?,'RESERVED',NULL)""",
                         (mid, revision, ordinal, digest, reservation, fingerprint, grant["worker_id"],
                          grant["actor_id"], packet["run_id"]))
            reauthorized = conn.execute("UPDATE contract_heads SET state='AUTHORIZED',state_version=state_version+1 WHERE mission_id=? AND state='BLOCKED'", (mid,))
            if reauthorized.rowcount:
                self._event(conn, packet, digest, "PREREQUISITES_REVALIDATED",
                            {"prerequisite_fingerprint": fingerprint, "fixture_only": True})
            conn.execute("UPDATE contract_heads SET state='ACTIVE',state_version=state_version+1 WHERE mission_id=?", (mid,))
            self._event(conn, packet, digest, "DISPATCH_RESERVED",
                        {"reservation_id": reservation, "ordinal": ordinal, "prerequisite_fingerprint": fingerprint,
                         "actor_id": grant["actor_id"], "worker_id": grant["worker_id"],
                         "host_id": grant["host_id"], "grant_sha256": grant_sha256,
                         "valid_until_utc": valid_until.isoformat(), "fixture_only": True})
            return {"status": "RESERVED", "reservation_id": reservation, "ordinal": ordinal,
                    "contract_sha256": digest, "revision": revision, "cached": False, "fixture_only": True}

    def _require_attempt(self, conn, packet, reservation, expected):
        digest = contract_digest(packet)
        mid = packet["mission_id"]
        head = conn.execute("SELECT * FROM contract_heads WHERE mission_id=?", (mid,)).fetchone()
        attempt = conn.execute("SELECT * FROM contract_attempts WHERE reservation_id=?",
                               (reservation,)).fetchone()
        if (not head or not attempt or head["digest"] != digest or head["revision"] != packet["revision"]
            or attempt["mission_id"] != mid or attempt["digest"] != digest
            or attempt["revision"] != packet["revision"] or attempt["run_id"] != packet["run_id"]
            or attempt["status"] not in expected):
            raise SchedulerError("Stale or mismatched dispatch reservation/completion.")
        return attempt

    def _reservation_binding(self, conn, packet, reservation, expected):
        attempt = self._require_attempt(conn, packet, reservation, expected)
        # The chained reservation event is the durable, trusted validity
        # record. No schema migration or caller-owned claim metadata.
        bindings = []
        for row in conn.execute("""SELECT payload_json FROM journal_events
                    WHERE mission_id=? AND run_id=? AND event_type='DISPATCH_RESERVED'""",
                    (packet["mission_id"], packet["run_id"])):
            binding = json.loads(row[0])
            if binding.get("reservation_id") == reservation:
                bindings.append(binding)
        if len(bindings) != 1:
            raise SchedulerError("Missing or ambiguous reservation binding.")
        binding = bindings[0]
        expected_binding = {"contract_sha256": attempt["digest"], "revision": attempt["revision"],
                            "ordinal": attempt["ordinal"], "actor_id": attempt["actor_id"],
                            "worker_id": attempt["worker_id"], "prerequisite_fingerprint": attempt["fingerprint"]}
        if (any(binding.get(key) != value for key, value in expected_binding.items())
                or not _nonempty(binding.get("host_id")) or not _nonempty(binding.get("grant_sha256"))):
            raise SchedulerError("Missing or mismatched trusted reservation validity.")
        _timestamp(binding.get("valid_until_utc"))
        return attempt, binding

    def _invocation_block_reason(self, packet, attempt, binding, adapter):
        now = dt.datetime.now(dt.timezone.utc)
        grant = adapter.resolve_grant(packet, attempt["digest"], now)
        if (not grant or digest_json(grant) != binding["grant_sha256"]
                or (grant["worker_id"], grant["actor_id"], grant["host_id"], grant["attempt_ordinal"])
                != (attempt["worker_id"], attempt["actor_id"], binding["host_id"], attempt["ordinal"])):
            return "GRANT_CHANGED_OR_EXPIRED_BEFORE_INVOCATION"
        now = dt.datetime.now(dt.timezone.utc)
        if not _fresh(grant, now):
            return "GRANT_CHANGED_OR_EXPIRED_BEFORE_INVOCATION"
        if now >= _timestamp(binding["valid_until_utc"]):
            return "CAPABILITY_EXPIRED_BEFORE_INVOCATION"
        return None

    def _no_effect(self, conn, packet, reservation, expected, reason):
        self._change_attempt(conn, packet, reservation, expected, "NO_EFFECT",
                             {"effect": "NO_EFFECT", "reason": reason})
        conn.execute("UPDATE contract_heads SET state='BLOCKED' WHERE mission_id=?", (packet["mission_id"],))
        return {"status": "NO_EFFECT", "reason": reason, "reservation_id": reservation,
                "cached": False, "fixture_only": True}

    def _change_attempt(self, conn, packet, reservation, expected, next_status, result=None):
        digest = contract_digest(packet)
        mid = packet["mission_id"]
        attempt = self._require_attempt(conn, packet, reservation, expected)
        serialized = canonical_json(result) if result is not None else None
        changed = conn.execute("""UPDATE contract_attempts SET status=?,result_json=?
                         WHERE reservation_id=? AND status=?""",
                         (next_status, serialized, reservation, attempt["status"]))
        if changed.rowcount != 1:
            raise SchedulerError("Reservation compare-and-set failed.")
        conn.execute("UPDATE contract_heads SET state_version=state_version+1 WHERE mission_id=?", (mid,))
        self._event(conn, packet, digest, "DISPATCH_" + next_status,
                    {"reservation_id": reservation, "ordinal": attempt["ordinal"],
                     "actor_id": attempt["actor_id"], "worker_id": attempt["worker_id"],
                     "fixture_only": True, "result": result})

    def complete_dispatch(self, raw, reservation_id, result, adapter):
        if not is_supported_fixture_adapter(adapter) or not isinstance(result, dict):
            raise SchedulerError("Trusted completion boundary and object result required.")
        packet = parse_mission_packet(raw)
        digest = contract_digest(packet)
        with self._transaction() as conn:
            self._assert_chain(conn)
            grant = adapter.resolve_grant(packet, digest, dt.datetime.now(dt.timezone.utc))
            attempt = conn.execute("SELECT * FROM contract_attempts WHERE reservation_id=?",
                                   (reservation_id,)).fetchone()
            if not grant or not attempt or (grant["worker_id"], grant["actor_id"], grant["attempt_ordinal"]) != (
                    attempt["worker_id"], attempt["actor_id"], attempt["ordinal"]):
                raise SchedulerError("Completion actor or authorized attempt mismatch.")
            self._change_attempt(conn, packet, reservation_id, {"RUNNING"}, "COMPLETED", result)

    def dispatch_fixture(self, raw, adapter):
        packet = parse_mission_packet(raw)
        claim = self.reserve_dispatch(raw, adapter)
        if claim.get("cached") or claim["status"] != "RESERVED":
            return claim
        reservation = claim["reservation_id"]
        with self._transaction() as conn:
            self._assert_chain(conn)
            attempt, binding = self._reservation_binding(conn, packet, reservation, {"RESERVED"})
            reason = self._invocation_block_reason(packet, attempt, binding, adapter)
            if reason:
                return self._no_effect(conn, packet, reservation, {"RESERVED"}, reason)
            self._change_attempt(conn, packet, reservation, {"RESERVED"}, "RUNNING")

        invocation_started = False

        def before_invoke():
            nonlocal invocation_started
            with self._transaction() as conn:
                self._assert_chain(conn)
                attempt, binding = self._reservation_binding(conn, packet, reservation, {"RUNNING"})
            # Resample after the transaction commit and packet copy, directly
            # before entering the fixture callback. This is not native wall-clock
            # fencing: a host pause after the final check remains outside scope.
            reason = self._invocation_block_reason(packet, attempt, binding, adapter)
            if reason:
                raise _PreInvocationBlocked(reason)
            invocation_started = True

        try:
            result = adapter.invoke(packet, before_invoke=before_invoke)
            if not isinstance(result, dict):
                raise AuthorityError("Fixture handler must return a JSON object.")
            self.complete_dispatch(raw, reservation, result, adapter)
        except BaseException as exc:
            with self._transaction() as conn:
                self._assert_chain(conn)
                if isinstance(exc, _PreInvocationBlocked) and not invocation_started:
                    return self._no_effect(conn, packet, reservation, {"RUNNING"}, str(exc))
                # Once callback entry is possible, failures remain uncertain.
                # A crash before this transaction leaves a non-replayable RUNNING
                # claim. Never infer host quiescence or automatically retry.
                self._change_attempt(conn, packet, reservation, {"RUNNING"}, "UNKNOWN")
            raise
        return {"status": "COMPLETED", "fixture_only": True, "result": result,
                "reservation_id": reservation, "contract_sha256": claim["contract_sha256"]}

    def reconcile_unknown(self, raw, reservation_id, adapter):
        """Only an UNKNOWN claim may use configured fixture reconciliation.

        RESERVED/RUNNING can be actively owned by a dispatcher in any process,
        including the pre-start gap. A fixture assertion cannot prove durable
        quiescence, so these states remain blocked even after restart; an operator
        must establish fencing through a separately authorized recovery procedure.
        UNKNOWN is recorded only after callback exit/failure in this fixture path;
        external effects still require operator-established quiescence.
        """
        if type(adapter) is not FixtureDispatchAdapter:
            raise SchedulerError("Trusted fixture reconciliation unavailable.")
        packet = parse_mission_packet(raw)
        digest = contract_digest(packet)
        evidence = adapter.reconciliation(reservation_id)
        with self._transaction() as conn:
            self._assert_chain(conn)
            grant = adapter.resolve_grant(packet, digest, dt.datetime.now(dt.timezone.utc))
            if not grant or not isinstance(evidence, dict) or (
                evidence.get("contract_sha256") != digest or evidence.get("reservation_id") != reservation_id
                or evidence.get("quiescent") is not True or evidence.get("effect") not in ("NO_EFFECT", "EFFECT_OBSERVED")
                or not _nonempty(evidence.get("evidence_ref"))):
                raise SchedulerError("Unresolved effect; no replay permitted.")
            attempt = self._require_attempt(conn, packet, reservation_id, {"UNKNOWN"})
            if (grant["worker_id"], grant["actor_id"], grant["attempt_ordinal"]) != (
                    attempt["worker_id"], attempt["actor_id"], attempt["ordinal"]):
                raise SchedulerError("Reconciliation actor or authorized attempt mismatch.")
            self._change_attempt(conn, packet, reservation_id, {"UNKNOWN"},
                                 "RECONCILED", {"effect": evidence["effect"], "evidence_ref": evidence["evidence_ref"]})


def archive_historical_journal(source: Path, destination: Path) -> str:
    """Explicit read-only SQLite backup; preserve v1 bytes/hash chain, no live import.

    Freeze original and backup operationally before cutover. Rollback retains the
    separate contract journal and requires authority plus effect reconciliation.
    """
    source, destination = Path(source), Path(destination)
    if not source.is_file() or destination.exists() or source.resolve() == destination.resolve():
        raise SchedulerError("Historical backup requires existing source and unused destination.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
        tables = dict(src.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
        if tables.get("missions") != "table" or tables.get("journal_events") != "table" or "contract_heads" in tables:
            raise SchedulerError("Expected historical journal only.")
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            dst.row_factory = sqlite3.Row
            previous = GENESIS_EVENT_HASH
            for row in dst.execute("SELECT * FROM journal_events ORDER BY seq"):
                if (row["prev_event_sha256"] != previous or
                    hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest() != row["payload_sha256"]):
                    raise SchedulerError("Historical chain verification failed; preserve backup for diagnosis.")
                previous = _compute_event_chain_hash(row)
    return hashlib.sha256(destination.read_bytes()).hexdigest()
