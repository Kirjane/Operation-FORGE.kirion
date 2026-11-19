"""F13 — Recovery and continuity: crash reconciliation, SQLite online backup/restore, and Sandbox Capsules."""
from __future__ import annotations

import datetime as dt
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Callable

from . import REPO_ROOT
from .authority import validate_contract
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
        """Restore a journal from a backup file and verify hash-chain integrity."""
        restored_db_path.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(backup_db_path)
        dst = sqlite3.connect(restored_db_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
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
        Detects remote branch drift during PENDING_REMOTE reconciliation and halts BLOCKED.
        """
        m = self.journal.get_mission(mission_id)
        packet = m["packet"]
        branch = packet["permitted_branch"]
        base_sha = m["base_sha"]
        candidate_sha = observed_local_sha or m["candidate_sha"]
        delivery_key = compute_delivery_key(mission_id, branch, candidate_sha)

        delivery_reconciled = False
        remote_already_delivered = False
        remote_drift_detected = False
        conn = sqlite3.connect(self.journal.db_path)
        conn.row_factory = sqlite3.Row
        try:
            table_check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='delivery_receipts'"
            ).fetchone()
            if table_check is not None:
                receipt = conn.execute(
                    "SELECT * FROM delivery_receipts WHERE delivery_key = ?",
                    (delivery_key,),
                ).fetchone()
                if receipt is not None:
                    if receipt["status"] == "DELIVERED":
                        remote_already_delivered = True
                        delivery_reconciled = True
                    elif receipt["status"] == "PENDING_REMOTE" and remote_head_probe is not None:
                        remote_sha = remote_head_probe(branch)
                        if remote_sha == candidate_sha:
                            conn.execute(
                                "UPDATE delivery_receipts SET status = 'DELIVERED' WHERE delivery_key = ?",
                                (delivery_key,),
                            )
                            conn.commit()
                            remote_already_delivered = True
                            delivery_reconciled = True
                        elif remote_sha in (None, base_sha):
                            conn.execute(
                                "UPDATE delivery_receipts SET status = 'RECONCILED_RETRY_ALLOWED' WHERE delivery_key = ?",
                                (delivery_key,),
                            )
                            conn.commit()
                            delivery_reconciled = True
                        else:
                            # Remote branch moved to an unexpected divergent SHA: fail closed!
                            remote_drift_detected = True
                            delivery_reconciled = False
        finally:
            conn.close()

        if remote_drift_detected:
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
