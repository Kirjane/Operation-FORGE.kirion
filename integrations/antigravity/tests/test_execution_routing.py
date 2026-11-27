import unittest

from integrations.antigravity.factory.execution_routing import select_execution_route


VERIFIED = dict(observed=True, authorized=True, scope_match=True, data_boundary_match=True)


class ExecutionRoutingTests(unittest.TestCase):
    def choose(self, **changes):
        args = dict(risk_class="RISK-1", task_kind="DETERMINISTIC", private_material=False,
                    observations={k: dict(VERIFIED) for k in ("DIRECT", "BOUNDED_HELPER", "NATIVE_EXECUTOR")})
        args.update(changes)
        result = select_execution_route(**args)
        self.assertFalse(result["authority_granted"])
        self.assertFalse(result["invoked"])
        self.assertFalse(result["operator_relay_required"])
        return result

    def test_deterministic_direct_first(self):
        self.assertEqual(self.choose()["route"], "DIRECT")

    def test_bounded_helper_then_native_fallback(self):
        self.assertEqual(self.choose(task_kind="BOUNDED")["route"], "BOUNDED_HELPER")
        self.assertEqual(self.choose(task_kind="BOUNDED", observations={"NATIVE_EXECUTOR": VERIFIED})["route"],
                         "NATIVE_EXECUTOR")

    def test_risk_and_integration_override_helper(self):
        for changes in ({"risk_class": "RISK-3"}, {"risk_class": "RISK-4"}, {"task_kind": "INTEGRATION"}):
            self.assertEqual(self.choose(**changes)["route"], "NATIVE_EXECUTOR")

    def test_private_material_never_sent_to_helper(self):
        self.assertEqual(self.choose(task_kind="BOUNDED", private_material=True)["route"], "NATIVE_EXECUTOR")

    def test_unobserved_unauthorized_or_mismatched_routes_denied(self):
        for key in VERIFIED:
            unavailable = dict(VERIFIED, **{key: False})
            self.assertEqual(self.choose(observations={"DIRECT": unavailable})["reason"],
                             "NO_VERIFIED_AUTHORIZED_ROUTE")
        self.assertEqual(self.choose(observations={"DIRECT": True})["status"], "BLOCKED")

    def test_unknown_effect_not_replayed(self):
        self.assertEqual(self.choose(previous_effect_unknown=True)["reason"], "RECONCILE_PREVIOUS_EFFECT")

    def test_missing_route_no_manual_fallback(self):
        self.assertEqual(self.choose(observations={})["reason"], "NO_VERIFIED_AUTHORIZED_ROUTE")

    def test_unknown_input_denied(self):
        self.assertEqual(self.choose(risk_class="HIGH")["reason"], "INVALID_ROUTE_INPUT")
