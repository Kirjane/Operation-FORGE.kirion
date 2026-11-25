"""Strict MissionPacket protocol and immutable authorization projection.

Structural validation is not proof of authority, source relevance or host capability.
The only resolver shipped here is the isolated fixture boundary in dispatch_preflight.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .authority import AuthorityError, is_valid_git_sha, validate_contract, verify_packet_policy
from .policy import normalize_rel_path, path_matches_prefix, MUTATING_OPERATIONS

# Only these arrays have set semantics. All other arrays, including argv, precedence,
# outcome presentation, skill order and stop conditions, retain their input order.
SET_FIELDS = {
    "owned_paths", "excluded_paths", "owned_modules", "owned_behaviors", "depends_on",
    "required_gates", "allowed_operations", "oracle_ids", "outcome_ids", "scope",
    "grant_scope", "permitted_revision_fields",
}
CAPABILITY_FLOORS = {
    "READ": "repository_read",
    "WRITE_OWNED": "scoped_worktree_write",
    "RUN_GATE": "local_command_execution",
    "REVIEW_READONLY": "independent_review_context",
    "INTEGRATE_BRANCH": "branch_integration",
    "DELIVER_DRAFT_PR": "github_draft_delivery",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorityError(message)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj = {}
    for key, value in pairs:
        _require(key not in obj, f"Duplicate JSON key: {key}")
        obj[key] = value
    return obj


def _invalid_constant(value: str) -> Any:
    raise AuthorityError(f"Nonfinite JSON constant: {value}")


def _check_json(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _require(type(key) is str, "JSON object keys must be strings")
            _check_json(key)
            _check_json(item)
    elif isinstance(value, list):
        for item in value:
            _check_json(item)
    elif type(value) is str:
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise AuthorityError("Invalid Unicode in mission packet") from exc
        _require("\x00" not in value, "NUL in mission packet")
    elif type(value) is float:
        _require(math.isfinite(value), "Nonfinite JSON number")
    else:
        _require(value is None or type(value) in (int, bool), "Non-JSON value in mission packet")


def parse_mission_packet(raw: str | bytes) -> dict[str, Any]:
    """Raw ingress rejects duplicates even inside nested objects, unknown versions and nonfinite values."""
    _require(type(raw) in (str, bytes), "Mission ingress requires raw JSON")
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="strict")
        packet = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
        _check_json(packet)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise AuthorityError(f"Invalid mission JSON: {exc}") from exc
    _require(isinstance(packet, dict) and type(packet.get("schema_version")) is int
             and packet["schema_version"] in (1, 2), "Unknown mission protocol version")
    if packet["schema_version"] == 1:
        validate_contract(packet, "mission-packet.schema.json")
    else:
        validate_mission_contract(packet)
    return packet


def canonical_json(value: Any) -> str:
    _check_json(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_sets(value: Any, field: str = "") -> Any:
    if isinstance(value, dict):
        return {key: _normalize_sets(item, key) for key, item in value.items()}
    if isinstance(value, list):
        items = [_normalize_sets(item) for item in value]
        if field in SET_FIELDS:
            _require(len({canonical_json(item) for item in items}) == len(items),
                     f"Duplicate set element in {field}")
            return sorted(items, key=canonical_json)
        return items
    return value


def contract_projection(packet: dict[str, Any]) -> dict[str, Any]:
    """Protocol v2: every declared field except run_id; no digest or signature self-reference."""
    validate_mission_contract(packet)
    return _normalize_sets({key: value for key, value in packet.items() if key != "run_id"})


# These fields identify the independently resolved grant envelope, not the
# substantive policy inherited from the predecessor. New policy fields default
# to immutable until a revision mechanism explicitly supports them.
_GRANT_ENVELOPE_FIELDS = frozenset({
    "issuer_actor_id", "issuer_role", "directive_ref", "directive_sha256", "parent_grant_ref",
})
_REVISION_ENVELOPE_FIELDS = frozenset({
    "revision", "previous_contract_sha256", "revision_reason", "authorization_ref",
})


def revision_changes(prior: dict[str, Any], successor: dict[str, Any]) -> set[str]:
    """Compare authorized content, not provenance renewal.

    Nested substantive authority is immutable in this protocol slice, including
    source precedence, Brain requirements, revision permissions and verifier.
    Grant scope may change only as the validated projection of allowed_operations;
    that operation change still needs predecessor permission. Future nested
    policy fields are not silently treated as envelope metadata.
    """
    before, after = contract_projection(prior), contract_projection(successor)
    changes = {key for key in before.keys() | after.keys()
               if key not in _REVISION_ENVELOPE_FIELDS and key != "authority"
               and canonical_json(before.get(key)) != canonical_json(after.get(key))}
    old_policy, new_policy = before["authority"], after["authority"]
    for key in old_policy.keys() | new_policy.keys():
        if key in _GRANT_ENVELOPE_FIELDS:
            continue
        if (key in old_policy and key in new_policy and
                canonical_json(old_policy[key]) == canonical_json(new_policy[key])):
            continue
        if (key == "grant_scope" and "allowed_operations" in changes
                and old_policy.get(key) == before["allowed_operations"]
                and new_policy.get(key) == after["allowed_operations"]):
            continue
        changes.add("authority." + key)
    return changes


def contract_digest(packet: dict[str, Any]) -> str:
    return digest_json(contract_projection(packet))


def _paths(paths: list[str]) -> None:
    folded = set()
    for raw in paths:
        _require(normalize_rel_path(raw) == raw and not any(char in raw for char in '<>:"|')
                 and all(not segment.endswith((" ", ".")) for segment in raw.split("/"))
                 and all(ord(char) >= 32 and ord(char) != 127 for char in raw),
                 f"Noncanonical or unsafe path: {raw!r}")
        _require(raw.lower() not in folded, f"Duplicate path: {raw}")
        folded.add(raw.lower())


def _indexed(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    indexed = {item[key]: item for item in items}
    _require(len(indexed) == len(items), f"Duplicate {key}")
    return indexed


def _nonblank(value: Any, field: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _nonblank(item, key)
    elif isinstance(value, list):
        for item in value:
            _nonblank(item, field)
    elif isinstance(value, str) and field != "command_argv" and field != "gate_commands":
        _require(bool(value.strip()), f"Blank {field}")


def validate_mission_contract(packet: dict[str, Any]) -> dict[str, Any]:
    """Use the explicit v2 schema and enforce cross-field semantics in the stdlib path."""
    from .quality import GATE_CATALOG, EVIDENCE_LEVEL_ORDER, GATE_ALLOWED_PASS_EVIDENCE_TYPES

    _check_json(packet)
    validate_contract(packet, "mission-packet-v2.schema.json")
    verify_packet_policy(packet)
    _nonblank(packet)
    _normalize_sets(packet)
    revision = packet["revision"]
    previous = packet["previous_contract_sha256"]
    _require((revision == 1 and previous is None) or
             (revision > 1 and previous is not None and previous != "0" * 64),
             "Revision predecessor mismatch")
    _require(packet["mission_id"] not in packet["depends_on"], "Self dependency")
    _require(packet["authorization_ref"] == packet["authority"]["directive_ref"], "Grant ref projection mismatch")
    _require(packet["authority"]["directive_sha256"] != "0" * 64, "Empty directive digest")
    _require((revision == 1) == (packet["authority"]["parent_grant_ref"] is None),
             "Parent grant reference mismatch")
    ops = set(packet["allowed_operations"])
    _paths(packet["owned_paths"])
    _paths(packet["excluded_paths"])
    _require(not ops.intersection(MUTATING_OPERATIONS) or bool(packet["owned_paths"]),
             "Mutating contract requires owned scope")
    _require(set(packet["authority"]["grant_scope"]) == ops, "Grant operation scope mismatch")
    if packet.get("work_mode") == "PAUSED":
        _require(not ops.intersection(MUTATING_OPERATIONS), "Paused mutation denied")
    _require(set(packet["authority"]["permitted_revision_fields"]) <=
             (set(packet) - {"schema_version", "mission_id", "run_id", "revision", "previous_contract_sha256", "revision_reason", "authority", "authorization_ref", "verifier"}),
             "Unknown or immutable revision field")

    sources = _indexed(packet["source_authorities"], "source_id")
    precedence = packet["authority"]["source_precedence"]
    _require(len(precedence) == len(sources) and set(precedence) == set(sources), "Source precedence must cover every source exactly once")
    for source in sources.values():
        _paths(source["scope"])
        _require(is_valid_git_sha(source["commit_sha"]), "Invalid source commit")
        if source["repository_id"] == packet["repo_id"]:
            _require(source["repository_name"] == packet["repo_name"], "Source repository identity mismatch")
        if source["repository_name"] == packet["repo_name"]:
            _require(source["repository_id"] == packet["repo_id"], "Source repository ID mismatch")

    outcomes = _indexed(packet["objective"]["outcomes"], "outcome_id")
    oracles = _indexed(packet["oracles"], "oracle_id")
    _require(packet["acceptance_criteria"] == [outcome["expected"] for outcome in outcomes.values()],
             "Acceptance criteria must project ordered outcome expectations")
    commands = {}
    for oracle_id, oracle in oracles.items():
        source = sources.get(oracle["source_id"])
        _require(source is not None and source["authority_kind"] != "REFERENCE", "Oracle lacks authoritative source")
        _paths([oracle["path"]])
        _require(any(path_matches_prefix(oracle["path"], prefix) for prefix in source["scope"]), "Oracle outside source scope")
        _require(is_valid_git_sha(oracle["blob_sha"]), "Invalid oracle blob SHA")
        _require(oracle["fixture_sha256"] != "0" * 64, "Invalid fixture digest")
        gate = oracle["gate_id"]
        _require(gate in packet["required_gates"], "Oracle gate not applicable")
        _require(oracle["evidence_type"] in GATE_ALLOWED_PASS_EVIDENCE_TYPES[gate] and
                 EVIDENCE_LEVEL_ORDER[oracle["minimum_evidence_level"]] >=
                 EVIDENCE_LEVEL_ORDER[GATE_CATALOG[gate]["min_evidence"]], "Oracle weakens gate evidence floor")
        argv = oracle["command_argv"]
        _require((oracle["evaluation_kind"] == "COMMAND" and argv and bool(argv[0].strip())) or
                 (oracle["evaluation_kind"] == "REVIEWED_OBSERVATION" and argv is None),
                 "Oracle evaluation kind/argv mismatch")
        if argv is not None:
            _require(gate not in commands or commands[gate] == argv, "Conflicting legacy gate command projection")
            commands[gate] = argv
        for outcome_id in oracle["outcome_ids"]:
            _require(outcome_id in outcomes and oracle_id in outcomes[outcome_id]["oracle_ids"],
                     "Unbound oracle outcome")
    for outcome_id, outcome in outcomes.items():
        for oracle_id in outcome["oracle_ids"]:
            _require(oracle_id in oracles and outcome_id in oracles[oracle_id]["outcome_ids"],
                     "Unbound outcome oracle")
    _require(packet.get("gate_commands", {}) == commands, "Gate commands must project authorized argv")

    capabilities = _indexed(packet["required_capabilities"], "capability_id")
    for cap in capabilities.values():
        _paths(cap["scope"])
        _require(cap["operation"] in ops, "Capability operation outside contract")
    for op in ops:
        cap = capabilities.get(CAPABILITY_FLOORS[op])
        _require(cap is not None and cap["operation"] == op, f"Missing capability floor for {op}")
        if op == "READ":
            _require(all(any(path_matches_prefix(path, prefix) for prefix in cap["scope"])
                         for source in sources.values() for path in source["scope"]),
                     "Repository read capability must cover declared source scopes")
        if op in MUTATING_OPERATIONS:
            _require(all(any(path_matches_prefix(path, prefix) for prefix in cap["scope"])
                         for path in packet["owned_paths"]), f"Capability scope too narrow for {op}")
    if packet["formal_role"] == "Reviewer":
        cap = capabilities.get("independent_review_context")
        _require(cap is not None and cap["independence_required"], "Reviewer requires independent context")
    for oracle in oracles.values():
        if oracle["evaluation_kind"] == "COMMAND":
            cap = capabilities.get("local_command_execution")
            _require(cap is not None and cap["environment"] == oracle["environment"] and
                     any(path_matches_prefix(oracle["path"], scope) for scope in cap["scope"]),
                     "Oracle requires command capability with matching scope/environment")
        if oracle["target_profile"] == "REAL":
            cap = capabilities.get("actual_runtime_observation")
            _require(cap is not None and cap["environment"] == oracle["environment"],
                     "Real oracle requires runtime observation capability")

    cognition = packet["cognition"]
    refs = ("brain_run_id", "context_sha256", "manifest_ref", "target_binding")
    if cognition["mode"] == "INHERITED":
        _require(all(cognition[key] is not None and cognition[key] != "0" * 64 for key in refs)
                 and cognition["reason"] is None and packet["cognition_hash"] == cognition["context_sha256"],
                 "Inherited cognition requires matching provenance")
        _require(cognition["target_binding"] == digest_json({key: packet[key] for key in
                 ("repo_id", "repo_name", "base_sha", "permitted_branch")}), "Cognition target mismatch")
    else:
        _require(all(cognition[key] is None for key in refs) and packet["cognition_hash"] is None
                 and bool(cognition["reason"]) and not packet["authority"]["brain_required"],
                 "Omitted/unavailable cognition must be explicit and optional")
    return packet
