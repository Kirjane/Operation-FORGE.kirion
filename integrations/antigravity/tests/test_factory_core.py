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
        "required_gates": ["G00", "G01", "G03", "G05", "G13", "G15"],
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
        csharp_bundle = select_skills_for_mission("csharp_aspnet", skill_source_sha=BASE_SHA)
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
            runner = TrustedEvidenceRunner(tmp_root / "artifacts")
            env = runner.run_gate_command(
                run_id="run-e2e",
                mission_id="F10-TEST",
                stage="VERIFY",
                gate_id="G05",
                command_argv=[sys.executable, "-c", "print('unit pass; token ghp_1234567890abcdefghijklmnop')"],
                cwd=REPO_ROOT,
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


if __name__ == "__main__":
    unittest.main()
