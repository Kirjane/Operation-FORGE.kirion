"""Contract validation and canonical identity regression tests (synthetic fixtures only)."""
from __future__ import annotations

import copy
import json
import unittest

from integrations.antigravity.factory.authority import AuthorityError, load_schema, verify_mission_packet
from integrations.antigravity.factory.mission_contract import (
    contract_digest, contract_projection, digest_json, parse_mission_packet, validate_mission_contract,
)
from integrations.antigravity.factory.policy import assert_paths_within_ownership, assert_operation_allowed


def make_contract():
    return {
        "schema_version": 2, "mission_id": "FIXTURE-READ", "run_id": "run-read",
        "authorization_ref": "FORGE-AUTH-fixture", "verifier": "Engineer:Kirch-Ivan-Balite",
        "repo_id": 42, "repo_name": "fixture/repository", "base_sha": "a" * 40,
        "permitted_branch": "feat/read-contract", "project_origin": "BROWNFIELD",
        "work_mode": "DISCOVERY", "contract_refs": ["docs/contract.md"],
        "acceptance_criteria": ["Report pinned source"], "cognition_hash": None,
        "selected_skills": {"skill_source_sha": "b" * 40, "files": ["docs/skill.md"]},
        "assigned_persona": "Antigravity-Maintainer", "formal_role": "Maintainer",
        "owned_paths": [], "excluded_paths": ["docs/private"], "depends_on": [],
        "risk_class": "RISK-0", "required_gates": ["G00", "G01", "G04", "G13", "G15"],
        "budget": {"max_parallel_writers": 3, "max_parallel_reviewers": 3, "max_repair_cycles": 2,
                   "max_identical_retries": 2, "max_nesting_depth": 2, "max_wall_seconds": 60},
        "stop_conditions": ["SHA drift"], "allowed_operations": ["READ"],
        "delivery_destination": "fixture-only", "revision": 1, "previous_contract_sha256": None,
        "revision_reason": "Initial fixture contract",
        "objective": {"statement": "Inspect contract", "outcomes": [{
            "outcome_id": "source_report", "actor": "reader", "scenario": "inspect pinned source",
            "expected": "Report pinned source", "oracle_ids": ["source_observation"]}], "non_goals": ["No remote effects"]},
        "source_authorities": [{"source_id": "contract", "repository_id": 42,
                                "repository_name": "fixture/repository", "commit_sha": "a" * 40,
                                "scope": ["docs"], "authority_kind": "FUNCTIONAL"}],
        "oracles": [{"oracle_id": "source_observation", "outcome_ids": ["source_report"], "gate_id": "G01",
                     "source_id": "contract", "path": "docs/contract.md", "blob_sha": "c" * 40,
                     "command_argv": None, "fixture_sha256": None, "target_profile": "SYNTHETIC",
                     "environment": "fixture", "expected_observation": "Pinned source read",
                     "evidence_type": "SOURCE", "minimum_evidence_level": "E1",
                     "negative_control": "Wrong blob fails", "evaluation_kind": "REVIEWED_OBSERVATION"}],
        "required_capabilities": [{"capability_id": "repository_read", "operation": "READ",
                                   "scope": ["docs"], "environment": "fixture", "independence_required": False}],
        "cognition": {"mode": "OMITTED", "brain_run_id": None, "context_sha256": None,
                      "manifest_ref": None, "target_binding": None, "reason": "Optional fixture read"},
        "authority": {"issuer_actor_id": 123, "issuer_role": "Engineer", "directive_ref": "FORGE-AUTH-fixture",
                      "directive_sha256": "d" * 64, "grant_scope": ["READ"], "parent_grant_ref": None,
                      "permitted_revision_fields": ["objective"], "source_precedence": ["contract"],
                      "brain_required": False},
    }


def historical_packet():
    packet = make_contract()
    fields = load_schema("mission-packet.schema.json")["properties"]
    packet = {key: value for key, value in packet.items() if key in fields}
    packet.update(schema_version=1, cognition_hash="c" * 64, owned_paths=["docs"])
    return packet


