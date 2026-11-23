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
        check(CONTRADICTED, x, "REQUIRED_GATE_FAILED")

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


if __name__ == "__main__":
    unittest.main()
