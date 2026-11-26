"""ChatGPT-first handoff and source-only candidate evidence.

Operator-supplied configuration is not an authenticated native grant.
No connector invocation, patch application, commit, ref update or delivery.
"""
from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

from .authority import AuthorityError
from .mission_contract import parse_mission_packet, contract_digest
from .policy import assert_paths_within_ownership
from .ownership import parse_git_raw_z_diff
from .skill_registry import PinnedGitSources, SkillRegistry, require, sha_ok
from .skill_loading import FixtureSkillRuntime
from .workflow_stages import workflow_stages

FORGE_REPOSITORY_ID = 1377058358
FORGE_REPOSITORY = "Kirjane/Operation-FORGE.kirion"


def supervised_handoff(raw, registry, config, *, workflow):
    packet = parse_mission_packet(raw)
    require(packet["schema_version"] == 2, "SUPERVISED_V2_CONTRACT_REQUIRED")
    stages = workflow_stages(workflow)
    require(bool(stages), "SUPERVISED_WORKFLOW_UNKNOWN")
    require(type(config) is dict and config.get("host") == "chatgpt",
            "SUPERVISED_CHATGPT_CONFIG_REQUIRED")
    # This runtime is used solely for retrieval. No signing key leaves the
    # process and no fixture/native consumption receipt is generated.
    runtime = FixtureSkillRuntime(registry, configs={contract_digest(packet): config},
                                  signing_key=secrets.token_bytes(32))
    bundle = runtime.manual_context(packet)
    require("kirion-session-host" in bundle["plan"]["required"], "SESSION_HOST_SKILL_REQUIRED")
    target = {key: packet[key] for key in ("repo_id", "repo_name", "base_sha", "permitted_branch")}
    return {"status": "SUPERVISED_HANDOFF_PREPARED", "contract_sha256": contract_digest(packet),
            "revision": packet["revision"], "run_id": packet["run_id"], "target": target,
            "authorization_ref": packet["authorization_ref"], "role": packet["formal_role"],
            "persona": packet["assigned_persona"], "owned_paths": packet["owned_paths"],
            "excluded_paths": packet["excluded_paths"], "allowed_operations": packet["allowed_operations"],
            "stop_conditions": packet["stop_conditions"], "required_gates": packet["required_gates"],
            "objective": packet["objective"], "workflow": workflow, "stages": stages,
            "context": bundle, "actor_status": "OPERATOR_REPORTED_NOT_AUTHENTICATED",
            "next_action": "OPERATOR_OPEN_SEPARATE_CHATGPT_SESSION_AND_VERIFY_ACTUAL_CONNECTOR",
            "start_receipt_required": True, "close_receipt_required": True,
            "native_execution": "UNAVAILABLE", "native_loading_verified": False,
            "write_authorized_by_harness": False, "promotion_authorized": False,
            "remote_invoked": False, "replay_permitted": False}


def inspect_supervised_candidate(raw, *, target_root, candidate_sha):
    """Read actual immutable Git candidate objects in an operator-mapped store.

    No arbitrary command, checkout, patch application or remote read. A local
    tree observation is not an authenticated GitHub ref or independent review.
    """
    packet = parse_mission_packet(raw)
    require(packet["schema_version"] == 2 and sha_ok(candidate_sha), "SUPERVISED_CANDIDATE_INVALID")
    require(candidate_sha != packet["base_sha"], "CANDIDATE_EQUALS_BASE")
    root = Path(target_root).resolve(strict=True)
    store = PinnedGitSources({packet["repo_id"]: (packet["repo_name"], root)})
    for sha in (packet["base_sha"], candidate_sha):
        require(store._git(root, "rev-parse", "--verify", sha + "^{commit}").decode("ascii").strip() == sha,
                "CANDIDATE_COMMIT_MISMATCH")
    store._git(root, "merge-base", "--is-ancestor", packet["base_sha"], candidate_sha)
    raw_diff = store._git(root, "diff", "--raw", "-z", "--no-renames", packet["base_sha"], candidate_sha)
    paths, forbidden = parse_git_raw_z_diff(raw_diff.decode("utf-8", errors="strict"))
    require(bool(paths) and not forbidden, "CANDIDATE_EFFECT_UNSUPPORTED")
    policy_status, denial = "PATHS_WITHIN_DECLARED_OWNERSHIP", None
    try:
        assert_paths_within_ownership(packet, paths)
    except AuthorityError as exc:
        policy_status, denial = "POLICY_NOT_AUTHORIZED", str(exc)
    tree = store._git(root, "rev-parse", candidate_sha + "^{tree}").decode("ascii").strip()
    require(sha_ok(tree), "CANDIDATE_TREE_INVALID")
    return {"status": "SOURCE_OBSERVATION_ONLY", "contract_sha256": contract_digest(packet),
            "run_id": packet["run_id"], "revision": packet["revision"], "candidate_sha": candidate_sha,
            "tree_sha": tree, "base_sha": packet["base_sha"], "changed_paths": paths,
            "raw_diff_sha256": hashlib.sha256(raw_diff).hexdigest(),
            "path_policy": policy_status, "path_policy_reason": denial,
            "repository_mapping": "OPERATOR_CONFIGURED_LOCAL_STORE", "independent": False,
            "native_actor_verified": False, "remote_head_verified": False,
            "actual_product_outcome": "NOT_TESTED", "acceptance": "NOT_EVALUATED",
            "write_authorized_by_harness": False, "promotion_authorized": False, "remote_invoked": False}
