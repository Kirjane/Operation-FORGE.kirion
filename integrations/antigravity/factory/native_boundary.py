"""Native entry denial and explicitly non-live W1/W2/W4 composition."""
from .authority import AuthorityError
from .dispatch_preflight import ContractJournal, fixture_adapter_binding
from .scoped_fixture import ScopedGitFixtureAdapter
from .assurance import FixtureAssuranceResolver
from .delivery import NairuDeliveryBroker
from .mission_contract import parse_mission_packet
from .fenced_file import supported

WORKFLOWS = frozenset({
    "greenfield_discovery", "feature_delivery", "self_healing_repair",
    "nox_adversarial_audit", "candidate_integration", "recovery_reconcile",
})
# Descriptive surfaces, not current probes or grants.
HOST_SURFACES = {
    "antigravity": ("run_workflow", "agent", "lifecycle_hooks"),
    "chatgpt": ("connected_repository_tools",),
    "codex": ("workspace_execution",),
}


def resolve_native_capabilities(host):
    known = type(host) is str and host in HOST_SURFACES
    return {
        "host_surface": host if known else "unknown",
        "descriptive_interfaces": list(HOST_SURFACES[host]) if known else [],
        "host_id": None, "actor_id": None, "observed": False,
        "trusted_native_execution": "UNAVAILABLE",
        "trusted_native_write_fence": "UNAVAILABLE",
        "independent_oracle": "UNAVAILABLE",
        "authorized_delivery": "UNAVAILABLE",
    }


def native_workflow_entry(workflow, host, ingress):
    """Never use ingress as trusted composition or invoke an agent from it."""
    reason = ("TRUSTED_NATIVE_PREFLIGHT_BRIDGE_UNAVAILABLE"
              if type(workflow) is str and workflow in WORKFLOWS
              else "UNKNOWN_NATIVE_WORKFLOW")
    return {"status": "BLOCKED", "reason": reason,
            "capabilities": resolve_native_capabilities(host),
            "invoked": False, "promotion_authorized": False}


class FixtureNativeBoundary:
    """Operator/test composition only. Never instantiate from a host workflow.

    No native agent, arbitrary executable, callback adapter or delivery transport.
    Generic skill loading remains owned by the dispatcher; no skill consumption
    is asserted here. Combined integration must wire a trusted loader.
    """

    def __init__(self, journal, adapter, *, assurance=None):
        if type(journal) is not ContractJournal or type(adapter) is not ScopedGitFixtureAdapter:
            raise AuthorityError("SCOPED_FIXTURE_COMPOSITION_REQUIRED")
        if assurance is not None and type(assurance) is not FixtureAssuranceResolver:
            raise AuthorityError("FIXTURE_ASSURANCE_COMPOSITION_REQUIRED")
        self._journal, self._adapter, self._assurance = journal, adapter, assurance

    def execute(self, workflow, raw):
        packet = parse_mission_packet(raw)
        if packet["schema_version"] != 2:
            raise AuthorityError("NATIVE_BOUNDARY_REQUIRES_V2")
        operations = set(packet["allowed_operations"])
        eligible = (
            workflow == "greenfield_discovery" and operations == {"READ"} or
            workflow in ("feature_delivery", "self_healing_repair")
            and operations == {"READ", "WRITE_OWNED"} and supported()
        )
        if not eligible:
            return self._journal.block_unavailable_bridge(raw)
        return self._journal.dispatch_fixture(raw, self._adapter)

    def inspect_recovery(self, raw, reservation_id):
        receipt = self._journal.inspect_attempt(raw, reservation_id)
        if receipt["adapter_binding"] != fixture_adapter_binding(self._adapter):
            raise AuthorityError("RECOVERY_ADAPTER_BINDING_MISMATCH")
        return {**receipt, "observation": self._adapter.inspect_local_effect(),
                "replay_permitted": False, "promotion_authorized": False}

    def record_evidence(self, raw, reservation_id, receipt_raw):
        return self._journal.record_assurance_evidence(
            raw, reservation_id, receipt_raw, self._assurance)

    def inspect_assurance(self, raw, reservation_id):
        return self._journal.evaluate_assurance(raw, reservation_id, self._assurance)

    def record_decision(self, raw, reservation_id, decision_raw):
        return self._journal.record_assurance_decision(
            raw, reservation_id, decision_raw, self._assurance)

    def inspect_delivery(self, raw, reservation_id):
        return NairuDeliveryBroker.inspect_contract_delivery(
            raw, reservation_id, journal=self._journal, resolver=self._assurance)
