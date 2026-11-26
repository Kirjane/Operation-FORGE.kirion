"""W4 adversarial assurance regressions, exclusively nonpromotable fixtures."""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from integrations.antigravity.factory.assurance import (FixtureAssuranceResolver, signed_material,
                                                        execution_projection, evaluate_applicable_receipts)
from integrations.antigravity.factory.delivery import NairuDeliveryBroker
from integrations.antigravity.factory.dispatch_preflight import ContractJournal, FixtureDispatchAdapter
from integrations.antigravity.factory.dispatcher import FleetDispatcher
from integrations.antigravity.factory.evidence import TrustedEvidenceRunner, FORGE_LEVEL_TO_CERTAINTY_CEILING
from integrations.antigravity.factory.mission_contract import canonical_json, contract_digest, digest_json
from integrations.antigravity.factory.recovery import RecoveryManager
from integrations.antigravity.tests.test_dispatch_preflight import make_grant, make_observation, timestamp
from integrations.antigravity.tests.test_mission_contract import make_contract


class AssuranceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.journal = ContractJournal(self.root / "contract.sqlite")
        self.runner = TrustedEvidenceRunner(self.root / "artifacts")
        self.dispatcher = FleetDispatcher()
        self.packet = make_contract()
        self.packet["objective"]["outcomes"][0]["oracle_ids"] = []
        exemplar = copy.deepcopy(self.packet["oracles"][0])
        self.packet["oracles"] = []
        for gid, kind, level in (("G00", "SOURCE", "E1"), ("G01", "SOURCE", "E1"),
                                 ("G04", "SECURITY", "E4"), ("G13", "INTEGRATION", "E4"),
                                 ("G15", "INTEGRATION", "E4")):
            oracle = {**exemplar, "oracle_id": "oracle-" + gid, "gate_id": gid,
                      "evidence_type": kind, "minimum_evidence_level": level}
            self.packet["oracles"].append(oracle)
            self.packet["objective"]["outcomes"][0]["oracle_ids"].append(oracle["oracle_id"])
        self.raw = canonical_json(self.packet)
        self.digest = contract_digest(self.packet)
        self.grant = make_grant(self.packet)
        self.adapter = FixtureDispatchAdapter(grants={self.digest: self.grant},
            trusted_verifiers={self.packet["verifier"]}, observe=lambda p: make_observation(p, self.grant),
            handler=lambda p: {"effect": "READ_ONLY"})
        result = self.dispatcher.dispatch_worker(self.raw, journal=self.journal, fixture_adapter=self.adapter)
        self.assertEqual(result["status"], "COMPLETED")
        self.reservation = result["reservation_id"]
        self.target = {"repo_id": 42, "repo_name": "fixture/repository", "branch": "feat/read-contract",
                       "kind": "source-tree", "profile": "SYNTHETIC", "environment": "fixture",
                       "data_authority": "fixture-only", "cwd": str(self.root), "device_id": None,
                       "executable_sha256": None, "signing_policy_sha256": None}
        self.plan = {
            "contract_sha256": self.digest, "revision": 1, "reservation_id": self.reservation,
            "grant_sha256": digest_json(self.grant), "worker_actor_id": self.grant["actor_id"],
            "run_id": self.packet["run_id"], "attempt_result_sha256": digest_json(result["result"]),
            "adapter_binding": {"kind": "CALLBACK_FIXTURE"},
            "candidate_sha": "b" * 40, "tree_sha": "e" * 40, "target": self.target,
            "author_actor_id": self.grant["actor_id"], "author_context_id": "writer-context",
            "observed_at_utc": timestamp(-1), "expires_at_utc": timestamp(120), "oracles": {},
        }
        for o in self.packet["oracles"]:
            target = copy.deepcopy(self.target)
            if o["gate_id"] == "G15":
                target.update(kind="device-fixture", device_id="device-A",
                              executable_sha256="c" * 64, signing_policy_sha256="d" * 64)
            comparisons = {"docs/contract.md": "c" * 40, "docs/second.md": "f" * 40} if o["evidence_type"] == "SOURCE" else {}
            self.plan["oracles"][o["oracle_id"]] = {
                "oracle_sha256": digest_json(o), "source_sha256": digest_json(self.packet["source_authorities"][0]),
                "oracle_blob_sha": o["blob_sha"], "stage": "PRE_DELIVERY", "target": target,
                "runtime_sha256": "e" * 64, "environment_versions": {"fixture": "1"},
                "source_comparisons": comparisons, "observed_source_comparisons": copy.deepcopy(comparisons),
                "observation_argv": ["fixture-observation", o["oracle_id"]],
                "expected": {"status": 403, "reason": "OWNERSHIP_DENIED"},
                "negative_expected": {"status": 403, "reason": "WRONG_TARGET"},
                "review_scope": ["docs"], "known_findings": {}, "authorized_dispositions": {},
                "finding_fix_oracles": {"P1-01": ["oracle-G01"]},
            }
        self.issuers = {}
        for issuer, role, actor, context, key in (
            ("writer", "WRITER", self.grant["actor_id"], "writer-context", b"w" * 32),
            ("reviewer", "REVIEWER", "reviewer-actor", "reviewer-context", b"r" * 32),
            ("acceptance", "ACCEPTANCE", "acceptance-actor", "acceptance-context", b"a" * 32),
        ):
            self.issuers[issuer] = {"role": role, "actor_id": actor, "context_id": context, "key": key,
                                    "revoked": False, "valid_from_utc": timestamp(-60),
                                    "expires_at_utc": timestamp(3600), "contracts": [self.digest],
                                    "oracles": [o["oracle_id"] for o in self.packet["oracles"]], "max_level": "E5"}
        self.executions = {}
        self.resolver = self.make_resolver()

    def observation(self):
        return {"candidate_sha": self.plan["candidate_sha"], "tree_sha": self.plan["tree_sha"],
                "oracles": {oid: {k: c[k] for k in ("target", "runtime_sha256", "environment_versions",
                    "source_sha256", "oracle_blob_sha", "observed_source_comparisons")}
                    for oid, c in self.plan["oracles"].items()}}

    def make_resolver(self, observe=None):
        observed = copy.deepcopy(self.observation())
        return FixtureAssuranceResolver(plans={self.reservation: self.plan}, issuers=self.issuers,
                    artifact_store_root=self.runner.artifact_store_root,
                    observe=observe or (lambda _: copy.deepcopy(observed)),
                    resolve_execution=lambda reservation, oracle, nonce:
                        copy.deepcopy(self.executions.get((reservation, oracle, nonce))))

    def sign(self, record, issuer=None):
        record["signature"] = hmac.new(self.issuers[issuer or record["issuer_id"]]["key"],
                                       signed_material(record), hashlib.sha256).hexdigest()
        return record

    def issuer_fields(self, issuer):
        return {"issuer_id": issuer, "issuer_actor_id": self.issuers[issuer]["actor_id"],
                "issuer_context_id": self.issuers[issuer]["context_id"], "nonce": uuid.uuid4().hex,
                "issued_at_utc": timestamp(), "expires_at_utc": timestamp(60)}

    def receipt(self, gate="G01", *, observed=None, negative=None, review=None, proofs=None,
                mutate_artifact=None, verdict="PASS", register_execution=True):
        o = next(o for o in self.packet["oracles"] if o["gate_id"] == gate)
        c = self.plan["oracles"][o["oracle_id"]]
        issuer = "reviewer" if gate == "G13" else "writer"
        record = {"schema_version": 1, "contract_sha256": self.digest, "revision": 1,
                  "repo_id": 42, "repo_name": self.packet["repo_name"], "base_sha": self.packet["base_sha"],
                  "branch": self.packet["permitted_branch"], "objective_sha256": digest_json(self.packet["objective"]),
                  "grant_sha256": self.plan["grant_sha256"], "reservation_id": self.reservation, "attempt_ordinal": 1,
                  "worker_actor_id": self.grant["actor_id"], "issuer_role": self.issuers[issuer]["role"],
                  "plan_sha256": digest_json(self.plan), "oracle_id": o["oracle_id"],
                  "oracle_sha256": digest_json(o), "source_sha256": c["source_sha256"], "outcome_ids": o["outcome_ids"],
                  "target": copy.deepcopy(c["target"]), "runtime_sha256": c["runtime_sha256"],
                  **self.issuer_fields(issuer)}
        artifact = {"schema_version": 1, "oracle_sha256": record["oracle_sha256"],
                    "source_sha256": record["source_sha256"], "target": c["target"],
                    "candidate_sha": self.plan["candidate_sha"], "tree_sha": self.plan["tree_sha"],
                    "runtime_sha256": c["runtime_sha256"], "nonce": record["nonce"],
                    "reservation_id": self.reservation, "outcome_ids": o["outcome_ids"],
                    "negative_scenario": o["negative_control"],
                    "observed": c["expected"] if observed is None else observed,
                    "negative_observed": c["negative_expected"] if negative is None else negative,
                    "source_comparisons": c["observed_source_comparisons"], "review": review,
                    "finding_proofs": proofs or {}}
        artifact = copy.deepcopy(artifact)
        if mutate_artifact:
            mutate_artifact(artifact)
        positive = artifact.pop("observed")
        negative = artifact.pop("negative_observed")
        path, size, digest = self.runner.capture_fixture_oracle_artifact(
            binding=artifact, observe_positive=lambda: positive, observe_negative=lambda: negative)
        level = o["minimum_evidence_level"]
        record["envelope"] = {
            "schema_version": 1, "run_id": self.packet["run_id"], "mission_id": self.packet["mission_id"],
            "stage": c["stage"], "gate_id": gate, "candidate_sha": self.plan["candidate_sha"],
            "tree_sha": self.plan["tree_sha"], "dirty": False, "command_argv": c["observation_argv"],
            "cwd": c["target"]["cwd"], "started_at_utc": self.plan["observed_at_utc"],
            "completed_at_utc": record["issued_at_utc"], "exit_code": 0, "status": verdict,
            "environment_versions": c["environment_versions"], "fixture_sha256": "0" * 64,
            "artifact_path": str(path), "artifact_size_bytes": size, "artifact_sha256": digest,
            "evidence_level": level, "evidence_type": o["evidence_type"],
            "provenance": "DIRECTLY_OBSERVED" if level == "E1" else "AUTOMATED",
            "certainty_ceiling": FORGE_LEVEL_TO_CERTAINTY_CEILING[level], "redacted": True}
        execution = execution_projection(record)
        record["execution_sha256"] = digest_json(execution)
        if register_execution:
            # This is trusted test composition, separate from the receipt
            # issuer. Ingress and sign() cannot create an observed execution.
            key = (record["reservation_id"], record["oracle_id"], record["nonce"])
            self.executions[key] = copy.deepcopy(execution)
        return self.sign(record)

    def record(self, receipt, resolver=None):
        return self.dispatcher.record_worker_evidence(self.raw, self.reservation, canonical_json(receipt),
                                                     journal=self.journal, resolver=resolver or self.resolver)

    def summary(self):
        return self.journal.evaluate_assurance(self.raw, self.reservation, self.resolver)

    def review(self, writer, findings=None):
        return {"schema_version": 1, "mission_id": self.packet["mission_id"],
                "frozen_sha": self.plan["candidate_sha"], "reviewer_context_id": "reviewer-context",
                "reviewer_persona": "Antigravity-Nox", "author_context_id": "writer-context",
                "inspected_scope": ["docs"], "evidence_inspected": writer, "findings": findings or [],
                "verdict": "PASS"}

    def complete(self):
        writer = []
        for gate in ("G00", "G01", "G04", "G15"):
            result = self.record(self.receipt(gate))
            self.assertEqual(result["status"], "RECORDED", result)
            writer.append(result["receipt_sha256"])
        review = self.record(self.receipt("G13", review=self.review(writer)))
        self.assertEqual(review["status"], "RECORDED", review)
        self.assertEqual(self.summary()["overall_status"], "PASS")
        return self.summary()["receipt_sha256s"]

    def decision(self, receipts, issuer="acceptance"):
        return self.sign({"schema_version": 1, "contract_sha256": self.digest, "revision": 1,
                          "reservation_id": self.reservation, "plan_sha256": digest_json(self.plan),
                          "candidate_sha": self.plan["candidate_sha"], "tree_sha": self.plan["tree_sha"],
                          "receipt_sha256s": sorted(receipts), "decision": "ACCEPT_FIXTURE",
                          **self.issuer_fields(issuer)})

    def accept(self, decision):
        return self.journal.record_assurance_decision(self.raw, self.reservation, canonical_json(decision), self.resolver)

    def test_complete_independent_fixture_and_delivery_denial(self):
        receipts = self.complete()
        decision = self.decision(receipts)
        result = self.accept(decision)
        self.assertEqual(result["status"], "FIXTURE_SUPPORTED", result)
        self.assertFalse(result["promotion_authorized"])
        self.assertEqual(result["actual_product_outcome"], "NOT_TESTED")
        self.assertEqual(self.accept(decision)["status"], "BLOCKED")
        reopened = ContractJournal(self.journal.db_path)
        self.assertTrue(reopened.verify_hash_chain())
        self.assertEqual(reopened.inspect_assurance_decision(self.raw, self.reservation, self.resolver)["status"],
                         "FIXTURE_SUPPORTED")
        recovery = RecoveryManager(reopened).inspect_contract_assurance(self.raw, self.reservation, self.resolver)
        self.assertFalse(recovery["replay_permitted"])
        self.assertEqual(recovery["assurance"]["status"], "FIXTURE_SUPPORTED")
        delivery = NairuDeliveryBroker.inspect_contract_delivery(self.raw, self.reservation,
                                                                   journal=reopened, resolver=self.resolver)
        self.assertEqual(delivery["status"], "BLOCKED")
        self.assertFalse(delivery["remote_invoked"])

    def test_missing_evidence_and_unavailable_resolver(self):
        self.assertIn("G13", self.summary()["missing_gates"])
        self.assertEqual(self.journal.evaluate_assurance(self.raw, self.reservation)["status"], "BLOCKED")
        self.assertEqual(self.accept(self.decision(["a" * 64]))["status"], "BLOCKED")

    def test_exact_scope_applies_to_both_pass_and_fail(self):
        for verdict in ("PASS", "FAIL"):
            for key, value in (("objective_sha256", "a" * 64), ("oracle_sha256", "a" * 64),
                               ("runtime_sha256", "a" * 64), ("source_sha256", "a" * 64),
                               ("reservation_id", "other"), ("outcome_ids", ["obsolete-journey"])):
                receipt = self.receipt(verdict=verdict)
                receipt[key] = value
                self.assertEqual(self.record(self.sign(receipt))["status"], "BLOCKED", (key, verdict))
        self.assertNotIn("G01", self.summary()["failed_gates"])
        self.assertIn("G01", self.summary()["missing_gates"])

    def test_wrong_device_signing_or_data_target_never_applies(self):
        for field, value in (("device_id", "device-B"), ("kind", "source-tree"),
                             ("signing_policy_sha256", "b" * 64), ("data_authority", "mock-other"),
                             ("executable_sha256", "b" * 64)):
            receipt = self.receipt("G15")
            receipt["target"][field] = value
            self.assertEqual(self.record(self.sign(receipt))["status"], "BLOCKED")

    def test_wrong_candidate_tree_stage_command_and_evidence_downgrade(self):
        for field, value in (("candidate_sha", "d" * 40), ("tree_sha", "d" * 40),
                             ("stage", "PRE_DESIGN"), ("command_argv", ["unrelated-ui-test"]),
                             ("evidence_level", "E0"), ("provenance", "REPORTED"),
                             ("certainty_ceiling", "PRODUCTION_PROVEN"), ("status", "NOT_RUN")):
            receipt = self.receipt()
            receipt["envelope"][field] = value
            self.assertEqual(self.record(self.sign(receipt))["status"], "BLOCKED")
        receipt = self.receipt("G04", verdict="FAIL")
        receipt["envelope"].update(evidence_level="E1", certainty_ceiling="SUPPORTED")
        self.assertEqual(self.record(self.sign(receipt))["status"], "BLOCKED")
        self.assertNotIn("G04", self.summary()["failed_gates"])

    def test_crosswalk_level_inflation_is_not_applicable(self):
        from integrations.antigravity.factory.quality import assert_assurance_applicable_envelope, QualityGateError
        oracle = next(o for o in self.packet["oracles"] if o["gate_id"] == "G04")
        envelope = copy.deepcopy(self.receipt("G04")["envelope"])
        for status in ("PASS", "FAIL"):
            envelope.update(status=status, evidence_level="E5", certainty_ceiling="VERIFIED",
                            provenance="DIRECTLY_OBSERVED")
            with self.assertRaises(QualityGateError):
                assert_assurance_applicable_envelope(envelope, oracle)

    def test_artifact_store_never_overwrites_existing_wrong_bytes(self):
        from integrations.antigravity.factory.authority import AuthorityError
        raw = "fixture artifact content"
        path, size, digest = self.runner._store_artifact(raw)
        self.assertEqual(self.runner._store_artifact(raw), (path, size, digest))
        path.write_bytes(b"tampered")
        with self.assertRaises(AuthorityError):
            self.runner._store_artifact(raw)
        self.assertEqual(path.read_bytes(), b"tampered")

    def test_actual_wrong_reason_is_failure_not_pass(self):
        wrong = {"status": 403, "reason": "UNRELATED_DENIAL"}
        self.assertEqual(self.record(self.receipt(observed=wrong))["status"], "BLOCKED")
        result = self.record(self.receipt(observed=wrong, verdict="FAIL"))
        self.assertEqual(result["applicable_verdict"], "FAIL", result)
        self.assertIn("G01", self.summary()["failed_gates"])
        self.assertEqual(self.record(self.receipt(negative={"status": 403, "reason": "WRONG"}))["status"], "BLOCKED")

    def test_source_comparison_path_and_coverage(self):
        for compare in ({"docs/unrelated.md": "c" * 40, "docs/second.md": "f" * 40},
                        {"docs/contract.md": "c" * 40}):
            receipt = self.receipt(mutate_artifact=lambda a: a.update(source_comparisons=compare))
            self.assertEqual(self.record(receipt)["status"], "BLOCKED")
        self.assertEqual(self.record(self.receipt())["status"], "RECORDED")

    def test_signed_receipt_without_independent_execution_is_unverified(self):
        receipt = self.receipt(register_execution=False)
        result = self.record(receipt)
        self.assertEqual(result["reason"], "TRUSTED_EXECUTION_OBSERVATION_MISSING")
        self.assertIn("G01", self.summary()["missing_gates"])
        receipt = self.receipt()
        receipt["nonce"] = uuid.uuid4().hex
        receipt["execution_sha256"] = digest_json(execution_projection(receipt))
        self.assertEqual(self.record(self.sign(receipt))["reason"], "TRUSTED_EXECUTION_OBSERVATION_MISSING")

    def test_optional_nonapplicable_gate_is_not_pass(self):
        from integrations.antigravity.factory.mission_contract import validate_mission_contract
        packet = copy.deepcopy(self.packet)
        packet["required_gates"].remove("G04")
        packet["non_applicable_gates"] = {"G04": "No applicable static/security check in this fixture"}
        packet["oracles"] = [o for o in packet["oracles"] if o["gate_id"] != "G04"]
        packet["objective"]["outcomes"][0]["oracle_ids"].remove("oracle-G04")
        validate_mission_contract(packet)
        result = evaluate_applicable_receipts(packet, [])
        self.assertNotIn("G04", result["passed_gates"])
        self.assertNotIn("G04", result["missing_gates"])
        self.assertIn("G04", result["documented_non_applicable"])
        self.assertEqual(result["overall_status"], "BLOCKED")

    def test_signature_replay_conflict_and_tampered_artifact(self):
        receipt = self.receipt()
        forged = copy.deepcopy(receipt)
        forged["issuer_actor_id"] = "someone-else"
        self.assertEqual(self.record(forged)["status"], "BLOCKED")
        forged = copy.deepcopy(receipt)
        forged["signature"] = "0" * 64
        self.assertEqual(self.record(forged)["status"], "BLOCKED")
        self.assertEqual(self.record(receipt)["status"], "RECORDED")
        self.assertEqual(self.record(receipt)["reason"], "REPLAYED_ASSURANCE_NONCE")
        conflict = self.receipt(observed={"status": 200, "reason": "UNAUTHORIZED"}, verdict="FAIL")
        self.assertEqual(self.record(conflict)["status"], "RECORDED")
        self.assertIn("G01", self.summary()["conflicted_gates"])
        Path(receipt["envelope"]["artifact_path"]).write_bytes(b"tampered")
        self.assertEqual(self.summary()["status"], "BLOCKED")

    def test_unsafe_artifact_and_wrong_issuer(self):
        receipt = self.receipt()
        receipt["envelope"]["artifact_path"] = str(self.root / "outside.log")
        self.assertEqual(self.record(self.sign(receipt))["reason"], "EXECUTION_RECEIPT_BINDING_MISMATCH")
        receipt = self.receipt()
        receipt.update(issuer_id="reviewer", issuer_actor_id="reviewer-actor", issuer_context_id="reviewer-context")
        self.assertEqual(self.record(self.sign(receipt))["status"], "BLOCKED")
        receipt = self.receipt()
        receipt["issued_at_utc"] = timestamp(-3600)
        self.assertEqual(self.record(self.sign(receipt))["status"], "BLOCKED")

    def test_independent_review_and_finding_dispositions(self):
        writer = self.record(self.receipt())["receipt_sha256"]
        review = self.review([writer])
        receipt = self.receipt("G13", review=review)
        receipt.update(issuer_id="writer", issuer_actor_id=self.grant["actor_id"], issuer_context_id="writer-context")
        self.assertEqual(self.record(self.sign(receipt))["status"], "BLOCKED")
        finding = {"id": "P1-01", "severity": "P1", "path": "docs/contract.md", "line": 1,
                   "contract_violated": "fixture", "reproduction": "observed", "requested_correction": "fix",
                   "disposition": "OPEN"}
        self.assertEqual(self.record(self.receipt("G13", review=self.review([writer], [finding])))["status"], "BLOCKED")
        finding["disposition"] = "FIXED"
        self.assertEqual(self.record(self.receipt("G13", review=self.review([writer], [finding])))["status"], "BLOCKED")
        self.assertEqual(self.record(self.receipt("G13", review=self.review([writer], [finding]),
                                              proofs={finding["id"]: writer}))["status"], "RECORDED")

    def test_finding_fix_requires_applicable_authorized_oracle(self):
        digests = []
        for gate in ("G00", "G01", "G04", "G15"):
            digests.append(self.record(self.receipt(gate))["receipt_sha256"])
        finding = {"id": "P1-01", "severity": "P1", "path": "docs/contract.md", "line": 1,
                   "contract_violated": "fixture", "reproduction": "observed", "requested_correction": "fix",
                   "disposition": "FIXED"}
        result = self.record(self.receipt("G13", review=self.review(digests, [finding]),
                                          proofs={"P1-01": digests[0]}))
        self.assertEqual(result["status"], "RECORDED")
        self.assertIn("G13", self.summary()["missing_gates"])
        self.assertEqual(self.summary()["overall_status"], "BLOCKED")

    def test_acceptance_actor_cannot_be_writer_or_reviewer(self):
        receipts = self.complete()
        for issuer in ("writer", "reviewer"):
            self.assertEqual(self.accept(self.decision(receipts, issuer))["status"], "BLOCKED")
        self.assertEqual(self.accept(self.decision(receipts[:-1]))["status"], "BLOCKED")

    def test_current_observation_drift_or_unavailable(self):
        receipt = self.receipt()
        observed = self.observation()
        observed["oracles"]["oracle-G01"]["runtime_sha256"] = "a" * 64
        resolver = self.make_resolver(lambda _: observed)
        self.assertEqual(self.record(receipt, resolver)["reason"], "CURRENT_SOURCE_TARGET_OR_RUNTIME_DRIFT")
        def unavailable(_):
            raise RuntimeError("fixture provider unavailable")
        self.assertEqual(self.record(receipt, self.make_resolver(unavailable))["reason"],
                         "CURRENT_OBSERVATION_UNAVAILABLE")

    def test_unknown_effect_never_cleared_by_assurance(self):
        # Deliberately model a corrupted or interrupted journal row. Assurance
        # cannot reconcile it, even with a previously valid receipt/decision.
        receipt = self.receipt()
        with sqlite3.connect(self.journal.db_path) as conn:
            conn.execute("UPDATE contract_attempts SET status='UNKNOWN' WHERE reservation_id=?", (self.reservation,))
        self.assertEqual(self.record(receipt)["status"], "BLOCKED")
        recovery = RecoveryManager(self.journal).inspect_contract_assurance(self.raw, self.reservation, self.resolver)
        self.assertFalse(recovery["replay_permitted"])
        self.assertEqual(recovery["reason"], "ATTEMPT_EFFECT_NOT_COMPLETED")
        self.assertEqual(self.journal.inspect_attempt(self.raw, self.reservation)["status"], "UNKNOWN")

    def test_raw_json_duplicate_and_invalid_shapes(self):
        for raw in ('{"schema_version":1,"schema_version":1}', '[]', '{"signature":NaN}', '{"target":null}'):
            result = self.journal.record_assurance_evidence(self.raw, self.reservation, raw, self.resolver)
            self.assertEqual(result["status"], "BLOCKED")
