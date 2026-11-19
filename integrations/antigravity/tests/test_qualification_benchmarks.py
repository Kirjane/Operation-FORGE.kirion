"""F15 & F16 — Qualification test runner executing Benchmarks A, B, C, D, and E end-to-end."""
from __future__ import annotations

import unittest

from integrations.antigravity.benchmarks.blind_defects_suite import (
    run_benchmark_c_suite,
)
from integrations.antigravity.benchmarks.hidden_oracles import (
    run_benchmark_a_with_hidden_oracle,
    run_benchmark_b_with_hidden_oracle,
)
from integrations.antigravity.benchmarks.reliability_suite import run_benchmark_d_suite
from integrations.antigravity.benchmarks.security_qualification_suite import (
    run_benchmark_e_suite,
)


class QualificationBenchmarksTests(unittest.TestCase):
    def test_benchmark_a_php_laravel_procurement_and_inventory(self) -> None:
        res = run_benchmark_a_with_hidden_oracle(trials=2)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["trials_executed"], 2)
        for t in res["trials"]:
            self.assertEqual(t["cli_assertions"], 28)
            self.assertTrue(t["http_oracle_verified"])

    def test_benchmark_b_csharp_aspnet_transaction_engine(self) -> None:
        res = run_benchmark_b_with_hidden_oracle(trials=2)
        self.assertEqual(res["status"], "PASS")
        self.assertTrue(res["build_output_clean"])
        self.assertEqual(res["trials_executed"], 2)
        for t in res["trials"]:
            self.assertEqual(t["self_test_assertions"], 25)
            self.assertTrue(t["external_hidden_oracle_verified"])

    def test_benchmark_c_blind_seeded_deceptive_defects(self) -> None:
        res = run_benchmark_c_suite()
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["total_seeded_defects"], 17)
        self.assertEqual(res["detected_defects"], 17)
        self.assertEqual(res["repaired_defects"], 17)
        self.assertEqual(res["detection_rate"], 1.0)
        self.assertEqual(res["repair_success_rate"], 1.0)
        self.assertEqual(res["holdout_variants_total"], 5)
        self.assertEqual(res["holdout_variants_detected"], 5)
        self.assertEqual(res["holdout_detection_rate"], 1.0)
        self.assertEqual(res["false_positives"], 0)
        self.assertEqual(res["false_positive_rate"], 0.0)

    def test_benchmark_d_factory_reliability_and_recovery(self) -> None:
        res = run_benchmark_d_suite(trials_per_point=3)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["total_interruption_trials"], 12)
        self.assertTrue(all(res["fault_matrix"].values()))

    def test_benchmark_e_adversarial_authority_and_supply_chain(self) -> None:
        res = run_benchmark_e_suite()
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["total_adversarial_vectors"], 16)
        self.assertEqual(res["denied_adversarial_vectors"], 16)
        self.assertTrue(res["positive_bounded_operations_succeeded"])


if __name__ == "__main__":
    unittest.main()
