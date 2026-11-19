"""F07 — Deterministic DAG scheduler, collision detector, budget guard, and SQLite WAL hash-chained journal."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .authority import (
    AuthorityError,
    is_valid_git_sha,
    validate_contract,
    validate_lifecycle_transition,
    verify_mission_packet,
)
from .policy import normalize_rel_path, path_matches_prefix

GENESIS_EVENT_HASH = "0" * 64


def _compute_event_chain_hash(ev: Any) -> str:
    """Compute tamper-evident SHA-256 digest binding all immutable metadata and payload digest of a journal event."""
    canonical = json.dumps(
        {
            "seq": ev["seq"],
            "event_id": ev["event_id"],
            "mission_id": ev["mission_id"],
            "run_id": ev["run_id"],
            "stage": ev["stage"],
            "event_type": ev["event_type"],
            "state_version": ev["state_version"],
            "payload_sha256": ev["payload_sha256"],
            "prev_event_sha256": ev["prev_event_sha256"],
            "created_at_utc": ev["created_at_utc"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SchedulerError(AuthorityError):
    """Raised on DAG cycles, parallel path collisions, budget exhaustion, or CAS conflicts."""


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def paths_overlap(path_a: str, path_b: str) -> bool:
    norm_a = normalize_rel_path(path_a.rstrip("/"))
    norm_b = normalize_rel_path(path_b.rstrip("/"))
    return path_matches_prefix(norm_a, norm_b) or path_matches_prefix(norm_b, norm_a)


def _is_writer_packet(packet: dict[str, Any]) -> bool:
    """Return True for any Code Writer, Integration Writer, or mutating packet."""
    role = packet.get("formal_role")
    ops = set(packet.get("allowed_operations", []))
    return role in ("Code Writer", "Integration Writer") or bool(ops & {"WRITE_OWNED", "INTEGRATE_BRANCH"})


def detect_parallel_collisions(packets: list[dict[str, Any]]) -> list[str]:
    """Detect overlapping owned_paths, owned_modules, or owned_behaviors across concurrent writer/integrator packets."""
    writers = [p for p in packets if _is_writer_packet(p)]
    collisions: list[str] = []
    for i in range(len(writers)):
        for j in range(i + 1, len(writers)):
            a, b = writers[i], writers[j]
            for pa in a.get("owned_paths", []):
                for pb in b.get("owned_paths", []):
                    if paths_overlap(pa, pb):
                        collisions.append(f"Path collision between {a['mission_id']} ({pa}) and {b['mission_id']} ({pb})")
            mods_a = {str(x).strip().lower() for x in a.get("owned_modules", []) if str(x).strip()}
            mods_b = {str(x).strip().lower() for x in b.get("owned_modules", []) if str(x).strip()}
            shared_mods = sorted(mods_a & mods_b)
            if shared_mods:
                collisions.append(f"Module collision between {a['mission_id']} and {b['mission_id']}: {shared_mods}")
            beh_a = {str(x).strip().lower() for x in a.get("owned_behaviors", []) if str(x).strip()}
            beh_b = {str(x).strip().lower() for x in b.get("owned_behaviors", []) if str(x).strip()}
            shared_beh = sorted(beh_a & beh_b)
            if shared_beh:
                collisions.append(f"Behavior collision between {a['mission_id']} and {b['mission_id']}: {shared_beh}")
    return collisions


def build_topological_waves(missions: list[dict[str, Any]]) -> list[list[str]]:
    """Validate acyclic DAG and group mission IDs into parallel execution waves."""
    by_id: dict[str, dict[str, Any]] = {}
    for m in missions:
        mid = m.get("mission_id") or m.get("id")
        if not mid:
            raise SchedulerError("Mission entry missing mission_id/id.")
        if mid in by_id:
            raise SchedulerError(f"Duplicate mission ID in DAG: {mid}")
        by_id[mid] = m

    in_degree: dict[str, int] = {mid: 0 for mid in by_id}
    dependents: dict[str, list[str]] = {mid: [] for mid in by_id}

    for mid, m in by_id.items():
        for dep in m.get("depends_on", []):
            if dep not in by_id:
                raise SchedulerError(f"Mission {mid} depends on unknown mission {dep}")
            if dep == mid:
                raise SchedulerError(f"Mission {mid} has a self-dependency cycle")
            in_degree[mid] += 1
            dependents[dep].append(mid)

    waves: list[list[str]] = []
    ready = sorted(mid for mid, deg in in_degree.items() if deg == 0)
    visited = 0

    while ready:
        waves.append(ready)
        next_ready: list[str] = []
        for mid in ready:
            visited += 1
            for child in dependents[mid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    next_ready.append(child)
        ready = sorted(next_ready)

    if visited != len(by_id):
        unresolved = sorted(mid for mid, deg in in_degree.items() if deg > 0)
        raise SchedulerError(f"Cycle detected in mission DAG involving: {unresolved}")

    return waves


def enforce_wave_budget(packets: list[dict[str, Any]]) -> None:
    """Enforce tightest packet budget (capped at 3 parallel writers and 3 parallel read-only reviewers) and zero collisions."""
    writers = [p for p in packets if _is_writer_packet(p)]
    reviewers = [p for p in packets if p.get("formal_role") == "Reviewer"]

    writer_caps = [3]
    reviewer_caps = [3]
    for p in packets:
        budget = p.get("budget")
        if isinstance(budget, dict):
            mw = budget.get("max_parallel_writers")
            mr = budget.get("max_parallel_reviewers")
            if isinstance(mw, int) and not isinstance(mw, bool) and mw >= 1:
                writer_caps.append(mw)
            if isinstance(mr, int) and not isinstance(mr, bool) and mr >= 1:
                reviewer_caps.append(mr)

    max_writers = min(writer_caps)
    max_reviewers = min(reviewer_caps)
    if len(writers) > max_writers:
        raise SchedulerError(f"Wave exceeds max_parallel_writers budget ({len(writers)} > {max_writers})")
    if len(reviewers) > max_reviewers:
        raise SchedulerError(f"Wave exceeds max_parallel_reviewers budget ({len(reviewers)} > {max_reviewers})")
    collisions = detect_parallel_collisions(packets)
    if collisions:
        raise SchedulerError("Parallel ownership collision rejected: " + "; ".join(collisions))


class FactoryJournal:
    """Append-only SQLite WAL event stream with compare-and-set state version and idempotent dispatch."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS missions (
                    mission_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    state_version INTEGER NOT NULL,
                    base_sha TEXT NOT NULL,
                    candidate_sha TEXT NOT NULL,
                    repair_cycles INTEGER NOT NULL DEFAULT 0,
                    identical_retries INTEGER NOT NULL DEFAULT 0,
                    last_failure_sig TEXT NOT NULL DEFAULT '',
                    packet_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS journal_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    mission_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    state_version INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    prev_event_sha256 TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dispatches (
                    dispatch_key TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    context_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                """
            )
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def register_mission(self, packet: dict[str, Any]) -> dict[str, Any]:
        verify_mission_packet(packet)
        mid = packet["mission_id"]
        run_id = packet["run_id"]
        base_sha = packet["base_sha"]
        canonical_packet_json = json.dumps(packet, sort_keys=True)
        now = utc_now_iso()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            existing = conn.execute("SELECT * FROM missions WHERE mission_id = ?", (mid,)).fetchone()
            if existing is not None:
                conn.execute("ROLLBACK;")
                if existing["packet_json"] != canonical_packet_json:
                    raise SchedulerError(
                        f"Conflicting re-registration for mission_id={mid!r}: submitted packet differs from stored mission."
                    )
                data = dict(existing)
                data["packet"] = json.loads(data["packet_json"])
                return data

            conn.execute(
                """
                INSERT INTO missions (
                    mission_id, run_id, state, state_version, base_sha, candidate_sha,
                    repair_cycles, identical_retries, last_failure_sig, packet_json, updated_at_utc
                ) VALUES (?, ?, 'PLANNED', 1, ?, ?, 0, 0, '', ?, ?)
                """,
                (mid, run_id, base_sha, base_sha, canonical_packet_json, now),
            )
            self._append_event_in_tx(
                conn,
                mission_id=mid,
                run_id=run_id,
                stage="INTAKE",
                event_type="MISSION_REGISTERED",
                state_version=1,
                payload={"state": "PLANNED", "base_sha": base_sha},
            )
            conn.execute("COMMIT;")
            return self.get_mission(mid)
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def _append_event_in_tx(
        self,
        conn: sqlite3.Connection,
        *,
        mission_id: str,
        run_id: str,
        stage: str,
        event_type: str,
        state_version: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        last_row = conn.execute(
            """
            SELECT seq, event_id, mission_id, run_id, stage, event_type, state_version,
                   payload_sha256, prev_event_sha256, created_at_utc
            FROM journal_events ORDER BY seq DESC LIMIT 1
            """
        ).fetchone()
        if last_row is None:
            prev_hash = GENESIS_EVENT_HASH
        else:
            prev_hash = _compute_event_chain_hash(last_row)

        payload_json = json.dumps(payload, sort_keys=True)
        payload_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        event_id = f"evt-{uuid.uuid4().hex[:16]}"
        now = utc_now_iso()

        cur = conn.execute(
            """
            INSERT INTO journal_events (
                event_id, mission_id, run_id, stage, event_type, state_version,
                payload_json, payload_sha256, prev_event_sha256, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, mission_id, run_id, stage, event_type, state_version, payload_json, payload_sha256, prev_hash, now),
        )
        event_obj = {
            "schema_version": 1,
            "seq": cur.lastrowid,
            "event_id": event_id,
            "mission_id": mission_id,
            "run_id": run_id,
            "stage": stage,
            "event_type": event_type,
            "state_version": state_version,
            "payload": payload,
            "payload_sha256": payload_sha256,
            "prev_event_sha256": prev_hash,
            "created_at_utc": now,
        }
        validate_contract(event_obj, "journal-event.schema.json")
        return event_obj

    def transition_state(
        self,
        mission_id: str,
        next_state: str,
        *,
        expected_version: int,
        actor_role: str,
        is_author: bool = False,
        candidate_sha: str | None = None,
        stage: str = "LIFECYCLE",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if candidate_sha is not None and not is_valid_git_sha(candidate_sha):
            raise SchedulerError(f"Invalid or all-zero candidate_sha in transition_state: {candidate_sha!r}")
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute("SELECT * FROM missions WHERE mission_id = ?", (mission_id,)).fetchone()
            if row is None:
                raise SchedulerError(f"Unknown mission_id: {mission_id}")
            if row["state_version"] != expected_version:
                raise SchedulerError(
                    f"Compare-and-set version conflict for {mission_id}: expected {expected_version}, found {row['state_version']}"
                )

            current_state = row["state"]
            validate_lifecycle_transition(current_state, next_state, actor_role=actor_role, is_author=is_author)
            new_version = expected_version + 1
            new_sha = candidate_sha or row["candidate_sha"]
            now = utc_now_iso()

            cur = conn.execute(
                """
                UPDATE missions
                SET state = ?, state_version = ?, candidate_sha = ?, updated_at_utc = ?
                WHERE mission_id = ? AND state_version = ?
                """,
                (next_state, new_version, new_sha, now, mission_id, expected_version),
            )
            if cur.rowcount != 1:
                raise SchedulerError(f"CAS update failed for {mission_id}")

            payload = {
                "from_state": current_state,
                "to_state": next_state,
                "actor_role": actor_role,
                "candidate_sha": new_sha,
                **(details or {}),
            }
            self._append_event_in_tx(
                conn,
                mission_id=mission_id,
                run_id=row["run_id"],
                stage=stage,
                event_type="STATE_TRANSITION",
                state_version=new_version,
                payload=payload,
            )
            conn.execute("COMMIT;")
            return self.get_mission(mission_id)
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def record_idempotent_dispatch(
        self,
        dispatch_key: str,
        mission_id: str,
        worker_id: str,
        context_id: str,
        result: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        """Record or return an existing idempotent worker dispatch result. Returns (was_cached, result)."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            existing = conn.execute("SELECT * FROM dispatches WHERE dispatch_key = ?", (dispatch_key,)).fetchone()
            if existing is not None:
                conn.execute("ROLLBACK;")
                return True, json.loads(existing["result_json"])

            now = utc_now_iso()
            conn.execute(
                """
                INSERT INTO dispatches (dispatch_key, mission_id, worker_id, context_id, status, result_json, created_at_utc)
                VALUES (?, ?, ?, ?, 'COMPLETED', ?, ?)
                """,
                (dispatch_key, mission_id, worker_id, context_id, json.dumps(result, sort_keys=True), now),
            )
            m = conn.execute("SELECT * FROM missions WHERE mission_id = ?", (mission_id,)).fetchone()
            if m is not None:
                self._append_event_in_tx(
                    conn,
                    mission_id=mission_id,
                    run_id=m["run_id"],
                    stage="DISPATCH",
                    event_type="WORKER_DISPATCHED",
                    state_version=m["state_version"],
                    payload={"dispatch_key": dispatch_key, "worker_id": worker_id, "context_id": context_id},
                )
            conn.execute("COMMIT;")
            return False, result
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def get_mission(self, mission_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM missions WHERE mission_id = ?", (mission_id,)).fetchone()
            if row is None:
                raise SchedulerError(f"Mission not found in journal: {mission_id}")
            data = dict(row)
            data["packet"] = json.loads(data["packet_json"])
            return data
        finally:
            conn.close()

    def list_events(self, mission_id: str | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            if mission_id:
                rows = conn.execute("SELECT * FROM journal_events WHERE mission_id = ? ORDER BY seq ASC", (mission_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM journal_events ORDER BY seq ASC").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["payload"] = json.loads(d.pop("payload_json"))
                out.append(d)
            return out
        finally:
            conn.close()

    def verify_hash_chain(self) -> bool:
        """Verify tamper-evidence of the entire journal_events hash chain including all event metadata columns."""
        events = self.list_events()
        prev_hash = GENESIS_EVENT_HASH
        for ev in events:
            if ev["prev_event_sha256"] != prev_hash:
                return False
            payload_json = json.dumps(ev["payload"], sort_keys=True)
            if hashlib.sha256(payload_json.encode("utf-8")).hexdigest() != ev["payload_sha256"]:
                return False
            prev_hash = _compute_event_chain_hash(ev)
        return True