class MissionContractTests(unittest.TestCase):
    def test_strict_json_ingress(self):
        packet = make_contract()
        raw = json.dumps(packet)
        self.assertEqual(parse_mission_packet(raw), packet)
        for bad in (raw.replace('"revision": 1', '"revision": 1, "revision": 1'),
                    raw.replace('"statement": "Inspect contract"', '"statement": "Inspect contract", "statement": "forged"'),
                    raw.replace('"repo_id": 42', '"repo_id": NaN'),
                    raw.replace('"repo_id": 42', '"repo_id": 1e999'),
                    raw.replace('"schema_version": 2', '"schema_version": 3'),
                    raw.replace('"schema_version": 2', '"schema_version": true'),
                    raw[:-1] + ', "unknown": true}', b"\xff", "[]"):
            with self.subTest(raw=str(bad)[:80]), self.assertRaises(AuthorityError):
                parse_mission_packet(bad)

    def test_contract_digest_excludes_run_only_and_normalizes_declared_sets(self):
        packet = make_contract()
        original = contract_digest(packet)
        reordered = copy.deepcopy(packet)
        reordered["run_id"] = "run-other"
        reordered["required_gates"].reverse()
        self.assertEqual(contract_digest(reordered), original)
        self.assertNotIn("run_id", contract_projection(packet))
        for field, value in (("repo_id", 43), ("base_sha", "e" * 40), ("permitted_branch", "feat/other"),
                             ("excluded_paths", ["docs/secret"]), ("revision_reason", "Different reason")):
            changed = copy.deepcopy(packet)
            changed[field] = value
            if field == "repo_id":
                changed["source_authorities"][0]["repository_id"] = value
            self.assertNotEqual(contract_digest(changed), original)
        changed = copy.deepcopy(packet)
        changed["objective"]["statement"] = "Different objective"
        self.assertNotEqual(contract_digest(changed), original)
        changed = copy.deepcopy(packet)
        changed["oracles"][0]["blob_sha"] = "e" * 40
        self.assertNotEqual(contract_digest(changed), original)

    def test_argv_order_is_authorized(self):
        packet = make_contract()
        packet["allowed_operations"].append("RUN_GATE")
        packet["authority"]["grant_scope"].append("RUN_GATE")
        packet["required_capabilities"].append({"capability_id": "local_command_execution", "operation": "RUN_GATE",
            "scope": ["docs"], "environment": "fixture", "independence_required": False})
        argv = ["python", "docs/test.py", "--first", "--second"]
        packet["oracles"][0].update(evaluation_kind="COMMAND", command_argv=argv)
        packet["gate_commands"] = {"G01": argv}
        initial = contract_digest(packet)
        packet["oracles"][0]["command_argv"] = ["python", "docs/test.py", "--second", "--first"]
        packet["gate_commands"]["G01"] = packet["oracles"][0]["command_argv"]
        self.assertNotEqual(contract_digest(packet), initial)

    def test_semantic_constraints(self):
        cases = [
            {"repo_id": 43}, {"permitted_branch": "main"}, {"revision": 2},
            {"owned_paths": ["../escape"]}, {"excluded_paths": ["docs/../private"]},
            {"acceptance_criteria": ["Different expectation"]}, {"required_capabilities": []},
            {"required_gates": ["G00", "G15"]}, {"depends_on": ["FIXTURE-READ"]},
            {"required_gates": ["G00", "G01", "G04", "G13", "G15", "G15"]},
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(AuthorityError):
                validate_mission_contract({**make_contract(), **changes})
        for key, value in (("path", "other/test.md"), ("source_id", "missing"), ("blob_sha", "0" * 40),
                           ("outcome_ids", ["missing"]), ("minimum_evidence_level", "E0"),
                           ("target_profile", "REAL"), ("gate_id", "G07")):
            packet = make_contract()
            packet["oracles"][0][key] = value
            with self.subTest(key=key), self.assertRaises(AuthorityError):
                validate_mission_contract(packet)
        packet = make_contract()
        packet["required_capabilities"][0]["scope"] = ["docs/contract.md"]
        with self.assertRaises(AuthorityError):
            validate_mission_contract(packet)
        packet = make_contract()
        packet["authority"]["brain_required"] = True
        with self.assertRaises(AuthorityError):
            validate_mission_contract(packet)

    def test_cognition_target_binding(self):
        packet = make_contract()
        packet["cognition_hash"] = "f" * 64
        packet["cognition"] = {"mode": "INHERITED", "brain_run_id": "brain-fixture",
            "context_sha256": "f" * 64, "manifest_ref": "fixture-manifest",
            "target_binding": digest_json({key: packet[key] for key in
                ("repo_id", "repo_name", "base_sha", "permitted_branch")}), "reason": None}
        validate_mission_contract(packet)
        packet["base_sha"] = "e" * 40
        with self.assertRaises(AuthorityError):
            validate_mission_contract(packet)

    def test_policy_exclusions_and_actor_override(self):
        packet = make_contract()
        packet.update(assigned_persona="Antigravity-Jane", formal_role="Code Writer",
                      owned_paths=["docs"], allowed_operations=["READ", "WRITE_OWNED"])
        packet["authority"]["grant_scope"] = packet["allowed_operations"]
        packet["required_capabilities"].append({"capability_id": "scoped_worktree_write", "operation": "WRITE_OWNED",
            "scope": ["docs"], "environment": "fixture", "independence_required": False})
        validate_mission_contract(packet)
        self.assertEqual(assert_paths_within_ownership(packet, ["docs/public.md"]), ["docs/public.md"])
        for path in ("docs/private/file.md", "other/file.md", "AGENTS.md"):
            with self.assertRaises(AuthorityError):
                assert_paths_within_ownership(packet, [path], allow_protected_governance=True)
        with self.assertRaises(AuthorityError):
            assert_operation_allowed(packet, "READ", actor_persona="Antigravity-Maintainer")

    def test_historical_protocol_no_downgrade(self):
        packet = historical_packet()
        self.assertEqual(verify_mission_packet(packet), packet)
        self.assertEqual(parse_mission_packet(json.dumps(packet)), packet)
        with self.assertRaises(AuthorityError):
            verify_mission_packet(packet, trusted_verifiers=set())
        with self.assertRaises(AuthorityError):
            verify_mission_packet(make_contract())

    def test_standard_and_fallback_schema(self):
        from jsonschema import Draft202012Validator  # required for qualification, not a runtime dependency
        schema = load_schema("mission-packet-v2.schema.json")
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(make_contract())
        invalid = {**make_contract(), "unknown": 1}
        self.assertFalse(validator.is_valid(invalid))
        with self.assertRaises(AuthorityError):
            validate_mission_contract(invalid)
        # Cross-field semantics must still be enforced after either validator.
        invalid = {**make_contract(), "revision": 2}
        self.assertTrue(validator.is_valid(invalid))
        with self.assertRaises(AuthorityError):
            validate_mission_contract(invalid)


if __name__ == "__main__":
    unittest.main()
