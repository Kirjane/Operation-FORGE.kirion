"""F06 — Mission and authority contracts, JSON Schema validation, and lifecycle state machine."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from . import REPO_ROOT, SCHEMAS_ROOT

SHA40_RE = re.compile(r"^[0-9a-f]{40}\Z")
ZERO_SHA40 = "0" * 40
SHA256_RE = re.compile(r"^[0-9a-f]{64}\Z")
MISSION_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,63}\Z")
REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
GATE_ID_RE = re.compile(r"^G(0[0-9]|1[0-5])\Z")


def is_valid_git_sha(sha: Any) -> bool:
    """Return True iff sha is a lowercase 40-hex Git SHA and not the all-zero placeholder."""
    return isinstance(sha, str) and bool(SHA40_RE.fullmatch(sha)) and sha != ZERO_SHA40

CANONICAL_STATES = (
    "PLANNED",
    "AUTHORIZED",
    "ACTIVE",
    "READY",
    "UNDER_REVIEW",
    "ACCEPTED",
    "REWORK",
    "REJECTED",
    "QUARANTINED",
    "INTEGRATED",
    "PROMOTED",
    "OBSERVED",
    "BLOCKED",
)

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "PLANNED": {"AUTHORIZED", "BLOCKED", "QUARANTINED"},
    "AUTHORIZED": {"ACTIVE", "BLOCKED", "QUARANTINED"},
    "ACTIVE": {"READY", "BLOCKED", "QUARANTINED"},
    "READY": {"UNDER_REVIEW", "BLOCKED", "QUARANTINED"},
    "UNDER_REVIEW": {"ACCEPTED", "REWORK", "REJECTED", "QUARANTINED", "BLOCKED"},
    "REWORK": {"ACTIVE", "BLOCKED", "QUARANTINED"},
    "ACCEPTED": {"INTEGRATED", "PROMOTED", "BLOCKED", "QUARANTINED"},
    "INTEGRATED": {"PROMOTED", "REWORK", "BLOCKED", "QUARANTINED"},
    "PROMOTED": {"OBSERVED", "BLOCKED", "QUARANTINED"},
    "OBSERVED": set(),
    "REJECTED": set(),
    "QUARANTINED": set(),
    "BLOCKED": {"AUTHORIZED", "ACTIVE", "QUARANTINED"},
}

VALID_PERSONAS = {
    "Antigravity-Maintainer",
    "Antigravity-Lucien",
    "Antigravity-Jane",
    "Antigravity-Nox",
    "Antigravity-Argon",
    "Antigravity-Iris",
    "Antigravity-QA",
    "Antigravity-Aegis",
    "Antigravity-Integrator",
    "Antigravity-Scribe",
}

VALID_FORMAL_ROLES = {"Maintainer", "Code Writer", "Integration Writer", "Reviewer"}
VALID_RISK_CLASSES = {"RISK-0", "RISK-1", "RISK-2", "RISK-3", "RISK-4"}
VALID_OPERATIONS = {
    "READ",
    "WRITE_OWNED",
    "RUN_GATE",
    "REVIEW_READONLY",
    "INTEGRATE_BRANCH",
    "DELIVER_DRAFT_PR",
}


class AuthorityError(ValueError):
    """Raised when a mission packet, state transition, or git authority check fails."""


def _compile_schema_pattern(pattern: str) -> re.Pattern[str]:
    """Compile JSON Schema regex preventing Python '$' from matching before a trailing newline."""
    anchored = re.sub(r"(?<!\\)\$$", r"\\Z", pattern)
    return re.compile(anchored)


def _json_equal(a: Any, b: Any) -> bool:
    """Strict JSON Schema value equality distinguishing bool from int/float."""
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_json_equal(x, y) for x, y in zip(a, b))
    return a == b


def validate_against_schema(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Deterministic JSON Schema Draft 2020-12 structural and constraint validator using stdlib."""
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type is not None:
        allowed_types = expected_type if isinstance(expected_type, list) else [expected_type]
        type_ok = False
        for t in allowed_types:
            if t == "object" and isinstance(instance, dict):
                type_ok = True
            elif t == "array" and isinstance(instance, list):
                type_ok = True
            elif t == "string" and isinstance(instance, str):
                type_ok = True
            elif t == "integer" and isinstance(instance, int) and not isinstance(instance, bool):
                type_ok = True
            elif t == "number" and isinstance(instance, (int, float)) and not isinstance(instance, bool):
                type_ok = True
            elif t == "boolean" and isinstance(instance, bool):
                type_ok = True
            elif t == "null" and instance is None:
                type_ok = True
        if not type_ok:
            return [f"{path}: expected type {expected_type}, got {type(instance).__name__}"]

    if "const" in schema and not _json_equal(instance, schema["const"]):
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")

    if "enum" in schema and not any(_json_equal(instance, item) for item in schema["enum"]):
        errors.append(f"{path}: value {instance!r} not in enum {schema['enum']}")

    if isinstance(instance, str):
        if "\x00" in instance:
            errors.append(f"{path}: null byte forbidden in string")
        min_len = schema.get("minLength")
        if min_len is not None and len(instance) < min_len:
            errors.append(f"{path}: string length {len(instance)} < minLength {min_len}")
        pattern = schema.get("pattern")
        if pattern is not None:
            if not _compile_schema_pattern(pattern).search(instance):
                errors.append(f"{path}: string {instance!r} does not match pattern {pattern}")

    elif isinstance(instance, int) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and instance < minimum:
            errors.append(f"{path}: {instance} < minimum {minimum}")
        if maximum is not None and instance > maximum:
            errors.append(f"{path}: {instance} > maximum {maximum}")

    elif isinstance(instance, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if min_items is not None and len(instance) < min_items:
            errors.append(f"{path}: array length {len(instance)} < minItems {min_items}")
        if max_items is not None and len(instance) > max_items:
            errors.append(f"{path}: array length {len(instance)} > maxItems {max_items}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(instance):
                errors.extend(validate_against_schema(item, item_schema, f"{path}[{idx}]"))

    elif isinstance(instance, dict):
        required = schema.get("required", [])
        for req_key in required:
            if req_key not in instance:
                errors.append(f"{path}: missing required property {req_key!r}")
        props = schema.get("properties", {})
        add_props = schema.get("additionalProperties", True)
        for key, val in instance.items():
            if key in props:
                errors.extend(validate_against_schema(val, props[key], f"{path}.{key}"))
            elif add_props is False:
                errors.append(f"{path}: unexpected additional property {key!r}")
            elif isinstance(add_props, dict):
                errors.extend(validate_against_schema(val, add_props, f"{path}.{key}"))

    return errors


def load_schema(schema_name: str, *, base_dir: Path = SCHEMAS_ROOT) -> dict[str, Any]:
    path = base_dir / schema_name
    if not path.is_file():
        raise AuthorityError(f"Missing schema file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(instance: Any, schema_filename: str, *, base_dir: Path = SCHEMAS_ROOT) -> None:
    schema = load_schema(schema_filename, base_dir=base_dir)
    errors = validate_against_schema(instance, schema)
    if errors:
        raise AuthorityError(f"Schema validation failed for {schema_filename}: {'; '.join(errors)}")


def verify_mission_packet(
    packet: dict[str, Any],
    *,
    expected_repo: str | None = None,
    observed_base_sha: str | None = None,
    trusted_verifiers: set[str] | None = None,
) -> dict[str, Any]:
    """Fail-closed verification of a MissionPacket against schema, authority, ownership, risk-floor gates, and role invariants."""
    from .policy import (
        PERSONA_PERMISSIONS,
        is_prohibited_branch,
        is_protected_governance_path,
        normalize_rel_path,
    )
    from .quality import (
        GATE_CATALOG,
        MANDATORY_NON_EXEMPTIBLE_GATES,
        RISK_REQUIRED_GATES,
    )

    validate_contract(packet, "mission-packet.schema.json")

    if not is_valid_git_sha(packet["base_sha"]):
        raise AuthorityError(f"Invalid or all-zero base_sha forbidden: {packet['base_sha']!r}")
    if not is_valid_git_sha(packet["selected_skills"]["skill_source_sha"]):
        raise AuthorityError("Invalid or all-zero selected_skills.skill_source_sha forbidden.")

    if packet.get("work_mode") == "PAUSED" and (
        set(packet.get("allowed_operations", [])) & {"WRITE_OWNED", "INTEGRATE_BRANCH", "DELIVER_DRAFT_PR"}
    ):
        raise AuthorityError("PAUSED work_mode forbids WRITE_OWNED, INTEGRATE_BRANCH, and DELIVER_DRAFT_PR operations.")

    branch = packet["permitted_branch"]
    if is_prohibited_branch(branch):
        raise AuthorityError(f"MissionPacket cannot authorize direct mutation on protected/invalid branch {branch!r}.")

    for owned in packet["owned_paths"]:
        norm = normalize_rel_path(owned)
        if is_protected_governance_path(norm):
            raise AuthorityError(f"MissionPacket owned_paths cannot claim protected governance file {owned!r}.")

    if expected_repo is not None and packet["repo_name"] != expected_repo:
        raise AuthorityError(f"Repository mismatch: packet={packet['repo_name']!r} expected={expected_repo!r}")

    if observed_base_sha is not None and packet["base_sha"] != observed_base_sha:
        raise AuthorityError(f"Stale base_sha: packet={packet['base_sha']} observed={observed_base_sha}")

    allowed_verifiers = trusted_verifiers or {"Engineer:Kirch-Ivan-Balite", "Maintainer:Kirch-Nairu"}
    if packet["verifier"] not in allowed_verifiers:
        raise AuthorityError(f"Untrusted authorization verifier: {packet['verifier']!r}")

    if not packet["authorization_ref"].startswith(("https://github.com/", "ISSUE-", "PR-", "FORGE-AUTH-")):
        raise AuthorityError(f"Invalid authorization_ref format: {packet['authorization_ref']!r}")

    req_gates = set(packet["required_gates"])
    missing_mandatory = sorted(MANDATORY_NON_EXEMPTIBLE_GATES - req_gates)
    if missing_mandatory:
        raise AuthorityError(
            f"MissionPacket.required_gates must include mandatory anchor gates {missing_mandatory}."
        )
    na_gates = packet.get("non_applicable_gates") or {}
    for gid, reason in na_gates.items():
        if gid not in GATE_CATALOG:
            raise AuthorityError(f"Unknown gate ID in MissionPacket.non_applicable_gates: {gid!r}")
        if gid in MANDATORY_NON_EXEMPTIBLE_GATES:
            raise AuthorityError(f"Mandatory anchor gate {gid} cannot be exempted via MissionPacket.non_applicable_gates.")
        if not isinstance(reason, str) or not reason.strip():
            raise AuthorityError(f"MissionPacket.non_applicable_gates[{gid!r}] requires a non-empty justification.")
    overlap_gates = sorted(req_gates & set(na_gates.keys()))
    if overlap_gates:
        raise AuthorityError(
            f"MissionPacket cannot list gates {overlap_gates} in both required_gates and non_applicable_gates."
        )
    risk_floor = set(RISK_REQUIRED_GATES[packet["risk_class"]])
    missing_floor = sorted(risk_floor - (req_gates | set(na_gates.keys())))
    if missing_floor:
        raise AuthorityError(
            f"MissionPacket for {packet['risk_class']} omits required risk-floor gates {missing_floor} "
            "without explicit documented non_applicable_gates justification."
        )

    persona = packet["assigned_persona"]
    role = packet["formal_role"]
    spec = PERSONA_PERMISSIONS.get(persona)
    if spec is None:
        raise AuthorityError(f"Unrecognized assigned_persona: {persona!r}")
    if role not in spec["formal_roles"]:
        raise AuthorityError(f"Persona {persona!r} cannot hold formal_role {role!r}; allowed: {sorted(spec['formal_roles'])}")

    allowed_ops = set(packet["allowed_operations"])
    if role == "Reviewer" and (allowed_ops & {"WRITE_OWNED", "INTEGRATE_BRANCH", "DELIVER_DRAFT_PR"}):
        raise AuthorityError("Reviewer formal_role cannot be granted write, integration, or delivery operations.")

    # Each operation in allowed_operations must be allowed by the persona (except DELIVER_DRAFT_PR which
    # is exercised by Antigravity-Maintainer after writer authority return on writer/integrator packets).
    permitted_for_packet = set(spec["allowed_ops"])
    if role in ("Code Writer", "Integration Writer"):
        permitted_for_packet.add("DELIVER_DRAFT_PR")
    disallowed_ops = allowed_ops - permitted_for_packet
    if disallowed_ops:
        raise AuthorityError(
            f"MissionPacket grants operations {sorted(disallowed_ops)} not permitted for {persona} ({role})."
        )

    return packet


def validate_lifecycle_transition(
    current_state: str,
    next_state: str,
    *,
    actor_role: str,
    is_author: bool = False,
) -> str:
    """Enforce canonical Forge lifecycle state transitions and anti-self-promotion rules."""
    if current_state not in CANONICAL_STATES:
        raise AuthorityError(f"Unknown current lifecycle state: {current_state!r}")
    if next_state not in CANONICAL_STATES:
        raise AuthorityError(f"Unknown target lifecycle state: {next_state!r}")
    if next_state not in ALLOWED_TRANSITIONS.get(current_state, set()):
        raise AuthorityError(f"Illegal lifecycle transition: {current_state} -> {next_state}")

    if next_state in ("ACCEPTED", "PROMOTED"):
        if is_author:
            raise AuthorityError(f"Core Law 3 violation: author cannot transition own candidate to {next_state}.")
        if actor_role not in ("Acceptance Agent", "Engineer"):
            raise AuthorityError(f"Transition to {next_state} requires Acceptance Agent or Engineer authority, got {actor_role!r}.")

    if next_state == "INTEGRATED" and actor_role not in ("Integration Writer", "Maintainer"):
        raise AuthorityError(f"Transition to INTEGRATED requires Integration Writer or Maintainer, got {actor_role!r}.")

    return next_state


def verify_git_authority(
    repo_root: Path = REPO_ROOT,
    *,
    expected_head_sha: str | None = None,
    expected_branch: str | None = None,
) -> dict[str, Any]:
    """Directly observe live Git HEAD SHA, branch, and working-tree cleanliness (fail-closed on git errors)."""
    head_p = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if head_p.returncode != 0:
        raise AuthorityError(f"Failed to read git HEAD in {repo_root}: {head_p.stderr.strip()}")
    head_sha = head_p.stdout.strip()
    if not is_valid_git_sha(head_sha):
        raise AuthorityError(f"Invalid 40-char git HEAD SHA observed: {head_sha!r}")

    branch_p = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if branch_p.returncode != 0:
        raise AuthorityError(f"Failed to read git branch in {repo_root}: {branch_p.stderr.strip()}")
    branch = branch_p.stdout.strip()

    status_p = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if status_p.returncode != 0:
        raise AuthorityError(f"Failed to read git status in {repo_root}: {status_p.stderr.strip()}")
    dirty = bool(status_p.stdout.strip())

    if expected_head_sha is not None and head_sha != expected_head_sha:
        raise AuthorityError(f"Git SHA drift detected: expected {expected_head_sha}, observed {head_sha}")
    if expected_branch is not None and branch != expected_branch:
        raise AuthorityError(f"Git branch mismatch: expected {expected_branch!r}, observed {branch!r}")

    return {
        "repo_root": str(repo_root),
        "head_sha": head_sha,
        "branch": branch,
        "dirty": dirty,
    }
