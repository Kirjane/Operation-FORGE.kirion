"""Inert stage semantics preserved from the pre-boundary workflow sources.
No agent calls, commands, role activation or acceptance transitions.
"""
from copy import deepcopy

STAGES = {
    "greenfield_discovery": [
        {"stage": "intake", "role": "Maintainer", "artifact": "origin, work mode, risk, bounded mission decomposition"},
        {"stage": "architecture_and_threat_model", "role": "Code Writer / Reviewer",
         "artifact": "architecture contracts and independent security invariants"}],
    "feature_delivery": [
        {"stage": "implementation", "role": "Code Writer", "artifact": "writer-result.schema.json, exact candidate and test evidence"},
        {"stage": "independent_review", "role": "Reviewer", "requires": "READY writer result and distinct actor/context",
         "artifact": "nox-result.schema.json for exact frozen candidate"}],
    "self_healing_repair": [
        {"stage": "failure_classification", "role": "Reviewer", "artifact": "failure taxonomy and discriminating regression",
         "stop_on": ["requirements", "drift", "resource"]},
        {"stage": "root_cause_repair", "role": "Code Writer", "requires": "authorized repairable class, exact candidate and remaining budget",
         "artifact": "writer-result.schema.json and pre/post regression evidence, no assertion weakening"},
        {"stage": "independent_recheck", "role": "Reviewer", "requires": "READY writer final_sha and distinct actor/context",
         "artifact": "nox-result.schema.json at exact repaired SHA", "candidate_binding": "writer final_sha"}],
    "nox_adversarial_audit": [
        {"stage": "frozen_candidate_audit", "role": "Reviewer", "requires": "independent nonauthor actor/context and exact SHA",
         "artifact": "source, tests, policy, evidence and security findings; nox-result.schema.json"}],
    "candidate_integration": [
        {"stage": "ancestry_and_collision_audit", "role": "Integration Writer",
         "artifact": "exact ancestry, shared routes, migrations, lockfile and semantic collision report"}],
    "recovery_reconcile": [
        {"stage": "capsule_reconciliation", "role": "Code Writer / Maintainer",
         "artifact": "read-only journal chain, delivery key and remote head evidence; recovery-capsule.schema.json",
         "requires": "separate recovery authority; UNKNOWN never authorizes replay"}],
}


def workflow_stages(workflow):
    if type(workflow) is not str:
        return []
    return [{**deepcopy(step), "native_invoked": False, "requires_separate_authority": True}
            for step in STAGES.get(workflow, ())]
