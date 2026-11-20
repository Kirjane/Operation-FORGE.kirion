"""ChatGPT-specific handoff adapter; canonical engine remains unchanged."""
from pathlib import Path
from integrations.antigravity.factory.authority import verify_mission_packet, AuthorityError
from integrations.antigravity.factory.scheduler import FactoryJournal, build_topological_waves, enforce_wave_budget
from integrations.antigravity.factory.policy import assert_operation_allowed
from integrations.antigravity.factory.quality import SelfHealingController

def plan_sequential(packets, *, expected_repo, observed_base_sha, trusted_verifiers):
    """Plan only; a plan does not acquire a native session or lease."""
    if not trusted_verifiers:
        raise AuthorityError("Trusted verifier authority is required")
    for packet in packets:
        verify_mission_packet(packet, expected_repo=expected_repo,
            observed_base_sha=observed_base_sha, trusted_verifiers=trusted_verifiers)
    waves = build_topological_waves(packets)
    by_id = {p["mission_id"]: p for p in packets}
    handoffs = []
    for wave in waves:
        # No concurrent launch without an actual native session ledger. Each
        # singleton wave preserves the DAG and counts primary + worker = 2.
        for mid in wave:
            enforce_wave_budget([by_id[mid]])
            handoffs.append(mid)
    return {"status": "PLANNED_ONLY", "sequential_handoffs": handoffs,
            "max_active_including_primary": 3, "native_context_created": False}

def prepare_handoff(packet, *, expected_repo, observed_base_sha, trusted_verifiers, journal_path):
    if not trusted_verifiers:
        raise AuthorityError("Trusted verifier authority is required")
    verify_mission_packet(packet, expected_repo=expected_repo,
        observed_base_sha=observed_base_sha, trusted_verifiers=trusted_verifiers)
    assert_operation_allowed(packet, "READ")
    journal = FactoryJournal(Path(journal_path))
    if not journal.verify_hash_chain():
        raise AuthorityError("Journal hash-chain invalid")
    record = journal.register_mission(packet)
    return {"status": "SEPARATE_SESSION_REQUIRED", "packet": packet,
            "journal_state": record["state"], "context_id": None,
            "native_context_created": False, "independent_review": False}

def repair_controller():
    return SelfHealingController(max_repair_cycles=5, max_identical_retries=2)
