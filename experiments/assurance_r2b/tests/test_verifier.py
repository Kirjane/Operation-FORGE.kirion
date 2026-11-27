"""Adversarial synthetic verifier qualification. No live CI/Host claims."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent.parent))
from experiments.assurance_r2b.verifier import (  # noqa: E402
    evaluate_fixture, evaluate_live, InvalidClaim,
    SUPPORTED, CONTRADICTED, UNVERIFIED,
)


def case(name):
    return json.loads((ROOT / "fixtures" / (name + ".json")).read_text(encoding="utf-8"))


def check(verdict, scenario, *reasons):
    response = evaluate_fixture(scenario)
    if response.verdict != verdict or any(reason not in response.reason_codes for reason in reasons):
        raise AssertionError(f"Expected {verdict}/{reasons}; got {response}")
    if response.promotion_authorized or response.actual_product_outcome != "NOT_TESTED" or not response.synthetic:
        raise AssertionError("Synthetic case escalated into real-world authority")


class SixHistoricalControls(unittest.TestCase):
    def test_all_six_expected_oracles(self):
        for name in [
            "r2a-red-cafe", "r2a-green-cafe", "r2a-red-talibon",
            "r2a-green-talibon", "r2a-red-retail", "r2a-green-retail"
        ]:
            with self.subTest(name=name):
                x = case(name)
                got = evaluate_fixture(x)
                # The oracle lives outside the untrusted claim and is not fed to evaluator.
                want = x["expected_oracle"]
                self.assertEqual(got.verdict, want["verdict"])
                self.assertTrue(set(want["reason_codes"]).issubset(set(got.reason_codes)), msg=f"{name}: additional material reasons {got.reason_codes}")
                self.assertFalse(got.promotion_authorized)


class HostileAndBenignH01toH21(unittest.TestCase):
    def test_H01(self): check(CONTRADICTED, case("r2a-red-cafe"), "WRONG_EXECUTABLE_TARGET")
    def test_H02(self): check(SUPPORTED, case("r2a-green-cafe"), "SCOPED_EVIDENCE_MATCH")
    def test_H03(self): check(CONTRADICTED, case("r2a-red-talibon"), "SOURCE_CONTENT_MISMATCH")
    def test_H04(self): check(SUPPORTED, case("r2a-green-talibon"), "SCOPED_EVIDENCE_MATCH")
    def test_H05(self): check(UNVERIFIED, case("r2a-red-retail"), "REQUIRED_GATE_NOT_RUN", "REQUIRED_GATE_BLOCKED")
    def test_H06(self): check(SUPPORTED, case("r2a-green-retail"), "SCOPED_EVIDENCE_MATCH")

    def test_H07_author_only_report(self):
        x = case("r2a-green-cafe")
        x["simulated_resolver_context"]["evidence_records"][0]["issuer_resolution"]["channel"] = "AUTHOR_REPORT_ONLY"
        check(UNVERIFIED, x, "UNTRUSTED_ATTESTATION")

    def test_H08_deleted_required_gate(self):
        x = case("r2a-red-retail")
        x["simulated_resolver_context"]["gate_observations"] = []
        check(UNVERIFIED, x, "REQUIRED_GATE_MISSING")

    def test_H09_unbacked_gate_pass(self):
        x = case("r2a-green-cafe")
        x["simulated_resolver_context"]["gate_observations"][0]["evidence_ids"] = []
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE")

    def test_H10_mutated_policy_hash(self):
        x = case("r2a-green-cafe")
        x["simulated_resolver_context"]["pinned_policy"]["sha256"] = "1"*64
        check(UNVERIFIED, x, "UNRESOLVED_AUTHORITY")

    def test_H11_runtime_with_E1_source_only(self):
        x = case("r2a-red-cafe")
        e = copy.deepcopy(case("r2a-green-retail")["simulated_resolver_context"]["evidence_records"][0])
        e["candidate_sha"] = x["untrusted_request"]["mission"]["candidate_sha"]
        e["evidence_id"] = "cafe-e1-only"
        x["untrusted_request"]["offered_evidence_ids"] = ["cafe-e1-only"]
        x["simulated_resolver_context"]["evidence_records"] = [e]
        check(UNVERIFIED, x, "REQUIRED_GATE_MISSING")

    def test_H12_explicit_trusted_failure(self):
        x = case("r2a-red-retail")
        g = x["simulated_resolver_context"]["gate_observations"][1]
        g.update(observed_status="FAIL", evidence_ids=["windows-lab-failed"])
        e = copy.deepcopy(x["simulated_resolver_context"]["evidence_records"][1]);e.update(evidence_id="windows-lab-failed",evidence_level="E5", evidence_type="DEVICE", provenance="DIRECTLY_OBSERVED", result="FAIL")
        x["simulated_resolver_context"]["evidence_records"].append(e)
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE", "REQUIRED_GATE_BLOCKED")

    def test_H13_fail_and_not_run(self):
        x = case("r2a-red-retail")
        g = x["simulated_resolver_context"]["gate_observations"][0]
        g["observed_status"] = "FAIL"
        e = x["simulated_resolver_context"]["evidence_records"][0]
        e["result"] = "FAIL"
        check(CONTRADICTED, x, "REQUIRED_GATE_FAILED", "REQUIRED_GATE_NOT_RUN")

    def test_H14_conflicting_pass_fail(self):
        x = case("r2a-green-cafe")
        x["simulated_resolver_context"]["evidence_records"][0]["result"] = "FAIL"
        check(UNVERIFIED, x, "INCONSISTENT_EVIDENCE")

    def test_H15_wrong_source_sha(self):
        x = case("r2a-green-cafe")
        x["simulated_resolver_context"]["evidence_records"][0]["candidate_sha"] = "0"*40
        check(CONTRADICTED, x, "EVIDENCE_SHA_MISMATCH")

    def test_H16_artifact_mismatch(self):
        x = case("r2a-red-cafe")
        e = copy.deepcopy(x["simulated_resolver_context"]["evidence_records"][0]);e.update(evidence_id="cafe-real-proof",evidence_level="E5",evidence_type="RUNTIME",provenance="DIRECTLY_OBSERVED")
        e["observed_target"] = copy.deepcopy(x["untrusted_request"]["claim"]["target"])
        e["observed_target"]["artifact_digest_sha256"] = "f"*64
        x["untrusted_request"]["offered_evidence_ids"] = ["cafe-real-proof"]
        x["simulated_resolver_context"]["evidence_records"] = [e]
        x["simulated_resolver_context"]["gate_observations"][0].update(observed_status="PASS",evidence_ids=["cafe-real-proof"])
        check(CONTRADICTED, x, "EVIDENCE_ARTIFACT_MISMATCH")

    def test_H17_reviewer_is_author(self):
        x = case("r2a-green-retail")
        result = evaluate_fixture(x, security_context={"author_identity":"123", "reviewer_identity":"123"})
        self.assertEqual(result.verdict, UNVERIFIED)
        self.assertIn("REVIEWER_CONFLICT", result.reason_codes)

    def test_H18_forbidden_author_blob(self):
        x = case("r2a-red-talibon")
        x["untrusted_request"]["approved_blob_sha"] = "1"*40
        with self.assertRaises(InvalidClaim): evaluate_fixture(x)

    def test_H19_E6_release(self):
        x = case("r2a-red-retail")
        x["untrusted_request"]["claim"]["requested_evidence_level"] = "E6"
        with self.assertRaises(InvalidClaim): evaluate_fixture(x)

    def test_H20_missing_runtime_entrypoint(self):
        x = case("r2a-red-cafe")
        del x["untrusted_request"]["claim"]["target"]["entrypoint"]
        with self.assertRaises(InvalidClaim): evaluate_fixture(x)

    def test_H21_synthetic_runtime_complete(self):
        x = case("r2a-red-cafe")
        e = copy.deepcopy(x["simulated_resolver_context"]["evidence_records"][0])
        e.update(evidence_id="cafe-installed-runtime",evidence_level="E5", evidence_type="RUNTIME", provenance="DIRECTLY_OBSERVED")
        e["observed_target"] = copy.deepcopy(x["untrusted_request"]["claim"]["target"])
        x["untrusted_request"]["offered_evidence_ids"] = ["cafe-installed-runtime"]
        x["simulated_resolver_context"]["evidence_records"] = [e]
        x["simulated_resolver_context"]["gate_observations"][0].update(observed_status="PASS",evidence_ids=["cafe-installed-runtime"])
        check(SUPPORTED, x, "SCOPED_EVIDENCE_MATCH")


class AdditionalCriticalSecurityCases(unittest.TestCase):
    def test_replay_same_sha_different_nonce(self):
        x = case("r2a-green-cafe")
        sec = {"claimant_id":"worker-A", "nonce":"N2", "receipt_bindings": {
            "cafe-legacy-ci": {"repository":x["untrusted_request"]["mission"]["repository"],
               "candidate_sha":x["untrusted_request"]["mission"]["candidate_sha"],
               "mission_id":x["untrusted_request"]["mission"]["mission_id"],
               "claim_id":x["untrusted_request"]["claim"]["claim_id"],
               "claimant_id":"worker-A", "nonce":"N1"}}}
        check_result = evaluate_fixture(x,security_context=sec)
        self.assertEqual(check_result.verdict, UNVERIFIED)
        self.assertIn("REPLAYED_RECEIPT", check_result.reason_codes)

    def test_replay_same_sha_new_claimant(self):
        x = case("r2a-green-cafe")
        s={"claimant_id":"B", "nonce":"same", "receipt_bindings": {
             "cafe-legacy-ci":{"repository":x["untrusted_request"]["mission"]["repository"],
                "candidate_sha":x["untrusted_request"]["mission"]["candidate_sha"],
                "mission_id":x["untrusted_request"]["mission"]["mission_id"],
                "claim_id":x["untrusted_request"]["claim"]["claim_id"],
                "claimant_id":"A", "nonce":"same"}}}
        self.assertIn("REPLAYED_RECEIPT",evaluate_fixture(x,security_context=s).reason_codes)

    def test_untrusted_policy_self_repin(self):
        x=case("r2a-green-cafe");x["simulated_resolver_context"]["pinned_policy"]["sha256"]="f"*64
        check(UNVERIFIED,x,"UNRESOLVED_AUTHORITY")

    def test_synthetic_refused_in_live(self):
        x=case("r2a-green-cafe")
        self.assertEqual(evaluate_fixture(x,mode="live").verdict,UNVERIFIED)
        self.assertEqual(evaluate_live(x).verdict,UNVERIFIED)
        self.assertFalse(evaluate_live(x).promotion_authorized)

    def test_nxr2a_009_optimized_python_safety(self):
        # Ordinary test runner and optimized (-O) runner both call explicit schema guards.
        x=case("r2a-green-cafe");x["untrusted_request"]["gates"]=[{"id":"forged"}]
        with self.assertRaises(InvalidClaim):evaluate_fixture(x)

    def test_selfreported_gate_conflict(self):
        x=case("r2a-green-cafe")
        x["simulated_resolver_context"]["gate_observations"][0]["resolved_by"]="AUTHOR_REPORT_ONLY"
        check(UNVERIFIED,x,"UNTRUSTED_ATTESTATION")

    def test_missing_gate_policy_not_supplied_by_candidate(self):
        x=case("r2a-green-cafe")
        del x["simulated_resolver_context"]["gate_observations"][0]
        check(UNVERIFIED,x,"REQUIRED_GATE_MISSING")

    def test_policy_paths_nonapproved_not_live(self):
        x=case("r2a-green-cafe")
        self.assertEqual(evaluate_fixture(x,mode="production").verdict,UNVERIFIED)


# Independent Nox R1 6031088112 hostile cases, with valid-scope controls.
# All receipt identities and targets remain SYNTHETIC test-harness inputs.
def retail_release():
    x = case("r2a-red-retail")
    claim = x["untrusted_request"]
    context = x["simulated_resolver_context"]
    digest = claim["claim"]["target"]["artifact_digest_sha256"]
    source = context["evidence_records"][0]
    device = copy.deepcopy(source)
    device.update(evidence_id="ret-windows-abc", evidence_level="E5", evidence_type="DEVICE",
                  result="PASS", provenance="DIRECTLY_OBSERVED")
    device["issuer_resolution"] = {"channel":"SIMULATED_REVIEWER_API", "issuer_id":"lab-test-operator",
                                   "trust_class":"SIMULATED_RESOLVED_FIXTURE_ONLY"}
    device["observed_target"] = {
        "kind":"runtime-entrypoint", "environment":"synthetic Windows VHDX adversarial lab",
        "data_authority":"installed-runtime", "entrypoint":"windows://retail-installed",
        "validation_scope":"Windows VHDX ACL adversarial A/B/C", "artifact_digest_sha256":digest,
        "device_matrix":["VHDX_A", "VHDX_B", "VHDX_C"],
    }
    signing = copy.deepcopy(source)
    signing.update(evidence_id="ret-signing-policy", evidence_level="E4", evidence_type="BUILD",
                   result="PASS", provenance="AUTOMATED")
    signing["issuer_resolution"] = {"channel":"SIMULATED_GITHUB_ACTIONS", "issuer_id":"signing-fixture",
                                    "trust_class":"SIMULATED_RESOLVED_FIXTURE_ONLY"}
    signing["observed_target"] = {
        "kind":"release-artifact", "environment":"synthetic signing authorization",
        "data_authority":"not-applicable", "validation_scope":"installer signing authorization",
        "artifact_digest_sha256":digest, "signing_policy_ref":"R2B_SYNTHETIC_SIGNING_POLICY",
    }
    context["evidence_records"] = [source, device, signing]
    context["gate_observations"][1].update(observed_status="PASS", evidence_ids=["ret-windows-abc"])
    context["gate_observations"][2].update(observed_status="PASS", evidence_ids=["ret-signing-policy"])
    claim["offered_evidence_ids"] = ["ret-pr105-source-review", "ret-windows-abc", "ret-signing-policy"]
    return x


class NoxR1CorrectiveAdversarialTests(unittest.TestCase):
    """Prove the corrected semantics, including legitimate positives/negatives."""

    def test_NXR2B_001_complete_matching_release_accepted_as_synthetic_only(self):
        check(SUPPORTED, retail_release(), "SCOPED_EVIDENCE_MATCH")

    def test_NXR2B_001_source_tree_mock_device_and_signing_false_support(self):
        x = retail_release()
        for e in x["simulated_resolver_context"]["evidence_records"][1:]:
            e["observed_target"].update(kind="source-tree", environment="mock browser", data_authority="mock-fixture")
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE")

    def test_NXR2B_001_wrong_device_target_only(self):
        x = retail_release()
        x["simulated_resolver_context"]["evidence_records"][1]["observed_target"]["kind"] = "source-tree"
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE")

    def test_NXR2B_001_wrong_signing_scope_only(self):
        x = retail_release()
        x["simulated_resolver_context"]["evidence_records"][2]["observed_target"]["validation_scope"] = "internal smoke"
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE")

    def test_NXR2B_001_device_missing_installer_digest(self):
        x = retail_release()
        del x["simulated_resolver_context"]["evidence_records"][1]["observed_target"]["artifact_digest_sha256"]
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE")

    def test_NXR2B_001_signing_issuer_substitution(self):
        x = retail_release()
        x["simulated_resolver_context"]["evidence_records"][2]["issuer_resolution"]["channel"] = "SIMULATED_REVIEWER_API"
        check(UNVERIFIED, x, "UNTRUSTED_ATTESTATION")


    def test_NXR2B_001_device_matrix_incomplete(self):
        x = retail_release()
        x["simulated_resolver_context"]["evidence_records"][1]["observed_target"]["device_matrix"] = ["VHDX_A"]
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE")

    def test_NXR2B_001_signing_policy_substitution(self):
        x = retail_release()
        x["simulated_resolver_context"]["evidence_records"][2]["observed_target"]["signing_policy_ref"] = "OTHER_POLICY"
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE")

    def test_NXR2B_001_wrong_digest_is_proof_binding_contradiction(self):
        x = retail_release()
        x["simulated_resolver_context"]["evidence_records"][1]["observed_target"]["artifact_digest_sha256"] = "1" * 64
        check(CONTRADICTED, x, "EVIDENCE_ARTIFACT_MISMATCH")

    def test_NXR2B_002_complete_matching_single_file_comparison(self):
        x = case("r2a-red-talibon")
        x["simulated_resolver_context"]["evidence_records"][1]["result"] = "PASS"
        x["simulated_resolver_context"]["gate_observations"][0]["observed_status"] = "PASS"
        comp = x["simulated_resolver_context"]["git_object_comparison"]
        comp["observed_blob_sha"] = comp["approved_blob_sha"]
        check(SUPPORTED, x, "SCOPED_EVIDENCE_MATCH")

    def test_NXR2B_002_same_hash_unrelated_path_and_receipt(self):
        x = case("r2a-red-talibon")
        x["simulated_resolver_context"]["evidence_records"][1]["result"] = "PASS"
        x["simulated_resolver_context"]["gate_observations"][0]["observed_status"] = "PASS"
        comp = x["simulated_resolver_context"]["git_object_comparison"]
        comp.update(path="unrelated/OtherController.php", linked_evidence_id="irrelevant-id",
                    observed_blob_sha=comp["approved_blob_sha"])
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE")

    def test_NXR2B_002_same_hash_wrong_candidate_sha(self):
        x = case("r2a-red-talibon")
        x["simulated_resolver_context"]["evidence_records"][1]["result"] = "PASS"
        x["simulated_resolver_context"]["gate_observations"][0]["observed_status"] = "PASS"
        comp = x["simulated_resolver_context"]["git_object_comparison"]
        comp.update(candidate_sha="f" * 40, observed_blob_sha=comp["approved_blob_sha"])
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE")

    def test_NXR2B_002_missing_offer_for_negative_comparison(self):
        x = case("r2a-red-talibon")
        x["untrusted_request"]["offered_evidence_ids"] = ["tal-path-only"]
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE")

    def test_NXR2B_002_multi_path_complete_positive(self):
        x = case("r2a-red-talibon")
        c = x["simulated_resolver_context"]
        e = c["evidence_records"][1]
        e["result"] = "PASS"
        c["gate_observations"][0]["observed_status"] = "PASS"
        e["observed_target"]["content_scope"].append("app/Http/Controllers/OtherController.php")
        x["untrusted_request"]["claim"]["target"]["content_scope"].append("app/Http/Controllers/OtherController.php")
        comp = c.pop("git_object_comparison")
        comp["observed_blob_sha"] = comp["approved_blob_sha"]
        second = copy.deepcopy(comp)
        second["path"] = "app/Http/Controllers/OtherController.php"
        c["git_object_comparisons"] = [comp, second]
        check(SUPPORTED, x, "SCOPED_EVIDENCE_MATCH")

    def test_NXR2B_002_multi_path_missing_one_comparison(self):
        x = case("r2a-red-talibon")
        c = x["simulated_resolver_context"]
        e = c["evidence_records"][1]
        e["result"] = "PASS"
        c["gate_observations"][0]["observed_status"] = "PASS"
        e["observed_target"]["content_scope"].append("app/Http/Controllers/OtherController.php")
        x["untrusted_request"]["claim"]["target"]["content_scope"].append("app/Http/Controllers/OtherController.php")
        comp = c.pop("git_object_comparison")
        comp["observed_blob_sha"] = comp["approved_blob_sha"]
        c["git_object_comparisons"] = [comp]
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE")

    def test_NXR2B_003_e1_receipt_issuer_is_author_not_review_reviewer(self):
        x = case("r2a-green-retail")
        x["simulated_resolver_context"]["evidence_records"][0]["issuer_resolution"]["issuer_id"] = "author-same-person"
        check(UNVERIFIED, x, "REVIEWER_CONFLICT")
        result = evaluate_fixture(x, security_context={
            "author_identity":"author-same-person", "reviewer_identity":"independent-person"})
        self.assertEqual(result.verdict, UNVERIFIED)
        self.assertIn("REVIEWER_CONFLICT", result.reason_codes)

    def test_NXR2B_003_absent_reviewer_resolution_fails_closed(self):
        x = case("r2a-green-retail")
        del x["simulated_resolver_context"]["reviewer_resolution"]
        check(UNVERIFIED, x, "REVIEWER_CONFLICT")

    def test_NXR2B_003_author_equals_resolved_reviewer(self):
        x = case("r2a-green-retail")
        x["simulated_resolver_context"]["reviewer_resolution"]["author_identity"] = "independent-fixture-reviewer"
        check(UNVERIFIED, x, "REVIEWER_CONFLICT")

    def test_NXR2B_003_valid_sec_identity_binding(self):
        x = case("r2a-green-retail")
        sec = {"author_identity":"retail-author-fixture", "reviewer_identity":"independent-fixture-reviewer"}
        self.assertEqual(evaluate_fixture(x, security_context=sec).verdict, SUPPORTED)

    def test_NXR2B_003_conflicting_sec_identity(self):
        x = case("r2a-green-retail")
        sec = {"author_identity":"retail-author-fixture", "reviewer_identity":"not-the-issuer"}
        self.assertEqual(evaluate_fixture(x, security_context=sec).verdict, UNVERIFIED)

    def test_NXR2B_004_low_level_source_fail_cannot_condemn_device_gate(self):
        x = case("r2a-red-retail")
        e = copy.deepcopy(x["simulated_resolver_context"]["evidence_records"][0])
        e.update(evidence_id="source-review-fail-not-device", result="FAIL")
        x["simulated_resolver_context"]["evidence_records"].append(e)
        x["untrusted_request"]["offered_evidence_ids"].append(e["evidence_id"])
        x["simulated_resolver_context"]["gate_observations"][1].update(
            observed_status="FAIL", evidence_ids=[e["evidence_id"]])
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE", "REQUIRED_GATE_BLOCKED")

    def test_NXR2B_004_wrong_target_e5_fail_cannot_condemn_device_gate(self):
        x = case("r2a-red-retail")
        x["simulated_resolver_context"]["gate_observations"][1].update(
            observed_status="FAIL", evidence_ids=["ret-internal-smoke"])
        e = x["simulated_resolver_context"]["evidence_records"][1]
        e.update(evidence_level="E5", evidence_type="DEVICE", provenance="DIRECTLY_OBSERVED", result="FAIL")
        e["issuer_resolution"].update(channel="SIMULATED_REVIEWER_API", issuer_id="lab-test-operator")
        check(UNVERIFIED, x, "MISSING_TARGET_EVIDENCE", "REQUIRED_GATE_BLOCKED")

    def test_NXR2B_004_correct_target_e5_fail_may_contradict(self):
        x = retail_release()
        x["simulated_resolver_context"]["evidence_records"][1]["result"] = "FAIL"
        x["simulated_resolver_context"]["gate_observations"][1]["observed_status"] = "FAIL"
        check(CONTRADICTED, x, "REQUIRED_GATE_FAILED")

    def test_NXR2B_004_true_dual_conflicting_receipts_hold(self):
        x = retail_release()
        e = copy.deepcopy(x["simulated_resolver_context"]["evidence_records"][1])
        e["evidence_id"] = "ret-windows-abc-disagreement"
        e["result"] = "FAIL"
        x["simulated_resolver_context"]["evidence_records"].append(e)
        x["simulated_resolver_context"]["gate_observations"][1]["evidence_ids"].append(e["evidence_id"])
        x["untrusted_request"]["offered_evidence_ids"].append(e["evidence_id"])
        check(UNVERIFIED, x, "INCONSISTENT_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
