"""Comprehensive unit and integration test suite for F00–F14 KIRION Forge Antigravity Factory modules."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from integrations.antigravity.factory import (
    ANTIGRAVITY_ROOT,
    EXPECTED_BROKER_LOGIN,
    EXPECTED_BROKER_USER_ID,
    PLUGIN_ROOT,
    PROFILES_ROOT,
    REPO_ROOT,
)
from integrations.antigravity.factory.authority import (
    AuthorityError,
    validate_contract,
    validate_lifecycle_transition,
    verify_git_authority,
    verify_mission_packet,
)
from integrations.antigravity.factory.delivery import (
    DeliveryBrokerError,
    NairuDeliveryBroker,
)
from integrations.antigravity.factory.dispatcher import (
    EXPECTED_FLEET_AGENTS,
    EXPECTED_PLUGIN_SPECIALIZATION_SKILLS,
    FleetDispatcher,
    query_live_host_plugin_discovery,
    select_skills_for_mission,
    verify_plugin_package,
)
from integrations.antigravity.factory.evidence import (
    TrustedEvidenceRunner,
    redact_secrets,
    translate_harness_capabilities_to_forge,
)
from integrations.antigravity.factory.knowledge import KnowledgeManager
from integrations.antigravity.factory.ownership import (
    LeaseConflictError,
    LeaseManager,
    WorktreeSandbox,
    assert_canonical_path_inside_worktree,
    sanitize_worker_env,
)
from integrations.antigravity.factory.policy import (
    PolicyViolationError,
    assert_operation_allowed,
    assert_paths_within_ownership,
)
from integrations.antigravity.factory.quality import (
    RISK_REQUIRED_GATES,
    NoxReviewEngine,
    QualityGateError,
    SelfHealingController,
    evaluate_gate_suite,
)
from integrations.antigravity.factory.recovery import RecoveryManager
from integrations.antigravity.factory.scheduler import (
    FactoryJournal,
    SchedulerError,
    build_topological_waves,
    detect_parallel_collisions,
    enforce_wave_budget,
)

BASE_SHA = "a864b88bda5f26c44709c9239dc73ae63abc78ad"
SKILL_REGISTRY_SHA = "05da5f962c87e5ab7cc4b956ecbbb2d4e8a0de2b"
NEXT_SHA = "d222222222222222222222222222222222222222"


def make_valid_packet(
    mission_id: str = "F06-TEST",
    persona: str = "Antigravity-Jane",
    formal_role: str = "Code Writer",
    owned_paths: list[str] | None = None,
    depends_on: list[str] | None = None,
) -> dict:
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
        "contract_refs": ["integrations/antigravity/ARCHITECTURE.md"],
        "acceptance_criteria": ["All gates pass"],
        "cognition_hash": "c" * 64,
        "selected_skills": {
            "skill_source_sha": BASE_SHA,
            "files": [".agents/skills/kirion-core/SKILL.md", ".agents/skills/kirion-dispatch/SKILL.md"],
        },
        "assigned_persona": persona,
        "formal_role": formal_role,
        "owned_paths": owned_paths or ["integrations/antigravity/factory/"],
        "depends_on": depends_on or [],
        "risk_class": "RISK-2",
        "required_gates": list(RISK_REQUIRED_GATES["RISK-2"]),
        "budget": {
            "max_parallel_writers": 3,
            "max_parallel_reviewers": 3,
            "max_repair_cycles": 5,
            "max_identical_retries": 2,
            "max_nesting_depth": 2,
            "max_wall_seconds": 1800,
        },
        "stop_conditions": ["SHA drift"],
        "allowed_operations": ["READ", "WRITE_OWNED", "RUN_GATE", "DELIVER_DRAFT_PR"]
        if formal_role != "Reviewer"
        else ["READ", "REVIEW_READONLY"],
        "delivery_destination": "PR #14",
    }


def _make_clean_git_repo(parent_dir: Path) -> Path:
    repo = parent_dir / "clean_repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Kirch-Nairu"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "nairu@example.com"], cwd=repo, capture_output=True, check=True)
    (repo / "README.md").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
    return repo


class FactoryCoreTests(unittest.TestCase):
    def test_f01_plugin_packaging_and_live_discovery(self) -> None:
        pkg = verify_plugin_package(PLUGIN_ROOT, REPO_ROOT)
        self.assertEqual(pkg["name"], "kirion-forge")
        self.assertEqual(pkg["agents_count"], 10)
        self.assertEqual(pkg["plugin_skills_count"], 16)
        self.assertEqual(pkg["core_skills_count"], 16)
        self.assertEqual(pkg["total_candidate_skills"], 32)
        self.assertTrue(pkg["hooks_present"])
        qual_report = (ANTIGRAVITY_ROOT / "QUALIFICATION_REPORT.md").read_text(encoding="utf-8")
        self.assertIn(pkg["package_sha256"], qual_report, "QUALIFICATION_REPORT.md must record exact current package_sha256")

        live = query_live_host_plugin_discovery(REPO_ROOT)
        if live["status"] == "OBSERVED":
            self.assertEqual(live["name"], "kirion-forge")
            self.assertFalse(live["isGlobal"])
            self.assertEqual(live["skills_count"], 16)
            self.assertEqual(live["agents_count"], 10)
            self.assertTrue(live["hooks_loaded"])

    def test_f02_fleet_dispatcher_and_progressive_skill_selection(self) -> None:
        dispatcher = FleetDispatcher(REPO_ROOT)
        for slug, persona in EXPECTED_FLEET_AGENTS.items():
            role = "Reviewer" if persona in ("Antigravity-Nox", "Antigravity-Aegis") else (
                "Maintainer" if persona == "Antigravity-Maintainer" else (
                    "Integration Writer" if persona == "Antigravity-Integrator" else "Code Writer"
                )
            )
            ctx = dispatcher.create_isolated_context(persona, role)
            self.assertEqual(ctx["persona"], persona)
            self.assertEqual(ctx["agent_slug"], slug)

        # Spoofed persona or mismatched role must fail closed
        with self.assertRaises(PolicyViolationError):
            dispatcher.create_isolated_context("Antigravity-Fake", "Code Writer")
        with self.assertRaises(PolicyViolationError):
            dispatcher.create_isolated_context("Antigravity-Nox", "Code Writer")

        # Progressive skill selector caps at <= 8 files and resolves both core and plugin skills
        csharp_bundle = select_skills_for_mission("csharp_aspnet", skill_source_sha=SKILL_REGISTRY_SHA)
        self.assertLessEqual(len(csharp_bundle["files"]), 8)
        self.assertIn(".agents/skills/kirion-core/SKILL.md", csharp_bundle["files"])
        self.assertIn("integrations/antigravity/plugins/kirion-forge/skills/kirion-csharp/SKILL.md", csharp_bundle["files"])

    def test_f03_f04_f05_profiles_and_32_skill_catalog(self) -> None:
        for profile_name in ("csharp_aspnet.json", "php_laravel.json", "salryn_high_integrity.json", "frontend_web.json"):
            p = PROFILES_ROOT / profile_name
            self.assertTrue(p.is_file(), f"Missing profile: {profile_name}")
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertIn("required_skills", data)
            self.assertIn("invariants", data)

        self.assertEqual(len(EXPECTED_PLUGIN_SPECIALIZATION_SKILLS), 16)

    def test_f06_mission_authority_and_lifecycle_transitions(self) -> None:
        pkt = make_valid_packet()
        verify_mission_packet(pkt, expected_repo="Kirch-Nairu/Operation-FORGE.kirion", observed_base_sha=BASE_SHA)

        # Malformed SHA, untrusted verifier, main branch, and wildcard owned_paths must be rejected
        with self.assertRaises(AuthorityError):
            verify_mission_packet({**pkt, "base_sha": "short-sha"})
        with self.assertRaises(AuthorityError):
            verify_mission_packet({**pkt, "verifier": "Untrusted:Mallory"})
        with self.assertRaises(AuthorityError):
            verify_mission_packet({**pkt, "permitted_branch": "main"})
        with self.assertRaises(AuthorityError):
            verify_mission_packet({**pkt, "owned_paths": ["*"]})

        # Valid lifecycle path
        self.assertEqual(validate_lifecycle_transition("PLANNED", "AUTHORIZED", actor_role="Maintainer"), "AUTHORIZED")
        self.assertEqual(validate_lifecycle_transition("AUTHORIZED", "ACTIVE", actor_role="Code Writer"), "ACTIVE")
        self.assertEqual(validate_lifecycle_transition("ACTIVE", "READY", actor_role="Code Writer"), "READY")
        self.assertEqual(validate_lifecycle_transition("READY", "UNDER_REVIEW", actor_role="Maintainer"), "UNDER_REVIEW")
        self.assertEqual(
            validate_lifecycle_transition("UNDER_REVIEW", "ACCEPTED", actor_role="Acceptance Agent", is_author=False),
            "ACCEPTED",
        )

        # Author self-acceptance must fail
        with self.assertRaises(AuthorityError):
            validate_lifecycle_transition("UNDER_REVIEW", "ACCEPTED", actor_role="Acceptance Agent", is_author=True)

    def test_f07_dag_scheduler_backlog_and_journal(self) -> None:
        backlog = json.loads((ANTIGRAVITY_ROOT / "BACKLOG.json").read_text(encoding="utf-8"))
        waves = build_topological_waves(backlog["missions"])
        self.assertEqual(waves[0], ["F00"])
        self.assertIn("F01", waves[1])
        self.assertIn("F06", waves[1])
        self.assertEqual(waves[-1], ["F17"])

        # Cycle detection
        with self.assertRaises(SchedulerError):
            build_topological_waves([{"id": "A", "depends_on": ["B"]}, {"id": "B", "depends_on": ["A"]}])

        # Parallel collision detection
        p1 = make_valid_packet("M1", owned_paths=["integrations/antigravity/factory/"])
        p2 = make_valid_packet("M2", owned_paths=["integrations/antigravity/factory/policy.py"])
        self.assertTrue(len(detect_parallel_collisions([p1, p2])) > 0)
        with self.assertRaises(SchedulerError):
            enforce_wave_budget([p1, p2])

        # SQLite WAL journal + CAS
        with tempfile.TemporaryDirectory() as tmp:
            j = FactoryJournal(Path(tmp) / "test_journal.db")
            state = j.register_mission(p1)
            self.assertEqual(state["state"], "PLANNED")
            self.assertEqual(state["state_version"], 1)
            s2 = j.transition_state("M1", "AUTHORIZED", expected_version=1, actor_role="Maintainer")
            self.assertEqual(s2["state"], "AUTHORIZED")
            self.assertEqual(s2["state_version"], 2)
            self.assertTrue(j.verify_hash_chain())

    def test_f08_worktree_sandbox_and_leases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            lm = LeaseManager(tmp_root / "leases.db")
            p1 = make_valid_packet("L1", owned_paths=["src/module_a/"])
            p2 = make_valid_packet("L2", owned_paths=["src/module_a/sub/"])
            p3 = make_valid_packet("L3", owned_paths=["src/module_b/"])

            acquired_1 = lm.acquire_leases(p1, "worker-1", ttl_seconds=60.0, now_epoch=100.0)
            self.assertEqual(len(acquired_1), 1)
            with self.assertRaises(LeaseConflictError):
                lm.acquire_leases(p2, "worker-2", ttl_seconds=60.0, now_epoch=110.0)
            acquired_3 = lm.acquire_leases(p3, "worker-2", ttl_seconds=60.0, now_epoch=110.0)
            self.assertEqual(len(acquired_3), 1)

            # Real git worktree isolation test in disposable repo
            repo_dir = tmp_root / "disp_repo"
            repo_dir.mkdir()
            subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True, check=True)
            subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=repo_dir, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.name", "Kirch-Nairu"], cwd=repo_dir, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.email", "nairu@example.com"], cwd=repo_dir, capture_output=True, check=True)
            (repo_dir / "README.md").write_text("init\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo_dir, capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, capture_output=True, check=True)
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True, check=True).stdout.strip()

            sandbox = WorktreeSandbox(repo_dir, tmp_root / "worktrees")
            wt = sandbox.create_worktree("feat/lane-1", sha, "wt_1")
            try:
                (wt / "src" / "module_a").mkdir(parents=True)
                (wt / "src" / "module_a" / "code.py").write_text("x = 1\n", encoding="utf-8")
                changed = sandbox.inspect_and_validate_worktree(wt, {**p1, "base_sha": sha}, base_sha=sha)
                self.assertEqual(changed, ["src/module_a/code.py"])

                # Out-of-scope file must fail
                (wt / "unowned.txt").write_text("bad\n", encoding="utf-8")
                with self.assertRaises(PolicyViolationError):
                    sandbox.inspect_and_validate_worktree(wt, {**p1, "base_sha": sha}, base_sha=sha)
            finally:
                sandbox.remove_worktree(wt)

    def test_f09_f10_f11_f12_f13_f14_end_to_end_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            clean_repo = _make_clean_git_repo(tmp_root)
            runner = TrustedEvidenceRunner(tmp_root / "artifacts")
            env = runner.run_gate_command(
                run_id="run-e2e",
                mission_id="F10-TEST",
                stage="VERIFY",
                gate_id="G05",
                command_argv=[sys.executable, "-c", "print('unit pass; token ghp_1234567890abcdefghijklmnop')"],
                cwd=clean_repo,
                evidence_type="UNIT",
            )
            self.assertEqual(env["status"], "PASS")
            self.assertEqual(env["evidence_level"], "E4")
            artifact_text = Path(env["artifact_path"]).read_text(encoding="utf-8")
            self.assertNotIn("ghp_1234567890", artifact_text)
            self.assertIn("[REDACTED_SECRET]", artifact_text)

            # Knowledge manager crosswalk & lesson proposal
            km = KnowledgeManager(tmp_root / "knowledge")
            cw = km.build_crosswalk_record(
                mission_id="F14-TEST",
                run_id="run-e2e",
                context_sha256="d" * 64,
                candidate_sha=BASE_SHA,
                harness_capabilities={"IMPLEMENTED", "TESTED", "OBSERVED", "DURABLE"},
                has_automated_provenance=True,
            )
            self.assertEqual(cw["forge_evidence_level"], "E5")
            self.assertEqual(cw["brain_certainty_state"], "VERIFIED")

            proposal = km.propose_skill_or_test_lesson(
                mission_id="F14-TEST",
                observed_sha=BASE_SHA,
                failure_signature="SIG-PDO-SQLITE",
                root_cause="Windows PHP CLI requires explicit extension_dir for pdo_sqlite when not enabled in php.ini",
                target_skill_name="kirion-laravel-runtime",
                proposed_guidance="Pass -d extension_dir=<ext> -d extension=pdo_sqlite on Windows CLI invocations.",
                discriminating_test_name="test_windows_pdo_sqlite_dynamic_load",
            )
            self.assertEqual(proposal["status"], "PROPOSED_REVIEW_ONLY_NOT_ADOPTED")
            self.assertFalse(proposal["auto_policy_elevation"])
            self.assertTrue(Path(proposal["proposal_path"]).is_file())

            km.record_instrumented_run(
                run_id="run-e2e",
                mission_id="F14-TEST",
                first_pass_valid=True,
                repair_cycles=0,
                escaped_defects=0,
                human_interventions=0,
                lead_time_seconds=4.25,
                recovered_from_interruption=True,
                evidence_hashes_valid=True,
            )
            metrics = km.summarize_metrics()
            self.assertEqual(metrics["instrumented_runs"], 1)
            self.assertEqual(metrics["first_pass_validation_rate"], 1.0)
            self.assertEqual(metrics["evidence_integrity_rate"], 1.0)

    def test_nox_cycle2_security_and_governance_regressions(self) -> None:
        """Discriminating regression tests for NOX-R2-001..011 findings."""
        # NOX-R2-001: evaluate_gate_suite rejects E0/ASSUMED/dirty/nonzero-exit PASS and mandatory exemptions
        bad_env = {
            "schema_version": 1,
            "run_id": "run-r2",
            "mission_id": "R2-TEST",
            "stage": "VERIFY",
            "gate_id": "G03",
            "candidate_sha": BASE_SHA,
            "tree_sha": BASE_SHA,
            "dirty": True,
            "command_argv": ["dotnet", "build"],
            "cwd": ".",
            "started_at_utc": "2026-11-19T00:00:00Z",
            "completed_at_utc": "2026-11-19T00:00:01Z",
            "exit_code": 1,
            "status": "PASS",
            "environment_versions": {"python": "3.13.5"},
            "fixture_sha256": "0" * 64,
            "artifact_path": "a.log",
            "artifact_size_bytes": 1,
            "artifact_sha256": "a" * 64,
            "evidence_level": "E0",
            "evidence_type": "NONE",
            "provenance": "ASSUMED",
            "certainty_ceiling": "HYPOTHESIS",
            "redacted": True,
        }
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite("RISK-1", [bad_env], candidate_sha=BASE_SHA)
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite("RISK-1", [{**bad_env, "dirty": False, "exit_code": 0}], candidate_sha=BASE_SHA)
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite("RISK-1", [], candidate_sha=BASE_SHA, non_applicable_gates={"G00": "skip"})
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite("RISK-1", [], candidate_sha=BASE_SHA, non_applicable_gates={"G03": "   "})

        # NOX-R2-002: TrustedEvidenceRunner never coerces BUILD to RUNTIME when is_runtime_gate=True
        with tempfile.TemporaryDirectory() as tmp:
            clean_repo = _make_clean_git_repo(Path(tmp))
            runner = TrustedEvidenceRunner(Path(tmp) / "artifacts")
            env_b = runner.run_gate_command(
                run_id="run-r2",
                mission_id="R2-TEST",
                stage="VERIFY",
                gate_id="G10",
                command_argv=[sys.executable, "-c", "print('ok')"],
                cwd=clean_repo,
                evidence_type="BUILD",
                is_runtime_gate=True,
            )
            self.assertEqual(env_b["evidence_type"], "BUILD")
            self.assertEqual(env_b["evidence_level"], "E4")
            with self.assertRaises(QualityGateError):
                evaluate_gate_suite("RISK-2", [env_b], candidate_sha=env_b["candidate_sha"])

        # NOX-R2-003: Forged NoxResult claiming verdict='PASS' with OPEN P0/P1/P2 fails closed
        nox = NoxReviewEngine()
        for sev in ("P0", "P1", "P2"):
            forged = {
                "schema_version": 1,
                "mission_id": "R2-TEST",
                "frozen_sha": BASE_SHA,
                "reviewer_context_id": "ctx-nox-r2",
                "reviewer_persona": "Antigravity-Nox",
                "author_context_id": "ctx-jane-r2",
                "inspected_scope": ["integrations/antigravity/"],
                "evidence_inspected": ["env-1"],
                "findings": [
                    {
                        "id": f"F-{sev}",
                        "severity": sev,
                        "path": "integrations/antigravity/factory/quality.py",
                        "line": 1,
                        "contract_violated": "Test violation",
                        "reproduction": "Repro",
                        "requested_correction": "Fix",
                        "disposition": "OPEN",
                    }
                ],
                "verdict": "PASS",
            }
            with self.assertRaises(QualityGateError):
                nox.assert_review_valid_for_sha(forged, BASE_SHA)

        # NOX-R2-005: Trailing newline SHA, protected refspec branches, overbroad owned_paths, mismatched persona/role
        base_pkt = make_valid_packet()
        with self.assertRaises(AuthorityError):
            verify_mission_packet({**base_pkt, "base_sha": BASE_SHA + "\n"})
        for bad_branch in ("MAIN", "refs/heads/main", "refs/heads/master", "origin/main", "production", "release"):
            with self.assertRaises(AuthorityError):
                verify_mission_packet({**base_pkt, "permitted_branch": bad_branch})
        for bad_path in ("./", "/etc/passwd", "C:/Windows", "AGENTS.md", "src/**"):
            with self.assertRaises(AuthorityError):
                verify_mission_packet({**base_pkt, "owned_paths": [bad_path]})
        with self.assertRaises(AuthorityError):
            verify_mission_packet({**base_pkt, "assigned_persona": "Antigravity-Jane", "formal_role": "Maintainer"})
        with self.assertRaises(AuthorityError):
            verify_mission_packet({**base_pkt, "assigned_persona": "Antigravity-Maintainer", "formal_role": "Code Writer"})

        # NOX-R2-006 & NOX-R2-011: PENDING_REMOTE fails closed on re-delivery; remote drift halts BLOCKED; canonical Sandbox Capsule export
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "r2_recovery.db"
            journal = FactoryJournal(db)
            recovery = RecoveryManager(journal)
            broker = NairuDeliveryBroker(
                db,
                actor_verifier=lambda: {"login": EXPECTED_BROKER_LOGIN, "id": EXPECTED_BROKER_USER_ID, "type": "User"},
            )
            journal.register_mission(base_pkt)
            from integrations.antigravity.factory.delivery import compute_delivery_key
            dkey = compute_delivery_key(base_pkt["mission_id"], base_pkt["permitted_branch"], NEXT_SHA)
            conn = broker._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO delivery_receipts (
                        delivery_key, mission_id, branch, base_sha, candidate_sha,
                        actor_login, actor_id, status, pr_mode, receipt_markdown, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING_REMOTE', 'VALIDATED_DRAFT_PR', 'md', '2026-11-19T00:00:00Z')
                    """,
                    (dkey, base_pkt["mission_id"], base_pkt["permitted_branch"], BASE_SHA, NEXT_SHA, EXPECTED_BROKER_LOGIN, EXPECTED_BROKER_USER_ID),
                )
            finally:
                conn.close()

            nox_ok = nox.execute_review(
                mission_id=base_pkt["mission_id"],
                frozen_sha=NEXT_SHA,
                author_context_id="ctx-jane",
                inspected_scope=["integrations/antigravity/factory/"],
                evidence_inspected=["env-1"],
                findings=[],
            )
            # Re-calling broker while PENDING_REMOTE must fail closed without calling remote_executor
            with self.assertRaisesRegex(DeliveryBrokerError, "PENDING_REMOTE"):
                broker.prepare_and_record_delivery(
                    packet=base_pkt,
                    candidate_sha=NEXT_SHA,
                    changed_files=["integrations/antigravity/factory/policy.py"],
                    gate_summary={
                        "risk_class": base_pkt["risk_class"],
                        "candidate_sha": NEXT_SHA,
                        "overall_status": "PASS",
                        "passed_gates": list(RISK_REQUIRED_GATES[base_pkt["risk_class"]]),
                        "failed_gates": [],
                        "missing_gates": [],
                        "not_run_gates": [],
                    },
                    nox_result=nox_ok,
                )

            # Divergent remote SHA during PENDING_REMOTE reconciliation must halt BLOCKED
            divergent_sha = "f" * 40
            drift_cap = recovery.reconcile_interrupted_mission(
                base_pkt["mission_id"],
                interruption_point="PRE_BROKER_RECEIPT",
                observed_local_sha=NEXT_SHA,
                remote_head_probe=lambda _b: divergent_sha,
            )
            self.assertFalse(drift_cap["delivery_reconciled"])
            self.assertEqual(drift_cap["next_allowed_action"], "HALT_BLOCKED_REQUIRE_MAINTAINER_RECONCILIATION")

            # Canonical schemas/sandbox-capsule.schema.json export validates strictly
            canonical_cap = recovery.export_canonical_forge_sandbox_capsule(drift_cap)
            self.assertEqual(canonical_cap["capsule_version"], 1)
            self.assertEqual(canonical_cap["next_permitted_action"], "HALT_BLOCKED_REQUIRE_MAINTAINER_RECONCILIATION")

        # NOX-R2-007: Worktree traversal name and prohibited branch rejected before rmtree
        with tempfile.TemporaryDirectory() as tmp:
            sb = WorktreeSandbox(REPO_ROOT, Path(tmp) / "sandboxes")
            with self.assertRaises(PolicyViolationError):
                sb.create_worktree("feat/ok", BASE_SHA, "../escape")
            with self.assertRaises(PolicyViolationError):
                sb.create_worktree("main", BASE_SHA, "valid_lane")

        # NOX-R2-008: Workflow scripts synchronize with canonical JSON Schema contracts
        nox_wf_src = (ANTIGRAVITY_ROOT / "workflows" / "nox_adversarial_audit.py").read_text(encoding="utf-8")
        feat_wf_src = (ANTIGRAVITY_ROOT / "workflows" / "feature_delivery.py").read_text(encoding="utf-8")
        self.assertIn("nox-result.schema.json", nox_wf_src)
        self.assertIn("writer-result.schema.json", feat_wf_src)
        self.assertIn("nox-result.schema.json", feat_wf_src)
        self.assertIn('writer_res["final_sha"]', feat_wf_src)
        self.assertNotIn('type_name="research",\n    workspace=', feat_wf_src)

        # NOX-R2-009: verify_plugin_package rejects malformed or missing-entry .agents/plugins.json and ignores __pycache__
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = Path(tmp) / "repo"
            (fake_repo / ".agents").mkdir(parents=True)
            (fake_repo / ".agents" / "plugins.json").write_text('{"entries": [{"path": "wrong/dir"}]}', encoding="utf-8")
            with self.assertRaises(AuthorityError):
                verify_plugin_package(PLUGIN_ROOT, fake_repo)
            (fake_repo / ".agents" / "plugins.json").write_text("{broken-json", encoding="utf-8")
            with self.assertRaises(AuthorityError):
                verify_plugin_package(PLUGIN_ROOT, fake_repo)

    def test_nox_cycle3_security_and_governance_regressions(self) -> None:
        """Discriminating regression tests for NOX-R3-001..010 findings."""
        from integrations.antigravity.factory.policy import is_prohibited_branch

        # NOX-R3-001: inspect_and_validate_worktree fails closed on invalid base_sha
        with tempfile.TemporaryDirectory() as tmp:
            sb = WorktreeSandbox(REPO_ROOT, Path(tmp) / "wts")
            wt = sb.create_worktree("feat/r3-invalid-sha", BASE_SHA, "wt_r3")
            try:
                with self.assertRaises(AuthorityError):
                    sb.inspect_and_validate_worktree(wt, make_valid_packet(), base_sha="deadbeef" * 5)
            finally:
                sb.remove_worktree(wt)

        # NOX-R3-002: Delivery broker rejects mismatched gate_summary SHA/risk/missing gates, mismatched Nox mission_id, and PAUSED delivery
        base_pkt = make_valid_packet("R3-MISSION-B")
        with self.assertRaises(AuthorityError):
            verify_mission_packet({**base_pkt, "work_mode": "PAUSED", "allowed_operations": ["READ", "DELIVER_DRAFT_PR"]})

        nox = NoxReviewEngine()
        wrong_mission_nox = nox.execute_review(
            mission_id="R3-MISSION-A",
            frozen_sha=NEXT_SHA,
            author_context_id="ctx-jane",
            inspected_scope=["integrations/antigravity/factory/"],
            evidence_inspected=["env-1"],
            findings=[],
        )
        with tempfile.TemporaryDirectory() as tmp:
            broker = NairuDeliveryBroker(
                Path(tmp) / "b.db",
                actor_verifier=lambda: {"login": EXPECTED_BROKER_LOGIN, "id": EXPECTED_BROKER_USER_ID, "type": "User"},
            )
            # Stale/mismatched gate summary rejected
            with self.assertRaises(DeliveryBrokerError):
                broker.prepare_and_record_delivery(
                    packet=base_pkt,
                    candidate_sha=NEXT_SHA,
                    changed_files=["integrations/antigravity/factory/policy.py"],
                    gate_summary={
                        "risk_class": "RISK-0",
                        "candidate_sha": BASE_SHA,
                        "overall_status": "PASS",
                        "passed_gates": ["G00"],
                        "failed_gates": ["G08"],
                        "missing_gates": ["G10"],
                    },
                    nox_result=wrong_mission_nox,
                )
            # Mismatched Nox mission_id rejected even when gate summary matches
            with self.assertRaises(QualityGateError):
                broker.prepare_and_record_delivery(
                    packet=base_pkt,
                    candidate_sha=NEXT_SHA,
                    changed_files=["integrations/antigravity/factory/policy.py"],
                    gate_summary={
                        "risk_class": base_pkt["risk_class"],
                        "candidate_sha": NEXT_SHA,
                        "overall_status": "PASS",
                        "passed_gates": base_pkt["required_gates"],
                        "failed_gates": [],
                        "missing_gates": [],
                        "not_run_gates": [],
                    },
                    nox_result=wrong_mission_nox,
                )

        # NOX-R3-003: SelfHealingController enforces Nox SHA/context/P0 invariants, fail-closed regression_failed_prefix, and valid distinct new_sha
        healer = SelfHealingController(max_repair_cycles=2, max_identical_retries=2)
        forged_p0 = {
            "schema_version": 1,
            "mission_id": "R3-HEAL",
            "frozen_sha": NEXT_SHA,
            "reviewer_context_id": "ctx-nox-distinct",
            "reviewer_persona": "Antigravity-Nox",
            "author_context_id": "ctx-author-1",
            "inspected_scope": ["integrations/antigravity/factory/quality.py"],
            "evidence_inspected": ["env-1"],
            "findings": [
                {
                    "id": "P0-LIVE",
                    "severity": "P0",
                    "path": "integrations/antigravity/factory/quality.py",
                    "line": 1,
                    "contract_violated": "Critical flaw",
                    "reproduction": "Repro",
                    "requested_correction": "Fix",
                    "disposition": "OPEN",
                }
            ],
            "verdict": "PASS",
        }
        res_forged_p0 = healer.run_repair_loop(
            initial_sha=NEXT_SHA,
            evaluate_fn=lambda _s: {"passed": True, "author_context_id": "ctx-author-1"},
            repair_fn=lambda _c, _fc, _e: {"new_sha": BASE_SHA, "regression_failed_prefix": True},
            nox_review_fn=lambda _s, _a: forged_p0,
        )
        self.assertEqual(res_forged_p0["status"], "QUARANTINED")

        # Missing regression_failed_prefix fails closed (BLOCKED)
        res_no_reg = healer.run_repair_loop(
            initial_sha=NEXT_SHA,
            evaluate_fn=lambda _s: {"passed": False, "failure_output": "unit failed", "author_context_id": "ctx-author-1"},
            repair_fn=lambda _c, _fc, _e: {"new_sha": BASE_SHA},
            nox_review_fn=lambda _s, _a: forged_p0,
        )
        self.assertEqual(res_no_reg["status"], "BLOCKED")

        # NOX-R3-005 & NOX-R3-006: G08 SECURITY -> E5 passes evaluate_gate_suite; dirty tree downgrades to E2; UNIT on G07 / certainty inflation rejected; G10 NOT_RUN -> BLOCKED cleanly
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            clean_repo = _make_clean_git_repo(tmp_root)
            runner = TrustedEvidenceRunner(tmp_root / "arts")
            g08_env = runner.run_gate_command(
                run_id="run-r3",
                mission_id="R3-SEC",
                stage="VERIFY",
                gate_id="G08",
                command_argv=[sys.executable, "-c", "print('sec ok')"],
                cwd=clean_repo,
                evidence_type="SECURITY",
                is_runtime_gate=True,
            )
            self.assertFalse(g08_env["dirty"])
            self.assertEqual(g08_env["evidence_level"], "E5")
            self.assertEqual(g08_env["provenance"], "DIRECTLY_OBSERVED")
            ev_res = evaluate_gate_suite("RISK-3", [g08_env], candidate_sha=g08_env["candidate_sha"])
            self.assertIn("G08", ev_res["passed_gates"])

            # Dirtying a file in clean_repo downgrades PASS envelope to E2/REPORTED
            (clean_repo / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
            dirty_env = runner.run_gate_command(
                run_id="run-r3",
                mission_id="R3-DIRTY",
                stage="VERIFY",
                gate_id="G08",
                command_argv=[sys.executable, "-c", "print('sec ok')"],
                cwd=clean_repo,
                evidence_type="SECURITY",
                is_runtime_gate=True,
            )
            self.assertTrue(dirty_env["dirty"])
            self.assertEqual(dirty_env["evidence_level"], "E2")
            self.assertEqual(dirty_env["provenance"], "REPORTED")

            # Non-git directory fails git status -> dirty=True and downgraded to E2/REPORTED
            non_git_dir = tmp_root / "not_a_git_repo"
            non_git_dir.mkdir()
            non_git_env = runner.run_gate_command(
                run_id="run-r3",
                mission_id="R3-NONGIT",
                stage="VERIFY",
                gate_id="G05",
                command_argv=[sys.executable, "-c", "print('ok')"],
                cwd=non_git_dir,
                evidence_type="UNIT",
            )
            self.assertTrue(non_git_env["dirty"])
            self.assertEqual(non_git_env["evidence_level"], "E2")

        # Certainty ceiling inflation & UNIT-on-G07 rejected
        inflated_g07 = {
            "schema_version": 1,
            "run_id": "run-r3",
            "mission_id": "R3-TEST",
            "stage": "VERIFY",
            "gate_id": "G07",
            "candidate_sha": BASE_SHA,
            "tree_sha": BASE_SHA,
            "dirty": False,
            "command_argv": ["pytest"],
            "cwd": ".",
            "started_at_utc": "2026-11-19T00:00:00Z",
            "completed_at_utc": "2026-11-19T00:00:01Z",
            "exit_code": 0,
            "status": "PASS",
            "environment_versions": {"python": "3.13.5"},
            "fixture_sha256": "0" * 64,
            "artifact_path": "a.log",
            "artifact_size_bytes": 1,
            "artifact_sha256": "a" * 64,
            "evidence_level": "E5",
            "evidence_type": "UNIT",
            "provenance": "DIRECTLY_OBSERVED",
            "certainty_ceiling": "PRODUCTION_PROVEN",
            "redacted": True,
        }
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite("RISK-3", [inflated_g07], candidate_sha=BASE_SHA)
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite("RISK-3", [{**inflated_g07, "certainty_ceiling": "VERIFIED"}], candidate_sha=BASE_SHA)

        # Clean G10 NOT_RUN returns BLOCKED with G10 in not_run_gates without crashing
        g10_not_run = {
            **inflated_g07,
            "gate_id": "G10",
            "exit_code": None,
            "status": "NOT_RUN",
            "evidence_level": "E0",
            "evidence_type": "NONE",
            "provenance": "ASSUMED",
            "certainty_ceiling": "HYPOTHESIS",
        }
        nr_res = evaluate_gate_suite("RISK-2", [g10_not_run], candidate_sha=BASE_SHA)
        self.assertEqual(nr_res["overall_status"], "BLOCKED")
        self.assertIn("G10", nr_res["not_run_gates"])

        # NOX-R3-007: PENDING_REMOTE with remote_head_probe=None halts BLOCKED
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "r3_rec.db"
            j = FactoryJournal(db)
            rm = RecoveryManager(j)
            br = NairuDeliveryBroker(db, actor_verifier=lambda: {"login": EXPECTED_BROKER_LOGIN, "id": EXPECTED_BROKER_USER_ID})
            j.register_mission(base_pkt)
            from integrations.antigravity.factory.delivery import compute_delivery_key
            dk = compute_delivery_key(base_pkt["mission_id"], base_pkt["permitted_branch"], NEXT_SHA)
            c = br._connect()
            try:
                c.execute(
                    """
                    INSERT INTO delivery_receipts (
                        delivery_key, mission_id, branch, base_sha, candidate_sha,
                        actor_login, actor_id, status, pr_mode, receipt_markdown, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING_REMOTE', 'VALIDATED_DRAFT_PR', 'md', '2026-11-19T00:00:00Z')
                    """,
                    (dk, base_pkt["mission_id"], base_pkt["permitted_branch"], BASE_SHA, NEXT_SHA, EXPECTED_BROKER_LOGIN, EXPECTED_BROKER_USER_ID),
                )
            finally:
                c.close()
            cap_no_probe = rm.reconcile_interrupted_mission(
                base_pkt["mission_id"],
                interruption_point="PRE_BROKER_RECEIPT",
                observed_local_sha=NEXT_SHA,
                remote_head_probe=None,
            )
            self.assertFalse(cap_no_probe["delivery_reconciled"])
            self.assertEqual(cap_no_probe["next_allowed_action"], "HALT_BLOCKED_REQUIRE_MAINTAINER_RECONCILIATION")

        # NOX-R3-008: Scribe/Lucien executable paths rejected, uppercase .MD allowed, upstream/main rejected
        scribe_pkt = make_valid_packet("R3-SCRIBE", persona="Antigravity-Scribe", formal_role="Code Writer", owned_paths=["integrations/antigravity/"])
        lucien_pkt = make_valid_packet("R3-LUCIEN", persona="Antigravity-Lucien", formal_role="Code Writer", owned_paths=["integrations/antigravity/"])
        with self.assertRaises(PolicyViolationError):
            assert_paths_within_ownership(scribe_pkt, ["integrations/antigravity/adr/exploit.py"])
        with self.assertRaises(PolicyViolationError):
            assert_paths_within_ownership(lucien_pkt, ["integrations/antigravity/schemas/evil.sh"])
        self.assertEqual(
            assert_paths_within_ownership(scribe_pkt, ["integrations/antigravity/README.MD"]),
            ["integrations/antigravity/README.MD"],
        )
        self.assertTrue(is_prohibited_branch("refs/remotes/upstream/main"))
        self.assertTrue(is_prohibited_branch("upstream/main"))
        self.assertFalse(is_prohibited_branch("feat/antigravity-software-factory-r1"))

        # NOX-R3-009: self_healing_repair.py invokes writer repair + schema-synced Nox re-review
        from integrations.antigravity.factory.workflow_stages import workflow_stages
        repair_wf = workflow_stages("self_healing_repair")
        self.assertEqual([s["stage"] for s in repair_wf],
                         ["failure_classification", "root_cause_repair", "independent_recheck"])
        self.assertIn("writer-result.schema.json", repair_wf[1]["artifact"])
        self.assertIn("nox-result.schema.json", repair_wf[2]["artifact"])
        self.assertIn("final_sha", repair_wf[2]["requires"])
        self.assertEqual(repair_wf[0]["stop_on"], ["requirements", "drift", "resource"])
        self.assertTrue(all(not s["native_invoked"] and s["requires_separate_authority"] for s in repair_wf))

        # NOX-R3-010: ANTIGRAVITY_CSRF_TOKEN= redacted
        self.assertNotIn("secret_csrf_token_12345", redact_secrets("ANTIGRAVITY_CSRF_TOKEN=secret_csrf_token_12345"))

    def test_nox_cycle4_security_and_governance_regressions(self) -> None:
        """Discriminating regression tests for NOX-R4-001..012 findings."""
        import importlib.util
        import sqlite3
        from integrations.antigravity.factory.authority import (
            ZERO_SHA40,
            load_schema,
            validate_against_schema,
        )
        from integrations.antigravity.factory.delivery import compute_delivery_key
        from integrations.antigravity.factory.policy import is_protected_governance_path

        base_pkt = make_valid_packet("R4-TEST")

        # NOX-R4-001: _validate_gate_summary rejects mandatory exemptions, empty N/A reasons, missing risk-floor gates, and zero SHA
        with self.assertRaises(AuthorityError):
            verify_mission_packet({**base_pkt, "base_sha": ZERO_SHA40})
        with self.assertRaises(AuthorityError):
            verify_mission_packet({**base_pkt, "risk_class": "RISK-3", "required_gates": ["G00", "G13", "G15"]})
        with self.assertRaises(AuthorityError):
            verify_mission_packet({**base_pkt, "non_applicable_gates": {"G00": "skip"}})

        with tempfile.TemporaryDirectory() as tmp:
            broker = NairuDeliveryBroker(
                Path(tmp) / "r4_broker.db",
                actor_verifier=lambda: {"login": EXPECTED_BROKER_LOGIN, "id": EXPECTED_BROKER_USER_ID, "type": "User"},
            )
            with self.assertRaises(DeliveryBrokerError):
                broker._validate_gate_summary(
                    {**base_pkt, "risk_class": "RISK-3", "required_gates": list(RISK_REQUIRED_GATES["RISK-3"])},
                    BASE_SHA,
                    {
                        "overall_status": "PASS",
                        "candidate_sha": BASE_SHA,
                        "risk_class": "RISK-3",
                        "passed_gates": [],
                        "documented_non_applicable": {"G00": "", "G13": "", "G15": ""},
                    },
                )
            with self.assertRaises(DeliveryBrokerError):
                broker._validate_gate_summary(
                    base_pkt,
                    ZERO_SHA40,
                    {
                        "overall_status": "PASS",
                        "candidate_sha": ZERO_SHA40,
                        "risk_class": base_pkt["risk_class"],
                        "passed_gates": list(RISK_REQUIRED_GATES[base_pkt["risk_class"]]),
                    },
                )

        # NOX-R4-002: evaluate_gate_suite blocks E4+NONE/SOURCE, non-required FAIL (G11), FAIL masked by N/A, duplicate gate_id, invalid N/A gate
        def _env(gid: str, *, status: str = "PASS", level: str = "E4", ev_type: str = "INTEGRATION", prov: str = "AUTOMATED") -> dict:
            return {
                "schema_version": 1,
                "run_id": "run-r4",
                "mission_id": "R4-TEST",
                "stage": "VERIFY",
                "gate_id": gid,
                "candidate_sha": BASE_SHA,
                "tree_sha": BASE_SHA,
                "dirty": False,
                "command_argv": ["python", "-B", "-c", "print('ok')"],
                "cwd": ".",
                "started_at_utc": "2026-11-20T00:00:00Z",
                "completed_at_utc": "2026-11-20T00:00:01Z",
                "exit_code": 0 if status == "PASS" else 1,
                "status": status,
                "environment_versions": {"python": "3.13.5"},
                "fixture_sha256": "0" * 64,
                "artifact_path": "a.log",
                "artifact_size_bytes": 1,
                "artifact_sha256": "a" * 64,
                "evidence_level": level,
                "evidence_type": ev_type,
                "provenance": prov,
                "certainty_ceiling": "VERIFIED" if level in ("E3", "E4", "E5") else ("SUPPORTED" if level in ("E1", "E2") else "HYPOTHESIS"),
                "redacted": True,
            }

        risk0_passing = [_env(g) for g in RISK_REQUIRED_GATES["RISK-0"]]
        self.assertEqual(evaluate_gate_suite("RISK-0", risk0_passing, candidate_sha=BASE_SHA)["overall_status"], "PASS")
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite("RISK-0", [_env(g, ev_type="NONE") for g in RISK_REQUIRED_GATES["RISK-0"]], candidate_sha=BASE_SHA)
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite("RISK-0", [_env(g, ev_type="SOURCE") for g in RISK_REQUIRED_GATES["RISK-0"]], candidate_sha=BASE_SHA)
        g11_fail_res = evaluate_gate_suite("RISK-0", risk0_passing + [_env("G11", status="FAIL", level="E1", ev_type="RUNTIME", prov="DIRECTLY_OBSERVED")], candidate_sha=BASE_SHA)
        self.assertEqual(g11_fail_res["overall_status"], "BLOCKED")
        self.assertIn("G11", g11_fail_res["failed_gates"])
        g04_masked = evaluate_gate_suite(
            "RISK-0",
            [_env(g) for g in RISK_REQUIRED_GATES["RISK-0"] if g != "G04"] + [_env("G04", status="FAIL", level="E1", prov="DIRECTLY_OBSERVED")],
            candidate_sha=BASE_SHA,
            non_applicable_gates={"G04": "attempt to mask fail"},
        )
        self.assertEqual(g04_masked["overall_status"], "BLOCKED")
        self.assertIn("G04", g04_masked["failed_gates"])
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite(
                "RISK-0",
                [_env(g) for g in RISK_REQUIRED_GATES["RISK-0"] if g != "G04"]
                + [_env("G04", status="FAIL", level="E1", prov="DIRECTLY_OBSERVED"), _env("G04")],
                candidate_sha=BASE_SHA,
            )
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite("RISK-0", risk0_passing, candidate_sha=BASE_SHA, non_applicable_gates={"G99": "invalid gate"})

        # NOX-R4-003: Reviewer/PAUSED mutating checks, Lucien Code Writer requirement, .git & second-brain governance paths
        lucien_rev = {**base_pkt, "assigned_persona": "Antigravity-Lucien", "formal_role": "Reviewer", "allowed_operations": ["READ", "WRITE_OWNED"]}
        qa_rev = {**base_pkt, "assigned_persona": "Antigravity-QA", "formal_role": "Reviewer", "allowed_operations": ["READ", "WRITE_OWNED"]}
        paused_pkt = {**base_pkt, "work_mode": "PAUSED"}
        with self.assertRaises(PolicyViolationError):
            assert_operation_allowed(lucien_rev, "WRITE_OWNED")
        with self.assertRaises(PolicyViolationError):
            assert_operation_allowed(qa_rev, "WRITE_OWNED")
        with self.assertRaises(PolicyViolationError):
            assert_operation_allowed(paused_pkt, "WRITE_OWNED")
        with self.assertRaises(PolicyViolationError):
            assert_paths_within_ownership(lucien_rev, ["integrations/antigravity/adr/x.md"], require_write_operation=False)
        for bad_gov in (".git/hooks", "owned/.git/config", "second-brain/AGENTS.md", "second-brain/SYSTEM_BOUNDARY.md", "second-brain/EVIDENCE_CROSSWALK.md", "second-brain/SHARED_DOCS.sha256"):
            self.assertTrue(is_protected_governance_path(bad_gov))
            with self.assertRaises(AuthorityError):
                verify_mission_packet({**base_pkt, "owned_paths": [bad_gov]})

        # NOX-R4-004 & NOX-R4-006: Staged index-only edit, 120000 gitlink/symlink mode, nested .git, zero base_sha, and broker repo_root ancestry/diff verification
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            repo = _make_clean_git_repo(troot)
            (repo / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
            (repo / "owned").mkdir()
            (repo / "owned" / "a.py").write_text("x = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, capture_output=True, check=True)
            base_s = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
            owned_pkt = make_valid_packet("R4-WT", owned_paths=["owned/"])
            owned_pkt["base_sha"] = base_s
            owned_pkt["selected_skills"]["skill_source_sha"] = base_s

            sb = WorktreeSandbox(repo, troot / "wts")
            with self.assertRaises(AuthorityError):
                sb.create_worktree("feat/r4-zero", ZERO_SHA40, "wt_zero")

            wt = sb.create_worktree("feat/r4-staged", base_s, "wt_staged")
            try:
                # 1. Index-only staged change on AGENTS.md (working tree restored to HEAD) must still be caught!
                (wt / "AGENTS.md").write_text("# Tampered\n", encoding="utf-8")
                subprocess.run(["git", "add", "AGENTS.md"], cwd=wt, capture_output=True, check=True)
                subprocess.run(["git", "checkout", "--", "AGENTS.md"], cwd=wt, capture_output=True, check=True)
                with self.assertRaises(PolicyViolationError):
                    sb.inspect_and_validate_worktree(wt, owned_pkt, base_sha=base_s)
                subprocess.run(["git", "reset", "HEAD", "AGENTS.md"], cwd=wt, capture_output=True, check=True)

                # 2. Git mode 120000 symlink in index (works even on Windows with core.symlinks=false) must fail closed!
                blob_sha = subprocess.run(
                    ["git", "hash-object", "-w", "--stdin"],
                    cwd=wt,
                    input="../AGENTS.md",
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
                subprocess.run(
                    ["git", "update-index", "--add", "--cacheinfo", f"120000,{blob_sha},owned/sym_link"],
                    cwd=wt,
                    capture_output=True,
                    check=True,
                )
                with self.assertRaises(PolicyViolationError):
                    sb.inspect_and_validate_worktree(wt, owned_pkt, base_sha=base_s)

                # Commit the symlink to test NOX-R4-006 broker repo_root detection
                subprocess.run(["git", "commit", "-m", "add symlink"], cwd=wt, capture_output=True, check=True)
                sym_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt, capture_output=True, text=True, check=True).stdout.strip()

                broker_r4 = NairuDeliveryBroker(
                    troot / "broker_repo.db",
                    actor_verifier=lambda: {"login": EXPECTED_BROKER_LOGIN, "id": EXPECTED_BROKER_USER_ID, "type": "User"},
                )
                nox_sym = NoxReviewEngine().execute_review(
                    mission_id=owned_pkt["mission_id"],
                    frozen_sha=sym_sha,
                    author_context_id="ctx-jane",
                    inspected_scope=["owned/"],
                    evidence_inspected=["env-1"],
                    findings=[],
                )
                with self.assertRaises(DeliveryBrokerError):
                    broker_r4.prepare_and_record_delivery(
                        packet=owned_pkt,
                        candidate_sha=sym_sha,
                        changed_files=["owned/a.py"],
                        gate_summary={
                            "risk_class": owned_pkt["risk_class"],
                            "candidate_sha": sym_sha,
                            "overall_status": "PASS",
                            "passed_gates": list(RISK_REQUIRED_GATES[owned_pkt["risk_class"]]),
                        },
                        nox_result=nox_sym,
                        repo_root=wt,
                    )

                # Reset back to base_s and test clean commit + omitted changed_files + non-ancestor commit
                subprocess.run(["git", "reset", "--hard", base_s], cwd=wt, capture_output=True, check=True)
                (wt / "owned" / "a.py").write_text("x = 2\n", encoding="utf-8")
                (wt / "owned" / "b.py").write_text("y = 3\n", encoding="utf-8")
                subprocess.run(["git", "add", "owned/a.py", "owned/b.py"], cwd=wt, capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "clean owned edit"], cwd=wt, capture_output=True, check=True)
                clean_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt, capture_output=True, text=True, check=True).stdout.strip()

                nox_clean = NoxReviewEngine().execute_review(
                    mission_id=owned_pkt["mission_id"],
                    frozen_sha=clean_sha,
                    author_context_id="ctx-jane",
                    inspected_scope=["owned/"],
                    evidence_inspected=["env-1"],
                    findings=[],
                )
                # Omitting owned/b.py from caller changed_files must fail closed!
                with self.assertRaises(DeliveryBrokerError):
                    broker_r4.prepare_and_record_delivery(
                        packet=owned_pkt,
                        candidate_sha=clean_sha,
                        changed_files=["owned/a.py"],
                        gate_summary={
                            "risk_class": owned_pkt["risk_class"],
                            "candidate_sha": clean_sha,
                            "overall_status": "PASS",
                            "passed_gates": list(RISK_REQUIRED_GATES[owned_pkt["risk_class"]]),
                        },
                        nox_result=nox_clean,
                        repo_root=wt,
                    )
                # Supplying accurate changed_files succeeds with repo_root verification!
                delivered = broker_r4.prepare_and_record_delivery(
                    packet=owned_pkt,
                    candidate_sha=clean_sha,
                    changed_files=["owned/a.py", "owned/b.py"],
                    gate_summary={
                        "risk_class": owned_pkt["risk_class"],
                        "candidate_sha": clean_sha,
                        "overall_status": "PASS",
                        "passed_gates": list(RISK_REQUIRED_GATES[owned_pkt["risk_class"]]),
                    },
                    nox_result=nox_clean,
                    repo_root=wt,
                )
                self.assertEqual(delivered["status"], "DELIVERED")

                # Nested owned/.git inside worktree must be caught!
                (wt / "owned" / ".git").mkdir()
                with self.assertRaises(PolicyViolationError):
                    sb.inspect_and_validate_worktree(wt, owned_pkt, base_sha=base_s)
            finally:
                sb.remove_worktree(wt)

        # NOX-R4-005: Direct forge_guard evaluation for all 9 bypass cases + safe non-forced git branch -d allowed
        guard_spec = importlib.util.spec_from_file_location("forge_guard_r4", PLUGIN_ROOT / "hooks" / "forge_guard.py")
        guard_mod = importlib.util.module_from_spec(guard_spec)
        assert guard_spec and guard_spec.loader
        guard_spec.loader.exec_module(guard_mod)
        for denied_cmd in (
            '"C:\\Program Files\\Git\\bin\\git.exe" push --force origin feat/x',
            '"C:\\Program Files\\GitHub CLI\\gh.exe" pr merge 14 --admin',
            "git -C. push --force origin feat/x",
            "git branch -df feat/x",
            "gh api --method=DELETE repos/Kirch-Nairu/Operation-FORGE.kirion/git/refs/heads/main",
            "gh api repos/Kirch-Nairu/Operation-FORGE.kirion/rulesets -f name=evil",
            "gh api -X PUT repos/Kirch-Nairu/Operation-FORGE.kirion/pulls/14/merge",
            "gh api -X POST repos/Kirch-Nairu/Operation-FORGE.kirion/pulls/14/reviews -f event=APPROVE",
            "gh api -X PATCH repos/Kirch-Nairu/Operation-FORGE.kirion -f default_branch=evil",
        ):
            self.assertEqual(
                guard_mod.evaluate_pre_tool_use({"toolCall": {"name": "run_command", "args": {"CommandLine": denied_cmd}}})["decision"],
                "deny",
                f"Expected deny for {denied_cmd}",
            )
        self.assertEqual(
            guard_mod.evaluate_pre_tool_use(
                {"toolCall": {"name": "write_file", "args": {"Path": "C:/Users/arane/.gemini/antigravity/../config/settings.json"}}}
            )["decision"],
            "deny",
        )
        # Positive controls: safe lowercase git branch -d and safe PR comment API are allowed
        self.assertEqual(
            guard_mod.evaluate_pre_tool_use({"toolCall": {"name": "run_command", "args": {"CommandLine": "git branch -d feat/merged"}}})["decision"],
            "allow",
        )
        self.assertEqual(
            guard_mod.evaluate_pre_tool_use(
                {"toolCall": {"name": "run_command", "args": {"CommandLine": "gh api repos/Kirch-Nairu/Operation-FORGE.kirion/issues/13/comments -f body=ok"}}}
            )["decision"],
            "allow",
        )

        # NOX-R4-007 & NOX-R4-010: Journal metadata hash chain, candidate_sha validation, conflicting re-registration, recovery terminal/drift/tamper halts
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "r4_journal.db"
            j = FactoryJournal(db)
            rm = RecoveryManager(j)
            br = NairuDeliveryBroker(db, actor_verifier=lambda: {"login": EXPECTED_BROKER_LOGIN, "id": EXPECTED_BROKER_USER_ID})

            m1 = j.register_mission(base_pkt)
            m1_repeat = j.register_mission(base_pkt)
            self.assertIn("packet", m1_repeat)
            self.assertEqual(m1_repeat["packet"]["mission_id"], m1["packet"]["mission_id"])
            with self.assertRaises(SchedulerError):
                j.register_mission({**base_pkt, "run_id": "run-conflicting"})
            with self.assertRaises(SchedulerError):
                j.transition_state(base_pkt["mission_id"], "AUTHORIZED", expected_version=1, actor_role="Maintainer", candidate_sha="not-a-sha")
            with self.assertRaises(SchedulerError):
                j.transition_state(base_pkt["mission_id"], "AUTHORIZED", expected_version=1, actor_role="Maintainer", candidate_sha=ZERO_SHA40)

            j.transition_state(base_pkt["mission_id"], "AUTHORIZED", expected_version=1, actor_role="Maintainer")
            # Insert unresolved PENDING_REMOTE under an older SHA -> recovery for a drifted local SHA must halt BLOCKED!
            prior_sha = "e" * 40
            dkey_prior = compute_delivery_key(base_pkt["mission_id"], base_pkt["permitted_branch"], prior_sha)
            c = br._connect()
            try:
                c.execute(
                    """
                    INSERT INTO delivery_receipts (
                        delivery_key, mission_id, branch, base_sha, candidate_sha,
                        actor_login, actor_id, status, pr_mode, receipt_markdown, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING_REMOTE', 'VALIDATED_DRAFT_PR', 'md', '2026-11-19T00:00:00Z')
                    """,
                    (dkey_prior, base_pkt["mission_id"], base_pkt["permitted_branch"], BASE_SHA, prior_sha, EXPECTED_BROKER_LOGIN, EXPECTED_BROKER_USER_ID),
                )
            finally:
                c.close()
            drift_local_cap = rm.reconcile_interrupted_mission(
                base_pkt["mission_id"],
                interruption_point="PRE_BROKER_RECEIPT",
                observed_local_sha=NEXT_SHA,
                remote_head_probe=lambda _b: BASE_SHA,
            )
            self.assertEqual(drift_local_cap["next_allowed_action"], "HALT_BLOCKED_REQUIRE_MAINTAINER_RECONCILIATION")

            # Terminal QUARANTINED mission must halt BLOCKED on reconciliation
            j.transition_state(base_pkt["mission_id"], "QUARANTINED", expected_version=2, actor_role="Maintainer")
            term_cap = rm.reconcile_interrupted_mission(
                base_pkt["mission_id"],
                interruption_point="PRE_LOCAL_COMMIT",
                observed_local_sha=BASE_SHA,
            )
            self.assertTrue(term_cap["next_allowed_action"].startswith("HALT_BLOCKED"))

            # Tampering with event_type column in SQLite must break verify_hash_chain() and halt recovery!
            self.assertTrue(j.verify_hash_chain())
            raw_conn = sqlite3.connect(db)
            try:
                raw_conn.execute("UPDATE journal_events SET event_type = 'TAMPERED_EVENT' WHERE seq = 1")
                raw_conn.commit()
            finally:
                raw_conn.close()
            self.assertFalse(j.verify_hash_chain())
            with self.assertRaises(AuthorityError):
                rm.reconcile_interrupted_mission(base_pkt["mission_id"], interruption_point="PRE_LOCAL_COMMIT", observed_local_sha=BASE_SHA)

        # NOX-R4-008: Strict bool-vs-int schema const validation, blank/zero-SHA Nox rejection, and verify_git_authority fail-closed
        sb_schema = load_schema("sandbox-capsule.schema.json", base_dir=REPO_ROOT / "schemas")
        bool_capsule = {
            "capsule_version": True,
            "repository": "Kirch-Nairu/Operation-FORGE.kirion",
            "remote": "origin",
            "source_branch": "feat/x",
            "source_sha": BASE_SHA,
            "target_branch": "feat/x",
            "candidate_head": BASE_SHA,
            "worktree_status": "clean",
            "commands_executed": [],
            "known_failures": [],
            "known_unverified_claims": [],
            "blocker": None,
            "next_permitted_action": "WAIT",
            "created_at": "2026-11-20T00:00:00Z",
            "created_by_role": "Maintainer",
        }
        self.assertTrue(len(validate_against_schema(bool_capsule, sb_schema)) > 0)
        nox_eng = NoxReviewEngine()
        with self.assertRaises(QualityGateError):
            nox_eng.execute_review(
                mission_id="R4-NOX",
                frozen_sha=BASE_SHA,
                author_context_id="ctx-jane",
                reviewer_context_id="   ",
                inspected_scope=["integrations/antigravity/"],
                evidence_inspected=[],
                findings=[],
            )
        with self.assertRaises(QualityGateError):
            nox_eng.execute_review(
                mission_id="R4-NOX",
                frozen_sha=ZERO_SHA40,
                author_context_id="ctx-jane",
                inspected_scope=["integrations/antigravity/"],
                evidence_inspected=[],
                findings=[],
            )

        # NOX-R4-009: Quoted secrets & sk-proj keys redacted; NOT_RUN emits E0/NONE/ASSUMED/HYPOTHESIS
        for raw_secret, leaked_frag in (
            ('ANTIGRAVITY_CSRF_TOKEN="csrf_secret_98765"', "csrf_secret_98765"),
            ('{"ANTIGRAVITY_CSRF_TOKEN": "csrf_secret_98765"}', "csrf_secret_98765"),
            ('password="super_secret_pw"', "super_secret_pw"),
            ('x-codeium-csrf-token: "tok_999999"', "tok_999999"),
            ("sk-proj-1234567890abcdefghijklmnop", "sk-proj-"),
        ):
            self.assertNotIn(leaked_frag, redact_secrets(raw_secret))
        with tempfile.TemporaryDirectory() as tmp:
            clean_repo = _make_clean_git_repo(Path(tmp))
            runner = TrustedEvidenceRunner(Path(tmp) / "arts")
            nr_env = runner.run_gate_command(
                run_id="run-nr",
                mission_id="R4-NR",
                stage="VERIFY",
                gate_id="G10",
                command_argv=["definitely_nonexistent_binary_kirion_404"],
                cwd=clean_repo,
                evidence_type="RUNTIME",
                is_runtime_gate=True,
            )
            self.assertEqual(nr_env["status"], "NOT_RUN")
            self.assertEqual(nr_env["evidence_level"], "E0")
            self.assertEqual(nr_env["evidence_type"], "NONE")
            self.assertEqual(nr_env["provenance"], "ASSUMED")
            self.assertEqual(nr_env["certainty_ceiling"], "HYPOTHESIS")

        # NOX-R4-011 & NOX-R4-012: FleetDispatcher verifies packet & works across external worktree roots; php_laravel profile matches dispatcher
        with tempfile.TemporaryDirectory() as tmp:
            ext_dispatcher = FleetDispatcher(repo_root=Path(tmp))
            ext_ctx = ext_dispatcher.create_isolated_context("Antigravity-Jane", "Code Writer")
            self.assertEqual(ext_ctx["agent_contract_path"], "integrations/antigravity/plugins/kirion-forge/agents/antigravity-jane.md")
            malicious_pkt = {**base_pkt, "permitted_branch": "main", "verifier": "Mallory", "work_mode": "PAUSED", "owned_paths": ["AGENTS.md"]}
            with self.assertRaises(AuthorityError):
                ext_dispatcher.dispatch_worker(malicious_pkt, lambda p, c, w: {"ran": True})
        for profile_name in ("csharp_aspnet.json", "php_laravel.json", "salryn_high_integrity.json", "frontend_web.json"):
            prof = json.loads((PROFILES_ROOT / profile_name).read_text(encoding="utf-8"))
            selected = select_skills_for_mission(prof["profile_id"], skill_source_sha=SKILL_REGISTRY_SHA)
            selected_names = [Path(f).parent.name for f in selected["files"]]
            self.assertEqual(selected_names, prof["required_skills"], f"Profile/dispatcher mismatch for {profile_name}")
            self.assertLessEqual(len(selected["files"]), 8)

    def test_nox_cycle5_security_and_governance_regressions(self) -> None:
        """Discriminating regression tests for NOX-R5-001..015 findings."""
        import importlib.util
        import urllib.error
        from integrations.antigravity.benchmarks.hidden_oracles import _wait_for_health
        from integrations.antigravity.factory.authority import ZERO_SHA40
        from integrations.antigravity.factory.policy import is_prohibited_branch

        base_pkt = make_valid_packet("R5-TEST")

        # NOX-R5-001: Post-hoc gate exemptions rejected; overlapping required_gates/non_applicable_gates rejected
        risk3_pkt = {**base_pkt, "risk_class": "RISK-3", "required_gates": list(RISK_REQUIRED_GATES["RISK-3"])}
        verify_mission_packet(risk3_pkt)
        with self.assertRaises(AuthorityError):
            verify_mission_packet({**risk3_pkt, "non_applicable_gates": {"G07": "overlap"}})

        with tempfile.TemporaryDirectory() as tmp:
            broker = NairuDeliveryBroker(
                Path(tmp) / "r5_broker.db",
                actor_verifier=lambda: {"login": EXPECTED_BROKER_LOGIN, "id": EXPECTED_BROKER_USER_ID, "type": "User"},
            )
            post_hoc_na = {g: "post-hoc skipped" for g in RISK_REQUIRED_GATES["RISK-3"] if g not in ("G00", "G13", "G15")}
            with self.assertRaises(DeliveryBrokerError):
                broker._validate_gate_summary(
                    risk3_pkt,
                    BASE_SHA,
                    {
                        "overall_status": "PASS",
                        "candidate_sha": BASE_SHA,
                        "risk_class": "RISK-3",
                        "passed_gates": ["G00", "G13", "G15"],
                        "documented_non_applicable": post_hoc_na,
                    },
                )
            # Pre-authorized non-mandatory exemption in MissionPacket succeeds
            pre_na_pkt = {
                **base_pkt,
                "risk_class": "RISK-2",
                "required_gates": [g for g in RISK_REQUIRED_GATES["RISK-2"] if g != "G14"],
                "non_applicable_gates": {"G14": "Pre-authorized single-lane docs fixture"},
            }
            verify_mission_packet(pre_na_pkt)
            broker._validate_gate_summary(
                pre_na_pkt,
                BASE_SHA,
                {
                    "overall_status": "PASS",
                    "candidate_sha": BASE_SHA,
                    "risk_class": "RISK-2",
                    "passed_gates": pre_na_pkt["required_gates"],
                    "documented_non_applicable": {"G14": "Pre-authorized single-lane docs fixture"},
                },
            )

        # NOX-R5-002: evaluate_gate_suite rejects ASSUMED/REPORTED on E1, zero tree_sha on PASS, and enforces extra required_gates (e.g. G11)
        g00_bad_prov = {
            "schema_version": 1,
            "run_id": "run-r5",
            "mission_id": "R5-TEST",
            "stage": "VERIFY",
            "gate_id": "G00",
            "candidate_sha": BASE_SHA,
            "tree_sha": BASE_SHA,
            "dirty": False,
            "command_argv": ["git", "rev-parse", "HEAD"],
            "cwd": ".",
            "started_at_utc": "2026-11-20T00:00:00Z",
            "completed_at_utc": "2026-11-20T00:00:01Z",
            "exit_code": 0,
            "status": "PASS",
            "environment_versions": {"python": "3.13.5"},
            "fixture_sha256": "0" * 64,
            "artifact_path": "a.log",
            "artifact_size_bytes": 1,
            "artifact_sha256": "a" * 64,
            "evidence_level": "E1",
            "evidence_type": "SOURCE",
            "provenance": "ASSUMED",
            "certainty_ceiling": "SUPPORTED",
            "redacted": True,
        }
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite("RISK-0", [g00_bad_prov], candidate_sha=BASE_SHA)
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite("RISK-0", [{**g00_bad_prov, "provenance": "REPORTED"}], candidate_sha=BASE_SHA)
        with self.assertRaises(QualityGateError):
            evaluate_gate_suite("RISK-0", [{**g00_bad_prov, "provenance": "DIRECTLY_OBSERVED", "tree_sha": ZERO_SHA40}], candidate_sha=BASE_SHA)
        extra_g11_res = evaluate_gate_suite("RISK-0", [{**g00_bad_prov, "provenance": "DIRECTLY_OBSERVED"}], candidate_sha=BASE_SHA, required_gates=["G11"])
        self.assertEqual(extra_g11_res["overall_status"], "BLOCKED")
        self.assertIn("G11", extra_g11_res["missing_gates"])

        # NOX-R5-003: TrustedEvidenceRunner re-checks post-run git state, maps SOURCE -> E1/DIRECTLY_OBSERVED, rejects NONE
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            clean_repo = _make_clean_git_repo(troot)
            runner = TrustedEvidenceRunner(troot / "arts")
            with self.assertRaises(AuthorityError):
                runner.run_gate_command(
                    run_id="run-r5",
                    mission_id="R5-EV",
                    stage="VERIFY",
                    gate_id="G00",
                    command_argv=[sys.executable, "-c", "print('ok')"],
                    cwd=clean_repo,
                    evidence_type="NONE",
                )
            src_env = runner.run_gate_command(
                run_id="run-r5",
                mission_id="R5-EV",
                stage="VERIFY",
                gate_id="G00",
                command_argv=[sys.executable, "-c", "print('sha ok')"],
                cwd=clean_repo,
                evidence_type="SOURCE",
            )
            self.assertEqual(src_env["evidence_level"], "E1")
            self.assertEqual(src_env["provenance"], "DIRECTLY_OBSERVED")
            self.assertFalse(src_env["dirty"])

            # Mid-command working-tree mutation must be detected post-run and downgraded to E2/REPORTED!
            mut_env = runner.run_gate_command(
                run_id="run-r5",
                mission_id="R5-EV",
                stage="VERIFY",
                gate_id="G05",
                command_argv=[sys.executable, "-c", "open('mutated_during_test.txt', 'w').write('dirty')"],
                cwd=clean_repo,
                evidence_type="UNIT",
            )
            self.assertTrue(mut_env["dirty"])
            self.assertEqual(mut_env["evidence_level"], "E2")
            self.assertEqual(mut_env["provenance"], "REPORTED")

        # NOX-R5-004: Embedded refspecs, tags, globs rejected by is_prohibited_branch
        for bad_br in ("feat/a:+main", "feat/a:+refs/heads/main", "feat/a:feat/b", "refs/tags/v1.0", "feat//bad", "feat/a..b"):
            self.assertTrue(is_prohibited_branch(bad_br), f"Expected prohibited branch: {bad_br}")
            with self.assertRaises(AuthorityError):
                verify_mission_packet({**base_pkt, "permitted_branch": bad_br})

        # NOX-R5-005: forge_guard blocks multiline continuations, -XDELETE/-XPUT, full URL direct repo, quoted -c, --no-optional-locks, gh repo admin, gh api graphql mutation
        guard_spec = importlib.util.spec_from_file_location("forge_guard_r5", PLUGIN_ROOT / "hooks" / "forge_guard.py")
        guard_mod = importlib.util.module_from_spec(guard_spec)
        assert guard_spec and guard_spec.loader
        guard_spec.loader.exec_module(guard_mod)
        for denied_cmd in (
            "git push \\\norigin --force feat/x",
            "git push \\\norigin main",
            "gh pr review \\\n14 --approve",
            "gh pr \\\nmerge 14",
            "php artisan migrate:fresh \\\n--force",
            "git push `\norigin --force feat/x",
            "gh api -XDELETE repos/Kirch-Nairu/Operation-FORGE.kirion/git/refs/heads/main",
            "gh api -XPUT repos/Kirch-Nairu/Operation-FORGE.kirion/pulls/14/merge",
            "gh api -X PATCH https://api.github.com/repos/Kirch-Nairu/Operation-FORGE.kirion -f default_branch=evil",
            'git -c user.name="Kirch Nairu" push --force origin feat/x',
            'git -c core.sshCommand="ssh -i k" push origin main',
            "git --no-optional-locks push --force origin feat/x",
            "gh repo delete Kirch-Nairu/Operation-FORGE.kirion --yes",
            "gh repo edit Kirch-Nairu/Operation-FORGE.kirion --default-branch evil",
            'gh api graphql -f query="mutation { mergePullRequest(input: {pullRequestId: \\"1\\"}) { clientMutationId } }"',
        ):
            self.assertEqual(
                guard_mod.evaluate_pre_tool_use({"toolCall": {"name": "run_command", "args": {"CommandLine": denied_cmd}}})["decision"],
                "deny",
                f"Expected deny for {denied_cmd!r}",
            )
        # Read-only graphql query and gh repo view still allowed
        self.assertEqual(
            guard_mod.evaluate_pre_tool_use(
                {"toolCall": {"name": "run_command", "args": {"CommandLine": 'gh api graphql -f query="query { viewer { login } }"'}}}
            )["decision"],
            "allow",
        )

        # NOX-R5-006: Integration Writers counted in collisions/budget; tighter packet cap enforced; case-insensitive modules
        int_pkts = [
            {
                **make_valid_packet(f"INT-{i}", persona="Antigravity-Integrator", formal_role="Integration Writer", owned_paths=[f"src/mod_{i}/"]),
                "allowed_operations": ["READ", "INTEGRATE_BRANCH", "RUN_GATE"],
            }
            for i in range(4)
        ]
        with self.assertRaises(SchedulerError):
            enforce_wave_budget(int_pkts)
        int_collide = [
            {**int_pkts[0], "owned_paths": ["integrations/antigravity/"]},
            {**int_pkts[1], "owned_paths": ["integrations/antigravity/"]},
        ]
        self.assertTrue(len(detect_parallel_collisions(int_collide)) > 0)
        mod_collide = [
            {**int_pkts[0], "owned_modules": [" AuthService "]},
            {**int_pkts[1], "owned_modules": ["authservice"]},
        ]
        self.assertTrue(len(detect_parallel_collisions(mod_collide)) > 0)
        tight_cap_pkts = [
            {**make_valid_packet("CAP-1", owned_paths=["src/a/"]), "budget": {**base_pkt["budget"], "max_parallel_writers": 1}},
            {**make_valid_packet("CAP-2", owned_paths=["src/b/"]), "budget": {**base_pkt["budget"], "max_parallel_writers": 1}},
        ]
        with self.assertRaises(SchedulerError):
            enforce_wave_budget(tight_cap_pkts)

        # NOX-R5-007: KnowledgeManager rejects traversal mission_id and ZERO_SHA40
        with tempfile.TemporaryDirectory() as tmp:
            km = KnowledgeManager(Path(tmp) / "k")
            with self.assertRaises(AuthorityError):
                km.propose_skill_or_test_lesson(
                    mission_id="/../../../escaped_dir/pwn",
                    observed_sha=BASE_SHA,
                    failure_signature="sig",
                    root_cause="rc",
                    target_skill_name="kirion-core",
                    proposed_guidance="g",
                    discriminating_test_name="t",
                )
            with self.assertRaises(AuthorityError):
                km.propose_skill_or_test_lesson(
                    mission_id="F14-ZERO",
                    observed_sha=ZERO_SHA40,
                    failure_signature="sig",
                    root_cause="rc",
                    target_skill_name="kirion-core",
                    proposed_guidance="g",
                    discriminating_test_name="t",
                )

        # NOX-R5-008 & NOX-R5-009: Recovery probes remote drift unconditionally, restores fail closed on missing backup,
        # delivery requires WRITE_OWNED/INTEGRATE_BRANCH, and BLOCKED_DIAGNOSTIC_DRAFT can upgrade to VALIDATED_DRAFT_PR
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            db = troot / "r5_rec.db"
            j = FactoryJournal(db)
            rm = RecoveryManager(j)
            br = NairuDeliveryBroker(db, actor_verifier=lambda: {"login": EXPECTED_BROKER_LOGIN, "id": EXPECTED_BROKER_USER_ID})
            j.register_mission(base_pkt)

            # Missing backup file fails closed without creating empty db
            missing_bk = troot / "does_not_exist.db"
            with self.assertRaises(AuthorityError):
                rm.restore_journal(missing_bk, troot / "restored.db")
            self.assertFalse(missing_bk.exists())

            # Divergent remote head caught even when no PENDING_REMOTE receipt exists
            div_cap = rm.reconcile_interrupted_mission(
                base_pkt["mission_id"],
                interruption_point="PRE_BROKER_RECEIPT",
                observed_local_sha=NEXT_SHA,
                remote_head_probe=lambda _b: "f" * 40,
            )
            self.assertEqual(div_cap["next_allowed_action"], "HALT_BLOCKED_REQUIRE_MAINTAINER_RECONCILIATION")

            # Code Writer without WRITE_OWNED cannot deliver changed files
            no_write_pkt = {**base_pkt, "allowed_operations": ["READ", "DELIVER_DRAFT_PR"]}
            with self.assertRaises(DeliveryBrokerError):
                br.prepare_and_record_delivery(
                    packet=no_write_pkt,
                    candidate_sha=NEXT_SHA,
                    changed_files=["integrations/antigravity/factory/policy.py"],
                    gate_summary={
                        "risk_class": base_pkt["risk_class"],
                        "candidate_sha": NEXT_SHA,
                        "overall_status": "PASS",
                        "passed_gates": list(RISK_REQUIRED_GATES[base_pkt["risk_class"]]),
                    },
                    nox_result=NoxReviewEngine().execute_review(
                        mission_id=base_pkt["mission_id"],
                        frozen_sha=NEXT_SHA,
                        author_context_id="ctx-jane",
                        inspected_scope=["integrations/antigravity/factory/"],
                        evidence_inspected=["env-1"],
                        findings=[],
                    ),
                )

            # Deliver BLOCKED_DIAGNOSTIC_DRAFT first; recovery does not treat it as already-delivered validated candidate;
            # subsequent VALIDATED_DRAFT_PR upgrades the receipt cleanly!
            diag_rec = br.prepare_and_record_delivery(
                packet=base_pkt,
                candidate_sha=NEXT_SHA,
                changed_files=["integrations/antigravity/factory/policy.py"],
                gate_summary={"overall_status": "BLOCKED", "failed_gates": ["G10"]},
                nox_result=None,
                allow_blocked_diagnostic_draft=True,
            )
            self.assertEqual(diag_rec["pr_mode"], "BLOCKED_DIAGNOSTIC_DRAFT")
            rec_after_diag = rm.reconcile_interrupted_mission(
                base_pkt["mission_id"],
                interruption_point="PRE_BROKER_RECEIPT",
                observed_local_sha=NEXT_SHA,
            )
            self.assertNotEqual(rec_after_diag["next_allowed_action"], "NO_OP_ALREADY_DELIVERED_AWAIT_INDEPENDENT_REVIEW")
            val_rec = br.prepare_and_record_delivery(
                packet=base_pkt,
                candidate_sha=NEXT_SHA,
                changed_files=["integrations/antigravity/factory/policy.py"],
                gate_summary={
                    "risk_class": base_pkt["risk_class"],
                    "candidate_sha": NEXT_SHA,
                    "overall_status": "PASS",
                    "passed_gates": list(RISK_REQUIRED_GATES[base_pkt["risk_class"]]),
                },
                nox_result=NoxReviewEngine().execute_review(
                    mission_id=base_pkt["mission_id"],
                    frozen_sha=NEXT_SHA,
                    author_context_id="ctx-jane",
                    inspected_scope=["integrations/antigravity/factory/"],
                    evidence_inspected=["env-1"],
                    findings=[],
                ),
            )
            self.assertEqual(val_rec["pr_mode"], "VALIDATED_DRAFT_PR")
            self.assertFalse(val_rec["idempotent_replay"])

        # NOX-R5-010: SelfHealingController quarantines blank or mismatched author_context_id
        healer = SelfHealingController(max_repair_cycles=2, max_identical_retries=2)
        nox_other_author = NoxReviewEngine().execute_review(
            mission_id="R5-HEAL",
            frozen_sha=NEXT_SHA,
            author_context_id="ctx-different-author",
            reviewer_context_id="ctx-nox-1",
            inspected_scope=["integrations/antigravity/"],
            evidence_inspected=["env-1"],
            findings=[],
        )
        res_blank_auth = healer.run_repair_loop(
            initial_sha=NEXT_SHA,
            evaluate_fn=lambda _s: {"passed": True, "author_context_id": "   "},
            repair_fn=lambda _c, _fc, _e: {"new_sha": BASE_SHA, "regression_failed_prefix": True},
            nox_review_fn=lambda _s, _a: nox_other_author,
        )
        self.assertEqual(res_blank_auth["status"], "QUARANTINED")
        res_mismatch_auth = healer.run_repair_loop(
            initial_sha=NEXT_SHA,
            evaluate_fn=lambda _s: {"passed": True, "author_context_id": "ctx-real-author"},
            repair_fn=lambda _c, _fc, _e: {"new_sha": BASE_SHA, "regression_failed_prefix": True},
            nox_review_fn=lambda _s, _a: nox_other_author,
        )
        self.assertEqual(res_mismatch_auth["status"], "QUARANTINED")

        # NOX-R5-011: Workflow stop-condition guards and canonical recovery-capsule schema loading
        repair_wf = (ANTIGRAVITY_ROOT / "workflows" / "self_healing_repair.py").read_text(encoding="utf-8")
        feat_wf = (ANTIGRAVITY_ROOT / "workflows" / "feature_delivery.py").read_text(encoding="utf-8")
        rec_wf = (ANTIGRAVITY_ROOT / "workflows" / "recovery_reconcile.py").read_text(encoding="utf-8")
        self.assertIn("non_repairable_classes", repair_wf)
        self.assertIn('writer_res.get("status") != "READY"', repair_wf)
        self.assertIn('writer_res.get("status") != "READY"', feat_wf)
        self.assertIn("recovery-capsule.schema.json", rec_wf)

        # NOX-R5-012: _wait_for_health retries transient URLError and fails cleanly on timeout
        attempts = {"n": 0}

        def _flaky_requester(_url: str) -> tuple[int, bytes]:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise urllib.error.URLError("Connection refused")
            return 200, b'{"status":"ok"}'

        self.assertEqual(_wait_for_health("http://127.0.0.1:9999", retries=5, delay_seconds=0.0, requester=_flaky_requester), 200)
        self.assertEqual(attempts["n"], 3)
        with self.assertRaises(RuntimeError):
            _wait_for_health(
                "http://127.0.0.1:9999",
                retries=2,
                delay_seconds=0.0,
                requester=lambda _u: (_ for _ in ()).throw(urllib.error.URLError("refused")),
            )

        # NOX-R5-013: select_skills_for_mission fails closed on unknown profile/zero SHA/bad slug; verify_plugin_package checks enabled:true
        import shutil
        with self.assertRaises(AuthorityError):
            select_skills_for_mission("nonexistent_stack", skill_source_sha=BASE_SHA)
        with self.assertRaises(AuthorityError):
            select_skills_for_mission("php_laravel", skill_source_sha=ZERO_SHA40)
        with self.assertRaises(AuthorityError):
            select_skills_for_mission("php_laravel", skill_source_sha=SKILL_REGISTRY_SHA, extra_specialists=["../evil"])
        with self.assertRaises(AuthorityError):
            select_skills_for_mission("php_laravel", skill_source_sha=BASE_SHA)
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            fake_plugin = troot / "plugins" / "kirion-forge"
            shutil.copytree(PLUGIN_ROOT, fake_plugin)
            (troot / ".agents").mkdir(parents=True)
            (troot / ".agents" / "plugins.json").write_text('{"entries": [{"path": "plugins"}]}', encoding="utf-8")
            hooks_file = fake_plugin / "hooks.json"
            hdata = json.loads(hooks_file.read_text(encoding="utf-8"))
            hdata["kirion-forge-safety-gate"]["enabled"] = False
            hooks_file.write_text(json.dumps(hdata), encoding="utf-8")
            with self.assertRaises(AuthorityError):
                verify_plugin_package(fake_plugin, troot)

        # NOX-R5-014: Antigravity-QA boundary check denies production files containing 'test' substring
        qa_writer_pkt = make_valid_packet("R5-QA", persona="Antigravity-QA", formal_role="Code Writer", owned_paths=["src/"])
        for prod_path in ("src/attestation.py", "src/latest_billing.py"):
            with self.assertRaises(PolicyViolationError):
                assert_paths_within_ownership(qa_writer_pkt, [prod_path])
        self.assertEqual(
            assert_paths_within_ownership(qa_writer_pkt, ["src/test_billing.py", "src/tests/auth.py", "src/BillingTests.cs"]),
            ["src/test_billing.py", "src/tests/auth.py", "src/BillingTests.cs"],
        )


if __name__ == "__main__":
    unittest.main()
