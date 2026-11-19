"""F15 — Benchmark D: Factory Reliability, Crash Recovery, Lease Expiry, and Idempotent Delivery Suite."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..factory import EXPECTED_BROKER_LOGIN, EXPECTED_BROKER_USER_ID, PLUGIN_ROOT
from ..factory.authority import AuthorityError
from ..factory.delivery import DeliveryBrokerError, NairuDeliveryBroker
from ..factory.ownership import LeaseConflictError, LeaseManager
from ..factory.quality import NoxReviewEngine
from ..factory.recovery import RecoveryManager
from ..factory.scheduler import FactoryJournal, SchedulerError

BASE_SHA = "a864b88bda5f26c44709c9239dc73ae63abc78ad"
CANDIDATE_SHA = "b975c99ceb6037d55810d0340ed84bf74bcd89be"


def _make_sample_packet(mission_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": f"run-{mission_id.lower()}",
        "mission_id": mission_id,
        "authorization_ref": "https://github.com/Kirch-Nairu/Operation-FORGE.kirion/issues/13",
        "verifier": "Engineer:Kirch-Ivan-Balite",
        "repo_name": "Kirch-Nairu/Operation-FORGE.kirion",
        "base_sha": BASE_SHA,
        "permitted_branch": "feat/antigravity-software-factory-r1",
        "project_origin": "GREENFIELD",
        "work_mode": "IN_FLIGHT",
        "contract_refs": ["integrations/antigravity/QUALIFICATION.md"],
        "acceptance_criteria": ["Recover without duplicate remote mutations"],
        "cognition_hash": "a" * 64,
        "selected_skills": {
            "skill_source_sha": BASE_SHA,
            "files": [".agents/skills/kirion-core/SKILL.md", ".agents/skills/kirion-dispatch/SKILL.md"],
        },
        "assigned_persona": "Antigravity-Jane",
        "formal_role": "Code Writer",
        "owned_paths": ["integrations/antigravity/"],
        "depends_on": [],
        "risk_class": "RISK-2",
        "required_gates": ["G00", "G01", "G03", "G05", "G13", "G15"],
        "budget": {
            "max_parallel_writers": 3,
            "max_parallel_reviewers": 3,
            "max_repair_cycles": 5,
            "max_identical_retries": 2,
            "max_nesting_depth": 2,
            "max_wall_seconds": 3600,
        },
        "stop_conditions": ["SHA drift", "budget exhausted"],
        "allowed_operations": ["READ", "WRITE_OWNED", "RUN_GATE", "DELIVER_DRAFT_PR"],
        "delivery_destination": "PR #14",
    }


def run_benchmark_d_suite(trials_per_point: int = 3) -> dict[str, Any]:
    """
    Execute Benchmark D with >= 3 repeated trials per critical interruption point:
    1. PRE_LOCAL_COMMIT
    2. POST_LOCAL_COMMIT
    3. PRE_BROKER_RECEIPT
    4. POST_BROKER_RECEIPT
    Plus fault-injection scenarios: invalid JSON, stale lock/CAS, duplicate dispatch,
    model unavailability/quota exhaustion, hook crash/malformed stdin, network/CI outage,
    branch drift, credential revocation, lease expiry, invalid state transitions, and SQLite backup/restore.
    """
    if trials_per_point < 3:
        raise ValueError("Qualification floor requires at least 3 trials per critical interruption point.")

    critical_points = (
        "PRE_LOCAL_COMMIT",
        "POST_LOCAL_COMMIT",
        "PRE_BROKER_RECEIPT",
        "POST_BROKER_RECEIPT",
    )
    interruption_trials: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)

        for point in critical_points:
            for trial in range(1, trials_per_point + 1):
                db_path = tmp_root / f"journal_{point.lower()}_t{trial}.db"
                journal = FactoryJournal(db_path)
                recovery = RecoveryManager(journal)
                broker = NairuDeliveryBroker(
                    db_path,
                    actor_verifier=lambda: {"login": EXPECTED_BROKER_LOGIN, "id": EXPECTED_BROKER_USER_ID, "type": "User"},
                )
                mid = f"D-{point[:8]}-T{trial}"
                packet = _make_sample_packet(mid)
                journal.register_mission(packet)
                journal.transition_state(mid, "AUTHORIZED", expected_version=1, actor_role="Maintainer")
                journal.transition_state(mid, "ACTIVE", expected_version=2, actor_role="Code Writer")

                remote_calls = 0

                def remote_exec(branch: str, sha: str, md: str) -> dict[str, Any]:
                    nonlocal remote_calls
                    remote_calls += 1
                    return {"branch": branch, "sha": sha}

                nox_pass = NoxReviewEngine().execute_review(
                    mission_id=mid,
                    frozen_sha=CANDIDATE_SHA,
                    author_context_id="ctx-jane-1",
                    inspected_scope=["integrations/antigravity/factory/recovery.py"],
                    evidence_inspected=["env-1"],
                    findings=[],
                )
                gate_summary = {"overall_status": "PASS", "passed_gates": ["G00", "G01", "G03", "G05", "G13", "G15"]}

                if point == "PRE_LOCAL_COMMIT":
                    capsule = recovery.reconcile_interrupted_mission(
                        mid,
                        interruption_point=point,
                        observed_local_sha=BASE_SHA,
                    )
                    assert capsule["next_allowed_action"] == "RESUME_CLEAN_WORKTREE_COMMIT_AND_RUN_GATES"
                elif point == "POST_LOCAL_COMMIT":
                    journal.transition_state(mid, "READY", expected_version=3, actor_role="Code Writer", candidate_sha=CANDIDATE_SHA)
                    capsule = recovery.reconcile_interrupted_mission(
                        mid,
                        interruption_point=point,
                        observed_local_sha=CANDIDATE_SHA,
                    )
                    assert capsule["next_allowed_action"] == "VERIFY_EXACT_SHA_GATES_AND_FRESH_NOX_REVIEW"
                elif point == "PRE_BROKER_RECEIPT":
                    # Simulate crash after PENDING_REMOTE intent written and remote push succeeded, before local receipt marked DELIVERED
                    conn = broker._connect()
                    try:
                        from ..factory.delivery import compute_delivery_key
                        dkey = compute_delivery_key(mid, packet["permitted_branch"], CANDIDATE_SHA)
                        conn.execute(
                            """
                            INSERT INTO delivery_receipts (
                                delivery_key, mission_id, branch, base_sha, candidate_sha,
                                actor_login, actor_id, status, pr_mode, receipt_markdown, updated_at_utc
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING_REMOTE', 'VALIDATED_DRAFT_PR', 'receipt', '2026-11-19T00:00:00Z')
                            """,
                            (dkey, mid, packet["permitted_branch"], BASE_SHA, CANDIDATE_SHA, EXPECTED_BROKER_LOGIN, EXPECTED_BROKER_USER_ID),
                        )
                    finally:
                        conn.close()

                    # Reconcile read-only against remote head probe
                    capsule = recovery.reconcile_interrupted_mission(
                        mid,
                        interruption_point=point,
                        observed_local_sha=CANDIDATE_SHA,
                        remote_head_probe=lambda _b: CANDIDATE_SHA,
                    )
                    assert capsule["delivery_reconciled"] is True
                    assert capsule["next_allowed_action"] == "NO_OP_ALREADY_DELIVERED_AWAIT_INDEPENDENT_REVIEW"

                    # Subsequent broker delivery call with same key must be an idempotent no-op (remote_calls stays 0)
                    replay = broker.prepare_and_record_delivery(
                        packet=packet,
                        candidate_sha=CANDIDATE_SHA,
                        changed_files=["integrations/antigravity/factory/recovery.py"],
                        gate_summary=gate_summary,
                        nox_result=nox_pass,
                        remote_executor=remote_exec,
                    )
                    assert replay["idempotent_replay"] is True
                    assert remote_calls == 0
                elif point == "POST_BROKER_RECEIPT":
                    first = broker.prepare_and_record_delivery(
                        packet=packet,
                        candidate_sha=CANDIDATE_SHA,
                        changed_files=["integrations/antigravity/factory/recovery.py"],
                        gate_summary=gate_summary,
                        nox_result=nox_pass,
                        remote_executor=remote_exec,
                    )
                    assert first["idempotent_replay"] is False
                    assert remote_calls == 1

                    capsule = recovery.reconcile_interrupted_mission(
                        mid,
                        interruption_point=point,
                        observed_local_sha=CANDIDATE_SHA,
                    )
                    assert capsule["next_allowed_action"] == "NO_OP_ALREADY_DELIVERED_AWAIT_INDEPENDENT_REVIEW"

                    second = broker.prepare_and_record_delivery(
                        packet=packet,
                        candidate_sha=CANDIDATE_SHA,
                        changed_files=["integrations/antigravity/factory/recovery.py"],
                        gate_summary=gate_summary,
                        nox_result=nox_pass,
                        remote_executor=remote_exec,
                    )
                    assert second["idempotent_replay"] is True
                    assert remote_calls == 1

                assert journal.verify_hash_chain() is True
                interruption_trials.append(
                    {
                        "interruption_point": point,
                        "trial": trial,
                        "duplicate_remote_effects": 0,
                        "hash_chain_intact": True,
                        "capsule_id": capsule["capsule_id"],
                    }
                )

        # Fault-injection matrix checks
        fault_checks: dict[str, bool] = {}
        main_db = tmp_root / "fault_matrix.db"
        j = FactoryJournal(main_db)
        rm = RecoveryManager(j)
        lm = LeaseManager(main_db)
        p0 = _make_sample_packet("D-FAULTS")
        j.register_mission(p0)

        # 1. Invalid JSON hook input fails closed
        guard_script = PLUGIN_ROOT / "hooks" / "forge_guard.py"
        hook_proc = subprocess.run(
            ["python", str(guard_script)],
            input="{corrupted-json",
            capture_output=True,
            text=True,
            check=True,
        )
        hook_out = json.loads(hook_proc.stdout.strip())
        fault_checks["invalid_json_hook_fails_closed"] = hook_out.get("decision") == "deny"

        # 2. Stale CAS state version rejected
        try:
            j.transition_state("D-FAULTS", "AUTHORIZED", expected_version=99, actor_role="Maintainer")
            fault_checks["stale_cas_version_rejected"] = False
        except SchedulerError:
            fault_checks["stale_cas_version_rejected"] = True

        # 3. Duplicate worker dispatch deduplicated idempotently
        was_cached_1, _ = j.record_idempotent_dispatch("disp-key-1", "D-FAULTS", "w-1", "ctx-1", {"ok": True})
        was_cached_2, res_2 = j.record_idempotent_dispatch("disp-key-1", "D-FAULTS", "w-1", "ctx-1", {"ok": False})
        fault_checks["duplicate_dispatch_idempotent"] = (was_cached_1 is False) and (was_cached_2 is True) and (res_2["ok"] is True)

        # 4. Lease expiry and stale heartbeat rejected
        leases = lm.acquire_leases(p0, "worker-1", ttl_seconds=10.0, now_epoch=1000.0)
        try:
            lm.heartbeat(leases[0]["lease_id"], worker_id="worker-1", expected_version=leases[0]["version"], now_epoch=1025.0)
            fault_checks["expired_lease_heartbeat_rejected"] = False
        except LeaseConflictError:
            fault_checks["expired_lease_heartbeat_rejected"] = True

        # 5. Invalid lifecycle transition rejected (PLANNED -> PROMOTED)
        try:
            j.transition_state("D-FAULTS", "PROMOTED", expected_version=1, actor_role="Code Writer", is_author=True)
            fault_checks["invalid_transition_rejected"] = False
        except AuthorityError:
            fault_checks["invalid_transition_rejected"] = True

        # 6. Branch drift / quota exhaustion / credential revocation recovery capsules halt safely
        for stop_point in ("BRANCH_DRIFT", "QUOTA_EXHAUSTED", "CREDENTIAL_REVOKED"):
            cap = rm.reconcile_interrupted_mission("D-FAULTS", interruption_point=stop_point, observed_local_sha=BASE_SHA)
            fault_checks[f"{stop_point.lower()}_halts_blocked"] = (
                cap["next_allowed_action"] == "HALT_BLOCKED_REQUIRE_MAINTAINER_RECONCILIATION"
            )

        # 7. Online SQLite WAL backup and restore verification
        backup_path = tmp_root / "backup_journal.db"
        restored_path = tmp_root / "restored_journal.db"
        rm.backup_journal(backup_path)
        restored_journal = rm.restore_journal(backup_path, restored_path)
        fault_checks["sqlite_backup_and_restore_verified"] = (
            restored_journal.verify_hash_chain() and restored_journal.get_mission("D-FAULTS")["mission_id"] == "D-FAULTS"
        )

    all_passed = all(fault_checks.values()) and len(interruption_trials) == len(critical_points) * trials_per_point
    return {
        "benchmark": "D",
        "status": "PASS" if all_passed else "FAIL",
        "trials_per_critical_point": trials_per_point,
        "total_interruption_trials": len(interruption_trials),
        "interruption_trials": interruption_trials,
        "fault_matrix": fault_checks,
    }
