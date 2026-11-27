"""Proportional execution routing, not capability attestation or dispatch.

Only a trusted host composition may supply verified availability observations.
A missing helper does not become an operator transfer. The executor retains the
mission, reconciles uncertain effects and records a blocker if no safe route exists.
"""
from .authority import VALID_RISK_CLASSES

ROUTE_ORDER = ("DIRECT", "BOUNDED_HELPER", "NATIVE_EXECUTOR")
TASK_KINDS = frozenset({"DETERMINISTIC", "BOUNDED", "INTEGRATION"})
CAPABILITY_KEYS = frozenset({"observed", "authorized", "scope_match", "data_boundary_match"})


def _eligible(observation):
    return (type(observation) is dict and set(observation) == CAPABILITY_KEYS
            and all(observation[key] is True for key in CAPABILITY_KEYS))


def select_execution_route(*, risk_class, task_kind, private_material, observations,
                           previous_effect_unknown=False):
    """Return a proposal only; no provider launch, invocation or permission."""
    base = {"authority_granted": False, "invoked": False, "promotion_authorized": False,
            "operator_relay_required": False}
    if (type(risk_class) is not str or risk_class not in VALID_RISK_CLASSES
            or type(task_kind) is not str or task_kind not in TASK_KINDS
            or type(private_material) is not bool or type(previous_effect_unknown) is not bool
            or type(observations) is not dict or set(observations) - set(ROUTE_ORDER)):
        return dict(base, status="BLOCKED", reason="INVALID_ROUTE_INPUT")
    if previous_effect_unknown:
        return dict(base, status="BLOCKED", reason="RECONCILE_PREVIOUS_EFFECT")
    if risk_class in {"RISK-3", "RISK-4"} or task_kind == "INTEGRATION":
        order = ("NATIVE_EXECUTOR",)
    elif task_kind == "DETERMINISTIC":
        order = ROUTE_ORDER
    else:
        order = ("BOUNDED_HELPER", "NATIVE_EXECUTOR")
    for route in order:
        if private_material and route == "BOUNDED_HELPER":
            continue
        if _eligible(observations.get(route)):
            return dict(base, status="PROPOSED", route=route, requires_trusted_preflight=True)
    return dict(base, status="BLOCKED", reason="NO_VERIFIED_AUTHORIZED_ROUTE")
