"""Read-only projection of the existing contract journal; no new state authority.

A locally consistent event chain is not an authenticated remote witness. All
current ContractJournal dispatches are fixtures. This view never grants a lease,
replays an effect, or derives acceptance from a completed callback.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

from .dispatch_preflight import _CONTRACT_STORAGE_CATALOG
from .mission_contract import canonical_json, contract_digest, parse_mission_packet
from .scheduler import GENESIS_EVENT_HASH, _compute_event_chain_hash, storage_catalog

_ATTEMPT_TRANSITIONS = {
    "RESERVED": {"RUNNING", "NO_EFFECT"},
    "RUNNING": {"COMPLETED", "UNKNOWN", "NO_EFFECT"},
    "UNKNOWN": {"RECONCILED"},
}


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _project(conn):
    _require(storage_catalog(conn) == _CONTRACT_STORAGE_CATALOG, "UNSUPPORTED_JOURNAL_CATALOG")
    heads, attempts, revisions = {}, {}, {}
    blockers, observations = set(), {}
    prior_hash, event_count, unbound_blockers = GENESIS_EVENT_HASH, 0, 0
    for event in conn.execute("SELECT * FROM journal_events ORDER BY seq"):
        event_count += 1
        _require(event["prev_event_sha256"] == prior_hash and
                 hashlib.sha256(event["payload_json"].encode("utf-8")).hexdigest() ==
                 event["payload_sha256"], "JOURNAL_CHAIN_MISMATCH")
        prior_hash = _compute_event_chain_hash(event)
        payload = json.loads(event["payload_json"])
        mid, kind, version = event["mission_id"], event["event_type"], event["state_version"]
        digest, revision = payload["contract_sha256"], payload["revision"]
        head = heads.get(mid)
        _require(payload.get("fixture_only") is True, "UNQUALIFIED_EVENT_PROVENANCE")
        if kind == "CONTRACT_AUTHORIZED":
            _require(revision == (head["revision"] + 1 if head else 1) and
                     version == (head["state_version"] + 1 if head else 1),
                     "AUTHORIZATION_SEQUENCE_MISMATCH")
            row = conn.execute("SELECT * FROM contract_revisions WHERE mission_id=? AND revision=?",
                               (mid, revision)).fetchone()
            _require(row is not None and row["digest"] == digest, "MISSING_CONTRACT_REVISION")
            packet = parse_mission_packet(row["packet_json"])
            _require(packet["schema_version"] == 2 and packet["mission_id"] == mid and
                     packet["revision"] == revision and contract_digest(packet) == digest,
                     "CONTRACT_REVISION_MISMATCH")
            if head:
                _require(packet["previous_contract_sha256"] == head["digest"] and
                         not any(a["mission_id"] == mid and a["status"] in
                                 ("RESERVED", "RUNNING", "UNKNOWN") for a in attempts.values()),
                         "UNRECONCILED_REVISION")
            revisions[(mid, revision)] = digest
            heads[mid] = {"mission_id": mid, "revision": revision, "digest": digest,
                          "state": "AUTHORIZED", "state_version": version,
                          "repo_id": packet["repo_id"], "repo_name": packet["repo_name"],
                          "base_sha": packet["base_sha"], "branch": packet["permitted_branch"],
                          "depends_on": packet["depends_on"], "last_blocker": None}
            continue
        if kind == "DISPATCH_BLOCKED":
            blockers.add((mid,digest,payload["prerequisite_fingerprint"],payload["reason"]))
            if head is None or head["digest"] != digest or head["revision"] != revision:
                _require(version == (head["state_version"] if head else 1),
                         "UNBOUND_BLOCKER_CHANGED_STATE")
                unbound_blockers += 1
                continue
            if version == head["state_version"] + 1:
                _require(head["state"] != "BLOCKED" and not any(
                    a["mission_id"] == mid and a["status"] in ("RESERVED", "RUNNING", "UNKNOWN")
                    for a in attempts.values()), "BLOCKER_STATE_MISMATCH")
                head.update(state="BLOCKED", state_version=version)
            else:
                _require(version == head["state_version"], "BLOCKER_VERSION_MISMATCH")
            head["last_blocker"] = payload["reason"]
            continue
        _require(head is not None and head["digest"] == digest and head["revision"] == revision,
                 "EVENT_CONTRACT_MISMATCH")
        if kind == "CAPABILITY_OBSERVED":
            _require(version == head["state_version"], "OBSERVATION_VERSION_MISMATCH")
            observations[(digest,payload["capability_id"],payload["worker_id"])] = (payload["observed_at"],payload["material_digest"])
            continue
        if kind == "PREREQUISITES_REVALIDATED":
            _require(head["state"] == "BLOCKED" and version == head["state_version"] + 1,
                     "REVALIDATION_SEQUENCE_MISMATCH")
            head.update(state="AUTHORIZED", state_version=version, last_blocker=None)
            continue
        if kind in ("ASSURANCE_EVIDENCE", "ASSURANCE_FIXTURE_DECISION"):
            _require(version == head["state_version"], "ASSURANCE_VERSION_MISMATCH")
            # Fixture assurance is never a lifecycle acceptance event.
            continue
        if kind == "DISPATCH_RESERVED":
            reservation = payload["reservation_id"]
            _require(reservation not in attempts and version == head["state_version"] + 1 and
                     head["state"] in ("AUTHORIZED", "ACTIVE"), "RESERVATION_SEQUENCE_MISMATCH")
            _require(not any(a["mission_id"] == mid and a["status"] in
                             ("RESERVED", "RUNNING", "UNKNOWN") for a in attempts.values()),
                     "CONCURRENT_UNRECONCILED_ATTEMPT")
            prior_ordinals = [a["ordinal"] for a in attempts.values()
                              if a["mission_id"] == mid and a["revision"] == revision]
            _require(payload["ordinal"] == (max(prior_ordinals, default=0) + 1),
                     "ATTEMPT_ORDINAL_MISMATCH")
            attempts[reservation] = {
                "mission_id": mid, "revision": revision, "ordinal": payload["ordinal"],
                "digest": digest, "reservation_id": reservation,
                "fingerprint": payload["prerequisite_fingerprint"],
                "worker_id": payload["worker_id"], "actor_id": payload["actor_id"],
                "run_id": event["run_id"], "status": "RESERVED", "result_json": None,
                "host_id": payload["host_id"], "valid_until_utc": payload["valid_until_utc"],
            }
            head.update(state="ACTIVE", state_version=version, last_blocker=None)
            continue
        _require(kind.startswith("DISPATCH_"), "UNKNOWN_JOURNAL_EVENT")
        status = kind.removeprefix("DISPATCH_")
        attempt = attempts.get(payload["reservation_id"])
        _require(attempt is not None and status in _ATTEMPT_TRANSITIONS.get(attempt["status"], set())
                 and version == head["state_version"] + 1 and
                 all(attempt[key] == value for key, value in {
                     "mission_id": mid, "revision": revision, "digest": digest,
                     "run_id": event["run_id"], "ordinal": payload["ordinal"],
                     "actor_id": payload["actor_id"], "worker_id": payload["worker_id"],
                 }.items()), "ATTEMPT_TRANSITION_MISMATCH")
        attempt["status"] = status
        result = payload.get("result")
        attempt["result_json"] = canonical_json(result) if result is not None else None
        head["state_version"] = version
        if status == "NO_EFFECT":
            head.update(state="BLOCKED", last_blocker=result["reason"])
    # Materialized state is checked against derived state, never accepted on sight.
    stored_revisions = {(row["mission_id"], row["revision"]): row["digest"] for row in
                        conn.execute("SELECT * FROM contract_revisions")}
    _require(stored_revisions == revisions, "REVISION_PROJECTION_MISMATCH")
    stored_heads = {row["mission_id"]: dict(row) for row in conn.execute("SELECT * FROM contract_heads")}
    _require(set(stored_heads) == set(heads), "HEAD_PROJECTION_MISMATCH")
    for mid, row in stored_heads.items():
        _require(all(heads[mid].get(key) == value for key, value in row.items()),
                 "HEAD_PROJECTION_MISMATCH")
    stored_attempts = {row["reservation_id"]: dict(row) for row in conn.execute("SELECT * FROM contract_attempts")}
    _require(set(stored_attempts) == set(attempts), "ATTEMPT_PROJECTION_MISMATCH")
    for reservation, row in stored_attempts.items():
        _require(all(attempts[reservation].get(key) == value for key, value in row.items()),
                 "ATTEMPT_PROJECTION_MISMATCH")
    _require({tuple(row) for row in conn.execute("SELECT mission_id,digest,fingerprint,reason FROM contract_blockers")} == blockers, "BLOCKER_PROJECTION_MISMATCH")
    _require({tuple(row)[:3]:tuple(row)[3:] for row in conn.execute("SELECT digest,capability_id,worker_id,observed_at,material_digest FROM contract_observations")} == observations, "OBSERVATION_PROJECTION_MISMATCH")
    missions = []
    for mid, head in sorted(heads.items()):
        rows = [{key: value for key, value in attempt.items() if key != "result_json"}
                for attempt in attempts.values() if attempt["mission_id"] == mid]
        pending = any(row["status"] in ("RESERVED", "RUNNING", "UNKNOWN") for row in rows)
        missions.append({**head, "attempts": rows, "reconciliation_required": pending,
                         "acceptance": "NOT_ESTABLISHED", "replay_permitted": False})
    return {"status": "PROJECTED", "scope": "LOCAL_FIXTURE_JOURNAL_ONLY",
            "chain_head": prior_hash, "event_count": event_count, "missions": missions,
            "unbound_blockers": unbound_blockers, "remote_state_verified": False,
            "native_host_verified": False, "authority_granted": False,
            "promotion_authorized": False}


def read_contract_board(path):
    """Read one coherent SQLite snapshot without initializing or migrating it."""
    try:
        db = Path(path).resolve(strict=True)
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            return _project(conn)
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, IndexError) as exc:
        # Do not publish raw database payloads, paths, or exception messages.
        return {"status": "BLOCKED", "reason": str(exc) if type(exc) is ValueError
                and str(exc).isupper() and str(exc).replace("_", "").isalnum()
                else type(exc).__name__, "missions": [], "authority_granted": False,
                "promotion_authorized": False}
