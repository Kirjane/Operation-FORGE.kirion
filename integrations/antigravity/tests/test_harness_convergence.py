"""Convergence contract tests using exact Forge pins and disposable target Git.

These require an actual clone containing the integrated immutable source
objects. No fixture receipt is a native host attestation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from integrations.antigravity.factory import REPO_ROOT
from integrations.antigravity.factory.authority import AuthorityError, load_schema
from integrations.antigravity.factory.dispatch_preflight import ContractJournal
from integrations.antigravity.factory.dispatcher import select_skills_for_mission, FleetDispatcher
from integrations.antigravity.factory.fenced_file import supported
from integrations.antigravity.factory.mission_contract import canonical_json, contract_digest, digest_json
from integrations.antigravity.factory.native_boundary import FixtureNativeBoundary, WORKFLOWS, native_workflow_entry
from integrations.antigravity.factory.scoped_fixture import ScopedGitFixtureAdapter
from integrations.antigravity.factory.skill_loading import FixtureSkillRuntime
from integrations.antigravity.factory.skill_registry import PinnedGitSources, SkillRegistry, digest
from integrations.antigravity.factory.supervised import supervised_handoff, inspect_supervised_candidate
from integrations.antigravity.tests.test_dispatch_preflight import make_grant, timestamp
from integrations.antigravity.tests.test_mission_contract import make_contract

REGISTRY = "05da5f962c87e5ab7cc4b956ecbbb2d4e8a0de2b"
FRONTEND_SOURCE = "91b79a901f91a218c0f6fcde8f1babe1918af3f6"
FORGE_REPO = "Kirjane/Operation-FORGE.kirion"
FORGE_ID = 1377058358
DOMAINS = ["integration", "architecture"]
REFERENCES = ["standards/frontend/README.md",
              "standards/frontend/frontend-architecture.md",
              "standards/frontend/implementation-workflow.md",
              "standards/frontend/product-integration.md",
              "standards/frontend/acceptance-and-evidence.md"]
SCOPE = ["standards/frontend/activation.json", "integrations/antigravity/profiles/frontend_web.json", *REFERENCES]


class HarnessConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.sources = PinnedGitSources({FORGE_ID: (FORGE_REPO, REPO_ROOT)})
        self.registry = SkillRegistry(self.sources, repository_id=FORGE_ID, repository_name=FORGE_REPO,
                                     registry_commit=REGISTRY)
        self.adapter = ScopedGitFixtureAdapter(grants={}, trusted_verifiers=set(), frontend_fixture=True)
        self.addCleanup(self.adapter.close)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.journal = ContractJournal(Path(temp.name) / "contract.sqlite")
        packet = make_contract()
        packet.update(base_sha=self.adapter.base_sha, assigned_persona="Antigravity-Iris",
                      formal_role="Code Writer", owned_paths=[self.adapter.owned_file],
                      allowed_operations=["READ", "WRITE_OWNED"])
        packet["source_authorities"][0]["commit_sha"] = self.adapter.base_sha
        packet["oracles"][0]["blob_sha"] = self.adapter.oracle_blob_sha
        packet["source_authorities"].append({"source_id": "frontend-standard", "repository_id": FORGE_ID,
            "repository_name": FORGE_REPO, "commit_sha": FRONTEND_SOURCE, "scope": SCOPE,
            "authority_kind": "CONSTRAINT"})
        packet["authority"]["source_precedence"] = ["contract", "frontend-standard"]
        packet["authority"]["grant_scope"] = packet["allowed_operations"]
        packet["required_capabilities"][0]["scope"] = ["docs", *SCOPE]
        packet["required_capabilities"].append({"capability_id": "scoped_worktree_write",
            "operation": "WRITE_OWNED", "scope": [self.adapter.owned_file], "environment": "fixture",
            "independence_required": False})
        packet["selected_skills"] = select_skills_for_mission("frontend_web", skill_source_sha=REGISTRY,
            sources=self.sources, host="fixture")
        content = "Fixture stage context café"
        document = {"path": "brain/context.md", "bytes": len(content.encode()),
                    "sha256": hashlib.sha256(content.encode()).hexdigest(), "depth": 0, "source": "REQUIRED_SEED"}
        manifest = {"status": "RESOLVED", "missing_required": [], "required_not_loaded": [],
                    "documents": [document], "document_count": 1, "total_bytes": document["bytes"],
                    "document_budget": 24, "byte_budget": 65536}
        checkpoint = {"stage": "PRE_IMPLEMENTATION", "effective_stage": "PRE_IMPLEMENTATION",
                      "context_sha256": digest(manifest), "context_manifest": manifest}
        checkpoint["checkpoint_sha256"] = digest(checkpoint)
        packet["cognition"] = {"mode": "INHERITED", "brain_run_id": "fixture-brain",
            "context_sha256": digest(manifest), "manifest_ref": "fixture-context",
            "target_binding": digest_json({k: packet[k] for k in ("repo_id", "repo_name", "base_sha", "permitted_branch")}),
            "reason": None}
        packet["cognition_hash"] = digest(manifest)
        packet["authority"]["brain_required"] = True
        self.packet = packet
        self.cfg = {"profile": "frontend_web", "host": "fixture", "stage": "PRE_IMPLEMENTATION",
            "task": "general", "run_id": packet["run_id"], "revision": packet["revision"],
            "actor_id": "native:fixture-iris", "host_id": "fixture-host", "context_id": "fixture-context",
            "attempt_ordinal": 1, "max_context_bytes": 65536, "include_routes": False,
            "frontend_domains": DOMAINS, "brain_run_id": "fixture-brain",
            "brain_stage_context": {"checkpoint": checkpoint, "documents": [{**document, "content": content}]}}

    def compose(self, *, actor_changes=None, grant_changes=None, config_changes=None):
        packet = self.packet
        contract = contract_digest(packet)
        grant = make_grant(packet)
        grant.update(actor_id="native:fixture-iris", identity_provider="native")
        grant.update(grant_changes or {})
        # Separate fixed test identity observation, not derived from supplied grant.
        actor = {"actor_id": "native:fixture-iris", "host_id": "fixture-host", "worker_id": "fixture-worker",
                 "identity_provider": "native", "persona": "Antigravity-Iris", "formal_role": "Code Writer",
                 "contract_sha256": contract, "revision": packet["revision"], "run_id": packet["run_id"],
                 "fixture_only": True, "observed_at_utc": timestamp(-1), "valid_until_utc": timestamp(3600)}
        actor.update(actor_changes or {})
        cfg = dict(self.cfg, **(config_changes or {}))
        self.runtime = FixtureSkillRuntime(self.registry, configs={contract: cfg}, signing_key=b"k" * 32)
        self.adapter.configure_fixture_grants({contract: grant}, {packet["verifier"]})
        self.adapter.configure_skill_context(self.runtime, observed_actors={contract: actor})
        self.raw = canonical_json(packet)
        return FixtureNativeBoundary(self.journal, self.adapter), grant

    def unchanged(self):
        self.assertEqual((self.adapter.repo / self.adapter.owned_file).read_bytes(), b"before\n")
        self.assertTrue(self.journal.verify_hash_chain())

    def test_actual_frontend_reference_reads_before_fenced_effect_and_custody(self):
        boundary, grant = self.compose()
        plan = self.runtime.prepare(self.packet, grant=grant, require_consumable=True).summary()
        self.assertEqual(plan["frontend_activation"]["required_paths"], REFERENCES)
        self.assertEqual(plan["frontend_activation"]["domains"], ["architecture", "integration", "evidence"])
        self.assertEqual(len([s for s in plan["selected"] if s["kind"] == "skill"]), 5)
        self.assertEqual(len([s for s in plan["selected"] if s["kind"] == "reference"]), 5)
        self.assertEqual(plan["total_context_bytes"], plan["prior_context_bytes"] + plan["skill_bytes"] + plan["reference_bytes"])
        result = boundary.execute("feature_delivery", self.raw)
        if not supported():
            self.assertEqual(result["status"], "BLOCKED")
            self.unchanged()
            return
        self.assertEqual(result["status"], "COMPLETED", result)
        self.assertEqual(result["skill_consumption_status"], "FIXTURE_CONSUMED")
        outcome = result["result"]["worker_result"]
        self.assertEqual(outcome["changed_paths"], [self.adapter.owned_file])
        self.assertEqual((self.adapter.repo / self.adapter.owned_file).read_bytes(), b"after\n")
        self.assertEqual(outcome["oracle_observation"]["blob_sha"], self.adapter.oracle_blob_sha)
        self.assertEqual(outcome["oracle_observation"]["sha256"], hashlib.sha256(b"pinned acceptance source\n").hexdigest())
        self.assertFalse(outcome["oracle_observation"]["independent"])
        receipt = result["result"]["skill_consumption"]
        self.assertEqual([e["source"]["path"] for e in receipt["loaded"] if e["id"].startswith("frontend-standard-")], REFERENCES)
        self.assertFalse(receipt["native_loading_verified"])
        reservation = result["reservation_id"]
        self.assertEqual(boundary.inspect_consumption(self.raw, reservation)["status"], "FIXTURE_CONSUMPTION_VERIFIED")
        self.assertEqual(boundary.inspect_recovery(self.raw, reservation)["observation"]["changed_paths"], [self.adapter.owned_file])
        self.assertEqual(boundary.inspect_assurance(self.raw, reservation)["overall_status"], "BLOCKED")
        self.assertFalse(boundary.inspect_delivery(self.raw, reservation)["promotion_authorized"])
        self.assertTrue(boundary.execute("feature_delivery", self.raw)["cached"])
        self.assertTrue(self.journal.verify_hash_chain())

    def test_wrong_actor_denies_before_effect(self):
        boundary, _ = self.compose(actor_changes={"actor_id": "native:other"})
        self.assertEqual(boundary.execute("feature_delivery", self.raw)["status"], "BLOCKED")
        self.unchanged()

    def test_stale_actor_denies_before_effect(self):
        boundary, _ = self.compose(actor_changes={"valid_until_utc": timestamp(-1)})
        self.assertEqual(boundary.execute("feature_delivery", self.raw)["status"], "BLOCKED")
        self.unchanged()

    def test_wrong_owned_path_denies_before_effect(self):
        self.packet["owned_paths"] = ["backend/payment.ts"]
        self.packet["required_capabilities"][1]["scope"] = self.packet["owned_paths"]
        boundary, _ = self.compose()
        self.assertEqual(boundary.execute("feature_delivery", self.raw)["status"], "BLOCKED")
        self.unchanged()

    def test_missing_standard_authority_denies(self):
        self.packet["source_authorities"][1]["scope"] = SCOPE[:-1]
        boundary, _ = self.compose()
        self.assertEqual(boundary.execute("feature_delivery", self.raw)["status"], "BLOCKED")
        self.unchanged()

    def test_advisory_standard_scope_cannot_satisfy_required_reference(self):
        self.packet['source_authorities'][1]['scope'] = SCOPE[:-1]
        self.packet['source_authorities'].append({**self.packet['source_authorities'][1],
            'source_id': 'advisory-standard', 'scope': SCOPE[-1:], 'authority_kind': 'REFERENCE'})
        self.packet['authority']['source_precedence'].append('advisory-standard')
        boundary, _ = self.compose()
        self.assertEqual(boundary.execute('feature_delivery', self.raw)['status'], 'BLOCKED')
        self.unchanged()

    def test_required_standard_budget_denies(self):
        boundary, _ = self.compose(config_changes={"max_reference_files": 1})
        self.assertEqual(boundary.execute("feature_delivery", self.raw)["status"], "BLOCKED")
        self.unchanged()

    def test_unknown_domains_deny(self):
        boundary, _ = self.compose(config_changes={"frontend_domains": ["invented"]})
        self.assertEqual(boundary.execute("feature_delivery", self.raw)["status"], "BLOCKED")
        self.unchanged()

    def test_forged_consumption_cannot_authorize_write(self):
        boundary, _ = self.compose()
        if not supported():
            self.assertEqual(boundary.execute("feature_delivery", self.raw)["status"], "BLOCKED")
            self.unchanged()
            return
        real = self.runtime.consume
        def forged(prepared, consumer, packet):
            result, receipt = real(prepared, consumer, packet)
            receipt["signature"] = "0" * 64
            return result, receipt
        with patch.object(self.runtime, "consume", side_effect=forged):
            self.assertEqual(boundary.execute("feature_delivery", self.raw)["status"], "NO_EFFECT")
        self.unchanged()

    def test_supervised_handoff_retrieves_but_never_loads_or_activates(self):
        self.packet["selected_skills"] = select_skills_for_mission("frontend_web", skill_source_sha=REGISTRY,
            sources=self.sources, extra_specialists=["kirion-session-host"])
        cfg = dict(self.cfg, host="chatgpt", required_extra=["kirion-session-host"])
        handoff = supervised_handoff(canonical_json(self.packet), self.registry, cfg, workflow="feature_delivery")
        self.assertEqual(handoff["next_action"], "EXECUTOR_RECONCILE_AUTHORIZED_ROUTE_OR_RECORD_BLOCKER")
        self.assertFalse(handoff["operator_relay_required"])
        self.assertEqual(handoff["execution_route"], "NOT_ESTABLISHED")
        self.assertEqual(handoff["status"], "SUPERVISED_HANDOFF_PREPARED")
        self.assertEqual(handoff["context"]["status"], "RETRIEVED_NOT_LOADED")
        self.assertTrue(handoff["context"]["documents"])
        self.assertTrue(handoff["context"]["brain_documents"])
        self.assertFalse(handoff["native_loading_verified"])
        self.assertFalse(handoff["write_authorized_by_harness"])
        self.assertFalse(handoff["remote_invoked"])

    def test_registry_and_receipt_schema_standard_parity(self):
        from jsonschema import Draft202012Validator
        from integrations.antigravity.factory.authority import validate_contract
        raw, _ = self.sources.read(FORGE_ID, FORGE_REPO, REGISTRY, "arsenal/manifest.json", max_bytes=524288)
        manifest = json.loads(raw)
        schema = load_schema("skill-registry.schema.json")
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(manifest)
        validate_contract(manifest, "skill-registry.schema.json")
        boundary, grant = self.compose()
        prepared = self.runtime.prepare(self.packet, grant=grant, require_consumable=True)
        _, receipt = self.runtime.consume(prepared, lambda p, c: {"actual_reads": [c.read(n) for n in c.available_ids()] != []}, self.packet)
        receipt_schema = load_schema("skill-consumption.schema.json")
        Draft202012Validator.check_schema(receipt_schema)
        Draft202012Validator(receipt_schema).validate(receipt)
        validate_contract(receipt, "skill-consumption.schema.json")
        for record, name, sch in ((manifest, "skill-registry.schema.json", schema),
                                  (receipt, "skill-consumption.schema.json", receipt_schema)):
            invalid = copy.deepcopy(record)
            if name.startswith("skill-registry"):
                invalid["frontend_activation"]["declaration"]["sha256"] = "not-a-digest"
            else:
                invalid["native_loading_verified"] = True
            self.assertFalse(Draft202012Validator(sch).is_valid(invalid))
            with self.assertRaises(AuthorityError):
                validate_contract(invalid, name)

    def test_native_workflows_preserve_stages_without_activation(self):
        for workflow in WORKFLOWS:
            result = native_workflow_entry(workflow, "chatgpt", {"authorized": True})
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(result["supervised_stages"])
            self.assertTrue(all(not stage["native_invoked"] for stage in result["supervised_stages"]))
            self.assertFalse(result["invoked"])


if __name__ == "__main__":
    unittest.main()
