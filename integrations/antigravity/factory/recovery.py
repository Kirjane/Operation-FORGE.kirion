"""F13 — Recovery and continuity: crash reconciliation, SQLite online backup/restore, and Sandbox Capsules."""
from __future__ import annotations

import datetime as dt
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Callable

from . import REPO_ROOT
from .authority import AuthorityError, is_valid_git_sha, validate_contract, verify_mission_packet
from .delivery import compute_delivery_key
from .scheduler import FactoryJournal


class RecoveryManager:
    """Reconciles interrupted missions, performs SQLite WAL backups, and emits schema-valid RecoveryCapsules."""

    def __init__(self, journal: FactoryJournal) -> None:
        self.journal = journal

    def backup_journal(self, backup_db_path: Path) -> Path:
        """Create a consistent online backup of the SQLite WAL journal database."""
        backup_db_path.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(self.journal.db_path)
        dst = sqlite3.connect(backup_db_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return backup_db_path

    def restore_journal(self, backup_db_path: Path, restored_db_path: Path) -> FactoryJournal:
        """Restore a journal from an existing backup file, verifying required tables and hash-chain integrity."""
        if not backup_db_path.is_file():
            raise AuthorityError(f"Backup journal database does not exist: {backup_db_path}")
        src = sqlite3.connect(f"file:{backup_db_path.resolve().as_posix()}?mode=ro", uri=True)
        try:
            tables = {
                row[0]
                for row in src.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if not {"missions", "journal_events"} <= tables:
                raise AuthorityError(
                    f"Backup journal {backup_db_path} is missing required tables ('missions', 'journal_events'); found {sorted(tables)}"
                )
            restored_db_path.parent.mkdir(parents=True, exist_ok=True)
            dst = sqlite3.connect(restored_db_path)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        restored = FactoryJournal(restored_db_path)
        if not restored.verify_hash_chain():
            raise RuntimeError("Restored SQLite journal failed hash-chain tamper verification.")
        return restored

    def reconcile_interrupted_mission(
        self,
        mission_id: str,
        *,
        interruption_point: str,
        observed_local_sha: str,
        remote_head_probe: Callable[[str], str | None] | None = None,
        active_leases: list[str] | None = None,
        evidence_digests: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Reconstruct exact mission state after an orchestrator crash or interruption
        without duplicating local commits or remote broker writes.
        Verifies hash-chain integrity and MissionPacket authority up front, halts terminal
        QUARANTINED/REJECTED missions, probes remote_head_probe whenever provided to catch
        branch drift regardless of PENDING_REMOTE presence, distinguishes VALIDATED_DRAFT_PR
        from BLOCKED_DIAGNOSTIC_DRAFT receipts, and performs WAL BEGIN IMMEDIATE CAS updates.
        """
        if not self.journal.verify_hash_chain():
            raise AuthorityError("Journal hash-chain tamper verification failed; recovery halted.")

        m = self.journal.get_mission(mission_id)
        packet = m["packet"]
        verify_mission_packet(packet)

        branch = packet["permitted_branch"]
        base_sha = m["base_sha"]
        candidate_sha = observed_local_sha or m["candidate_sha"]
        if not is_valid_git_sha(candidate_sha):
            raise AuthorityError(f"Invalid or all-zero candidate_sha during reconciliation: {candidate_sha!r}")

        delivery_key = compute_delivery_key(mission_id, branch, candidate_sha)

        delivery_reconciled = False
        remote_already_delivered = False
        remote_drift_or_unreconciled = False
        is_terminal_blocked = m["state"] in ("QUARANTINED", "REJECTED")

        if not is_terminal_blocked:
            # Probe remote head whenever provided so branch drift is caught even without PENDING_REMOTE rows
            probed_remote_sha: str | None = None
            probe_performed = False
            probe_failed = False
            if remote_head_probe is not None:
                probe_performed = True
                try:
                    probed_remote_sha = remote_head_probe(branch)
                except Exception:
                    probe_failed = True
                    remote_drift_or_unreconciled = True
                else:
                    if probed_remote_sha not in (None, base_sha, candidate_sha):
                        remote_drift_or_unreconciled = True

            conn = sqlite3.connect(self.journal.db_path, timeout=15.0, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            try:
                table_check = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='delivery_receipts'"
                ).fetchone()
                if table_check is not None:
                    pending_rows = conn.execute(
                        "SELECT * FROM delivery_receipts WHERE mission_id = ? AND branch = ? AND status = 'PENDING_REMOTE'",
                        (mission_id, branch),
                    ).fetchall()
                    if any(r["candidate_sha"] != candidate_sha for r in pending_rows):
                        remote_drift_or_unreconciled = True
                        delivery_reconciled = False
                    elif any(r["delivery_key"] == delivery_key for r in pending_rows):
                        matching_pending = next(r for r in pending_rows if r["delivery_key"] == delivery_key)
                        if not probe_performed or probe_failed or remote_drift_or_unreconciled:
                            remote_drift_or_unreconciled = True
                            delivery_reconciled = False
                        else:
                            now_upd = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                            if probed_remote_sha == candidate_sha:
                                conn.execute("BEGIN IMMEDIATE;")
                                cur = conn.execute(
                                    """
                                    UPDATE delivery_receipts
                                    SET status = 'DELIVERED', updated_at_utc = ?
                                    WHERE delivery_key = ? AND status = 'PENDING_REMOTE'
                                    """,
                                    (now_upd, delivery_key),
                                )
                                conn.execute("COMMIT;")
                                if cur.rowcount == 1:
                                    delivery_reconciled = True
                                    if matching_pending["pr_mode"] == "VALIDATED_DRAFT_PR":
                                        remote_already_delivered = True
                                else:
                                    refreshed = conn.execute(
                                        "SELECT status, pr_mode FROM delivery_receipts WHERE delivery_key = ?",
                                        (delivery_key,),
                                    ).fetchone()
                                    if refreshed is not None and refreshed["status"] == "DELIVERED":
                                        delivery_reconciled = True
                                        if refreshed["pr_mode"] == "VALIDATED_DRAFT_PR":
                                            remote_already_delivered = True
                                    else:
                                        remote_drift_or_unreconciled = True
                                        delivery_reconciled = False
                            elif probed_remote_sha in (None, base_sha):
                                conn.execute("BEGIN IMMEDIATE;")
                                cur = conn.execute(
                                    """
                                    UPDATE delivery_receipts
                                    SET status = 'RECONCILED_RETRY_ALLOWED', updated_at_utc = ?
                                    WHERE delivery_key = ? AND status = 'PENDING_REMOTE'
                                    """,
                                    (now_upd, delivery_key),
                                )
                                conn.execute("COMMIT;")
                                if cur.rowcount == 1:
                                    delivery_reconciled = True
                                else:
                                    remote_drift_or_unreconciled = True
                                    delivery_reconciled = False
                            else:
                                remote_drift_or_unreconciled = True
                                delivery_reconciled = False
                    else:
                        receipt = conn.execute(
                            "SELECT * FROM delivery_receipts WHERE delivery_key = ?",
                            (delivery_key,),
                        ).fetchone()
                        if receipt is not None and receipt["status"] == "DELIVERED":
                            if receipt["pr_mode"] == "VALIDATED_DRAFT_PR":
                                remote_already_delivered = True
                                delivery_reconciled = True
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK;")
                raise
            finally:
                conn.close()

        if is_terminal_blocked:
            next_action = "HALT_BLOCKED_TERMINAL_QUARANTINED_OR_REJECTED"
        elif remote_drift_or_unreconciled:
            next_action = "HALT_BLOCKED_REQUIRE_MAINTAINER_RECONCILIATION"
        elif remote_already_delivered:
            next_action = "NO_OP_ALREADY_DELIVERED_AWAIT_INDEPENDENT_REVIEW"
        elif interruption_point == "PRE_LOCAL_COMMIT":
            next_action = "RESUME_CLEAN_WORKTREE_COMMIT_AND_RUN_GATES"
        elif interruption_point == "POST_LOCAL_COMMIT":
            next_action = "VERIFY_EXACT_SHA_GATES_AND_FRESH_NOX_REVIEW"
        elif interruption_point in ("PRE_BROKER_RECEIPT", "POST_BROKER_RECEIPT"):
            next_action = "EXECUTE_IDEMPOTENT_NAIRU_DELIVERY_WITH_KEY"
        elif interruption_point in ("BRANCH_DRIFT", "CREDENTIAL_REVOKED", "QUOTA_EXHAUSTED"):
            next_action = "HALT_BLOCKED_REQUIRE_MAINTAINER_RECONCILIATION"
        else:
            next_action = "REVERIFY_AUTHORITY_AND_LEASES_BEFORE_RESUME"

        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        capsule = {
            "schema_version": 1,
            "capsule_id": f"cap-{uuid.uuid4().hex[:12]}",
            "mission_id": mission_id,
            "run_id": m["run_id"],
            "base_sha": base_sha,
            "candidate_sha": candidate_sha,
            "lifecycle_state": m["state"],
            "state_version": m["state_version"],
            "interruption_point": interruption_point,
            "active_leases": list(active_leases or []),
            "evidence_digests": list(evidence_digests or []),
            "delivery_key": delivery_key,
            "delivery_reconciled": delivery_reconciled,
            "next_allowed_action": next_action,
            "created_at_utc": now,
        }
        validate_contract(capsule, "recovery-capsule.schema.json")
        return capsule

    def export_canonical_forge_sandbox_capsule(
        self,
        recovery_capsule: dict[str, Any],
        *,
        worktree_status: str = "clean",
        commands_executed: list[str] | None = None,
        known_failures: list[str] | None = None,
        known_unverified_claims: list[str] | None = None,
        created_by_role: str = "Maintainer",
    ) -> dict[str, Any]:
        """Serialize a factory RecoveryCapsule into the canonical root schemas/sandbox-capsule.schema.json format."""
        validate_contract(recovery_capsule, "recovery-capsule.schema.json")
        m = self.journal.get_mission(recovery_capsule["mission_id"])
        packet = m["packet"]
        canonical = {
            "capsule_version": 1,
            "repository": packet["repo_name"],
            "remote": "origin",
            "source_branch": packet["permitted_branch"],
            "source_sha": recovery_capsule["base_sha"],
            "target_branch": packet["permitted_branch"],
            "candidate_head": recovery_capsule["candidate_sha"],
            "worktree_status": worktree_status,
            "commands_executed": list(commands_executed or []),
            "known_failures": list(known_failures or []),
            "known_unverified_claims": list(known_unverified_claims or []),
            "blocker": (
                f"Interruption at {recovery_capsule['interruption_point']}"
                if recovery_capsule["next_allowed_action"].startswith("HALT_BLOCKED")
                else None
            ),
            "next_permitted_action": recovery_capsule["next_allowed_action"],
            "created_at": recovery_capsule["created_at_utc"],
            "created_by_role": created_by_role,
        }
        validate_contract(canonical, "sandbox-capsule.schema.json", base_dir=REPO_ROOT / "schemas")
        return canonical
