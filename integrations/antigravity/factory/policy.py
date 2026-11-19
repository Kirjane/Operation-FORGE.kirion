"""F06 / F08 / F16 — Deny-by-default policy engine, protected surface guards, and prompt-injection defense."""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from .authority import AuthorityError

UNCONDITIONALLY_DENIED_OPERATIONS = {
    "FORCE_PUSH",
    "MERGE_PR",
    "DELETE_REF",
    "ADMIN_MUTATION",
    "PRODUCTION_DEPLOY",
    "RESET_CLIENT_DATA",
    "GLOBAL_PLUGIN_INSTALL",
    "SELF_APPROVE",
    "SELF_PROMOTE",
    "SECRET_EXFILTRATION",
    "BYPASS_HOOKS",
}

PROTECTED_GOVERNANCE_PATHS = {
    "AGENTS.md",
    "SYSTEM_BOUNDARY.md",
    "EVIDENCE_CROSSWALK.md",
    "SHARED_DOCS.sha256",
    "ENTITY.md",
    "ENTITY_MANIFEST.json",
    "FORGE_MANIFESTO.md",
    "FORGE_GLOSSARY.md",
    ".forge/AUTHORITY.md",
    ".forge/NEST.md",
    ".forge/SSOT_CURRENT.md",
}

PERSONA_PERMISSIONS: dict[str, dict[str, Any]] = {
    "Antigravity-Maintainer": {
        "formal_roles": {"Maintainer"},
        "allowed_ops": {"READ", "RUN_GATE", "DELIVER_DRAFT_PR"},
    },
    "Antigravity-Lucien": {
        "formal_roles": {"Code Writer", "Reviewer"},
        "allowed_ops": {"READ", "WRITE_OWNED", "RUN_GATE", "REVIEW_READONLY"},
    },
    "Antigravity-Jane": {
        "formal_roles": {"Code Writer"},
        "allowed_ops": {"READ", "WRITE_OWNED", "RUN_GATE"},
    },
    "Antigravity-Nox": {
        "formal_roles": {"Reviewer"},
        "allowed_ops": {"READ", "REVIEW_READONLY"},
    },
    "Antigravity-Argon": {
        "formal_roles": {"Code Writer"},
        "allowed_ops": {"READ", "WRITE_OWNED", "RUN_GATE"},
    },
    "Antigravity-Iris": {
        "formal_roles": {"Code Writer"},
        "allowed_ops": {"READ", "WRITE_OWNED", "RUN_GATE"},
    },
    "Antigravity-QA": {
        "formal_roles": {"Reviewer", "Code Writer"},
        "allowed_ops": {"READ", "REVIEW_READONLY", "RUN_GATE", "WRITE_OWNED"},
    },
    "Antigravity-Aegis": {
        "formal_roles": {"Reviewer"},
        "allowed_ops": {"READ", "REVIEW_READONLY", "RUN_GATE"},
    },
    "Antigravity-Integrator": {
        "formal_roles": {"Integration Writer"},
        "allowed_ops": {"READ", "WRITE_OWNED", "INTEGRATE_BRANCH", "RUN_GATE"},
    },
    "Antigravity-Scribe": {
        "formal_roles": {"Code Writer"},
        "allowed_ops": {"READ", "WRITE_OWNED"},
    },
}

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"(approve|merge|force[-\s]?push)\s+(this|the)\s+(pr|pull\s+request|branch)", re.IGNORECASE),
    re.compile(r"(exfiltrate|print|dump|upload)\s+(all\s+)?(env|environment|secrets|tokens|github_token|gh_token)", re.IGNORECASE),
    re.compile(r"bypass\s+(forge|nox|aegis|security|authority|gates)", re.IGNORECASE),
    re.compile(r"reset\s+(production|client)\s+(database|data|license)", re.IGNORECASE),
]


class PolicyViolationError(AuthorityError):
    """Raised when an operation, path mutation, or untrusted input violates deny-default policy."""


def normalize_rel_path(raw_path: str) -> str:
    cleaned = raw_path.replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if cleaned.startswith("/") or re.match(r"^[A-Za-z]:", cleaned):
        raise PolicyViolationError(f"Absolute path forbidden in relative path check: {raw_path!r}")
    parts = cleaned.split("/")
    if ".." in parts:
        raise PolicyViolationError(f"Parent directory traversal ('..') forbidden: {raw_path!r}")
    return str(PurePosixPath(cleaned))


def path_matches_prefix(candidate_rel: str, owned_prefix: str) -> bool:
    norm_cand = normalize_rel_path(candidate_rel)
    norm_pref = normalize_rel_path(owned_prefix.rstrip("/"))
    if norm_cand == norm_pref:
        return True
    return norm_cand.startswith(norm_pref + "/")


def assert_operation_allowed(
    packet: dict[str, Any],
    operation: str,
    *,
    actor_persona: str | None = None,
) -> None:
    """Deny-by-default check for any requested factory operation."""
    if operation in UNCONDITIONALLY_DENIED_OPERATIONS:
        raise PolicyViolationError(f"Operation {operation!r} is unconditionally denied by Forge factory policy.")

    persona = actor_persona or packet.get("assigned_persona", "")
    spec = PERSONA_PERMISSIONS.get(persona)
    if spec is None:
        raise PolicyViolationError(f"Unrecognized or spoofed persona: {persona!r}")

    if actor_persona is None or actor_persona == packet.get("assigned_persona"):
        formal_role = packet.get("formal_role")
        if formal_role not in spec["formal_roles"]:
            raise PolicyViolationError(f"Persona {persona!r} cannot assume formal_role {formal_role!r}")

    if operation not in spec["allowed_ops"]:
        raise PolicyViolationError(f"Persona {persona!r} is not permitted to perform {operation!r}")

    if operation not in set(packet.get("allowed_operations", [])):
        raise PolicyViolationError(f"Operation {operation!r} is not authorized in MissionPacket.allowed_operations")


def assert_paths_within_ownership(
    packet: dict[str, Any],
    changed_paths: list[str],
    *,
    allow_protected_governance: bool = False,
) -> list[str]:
    """Verify every touched file is inside MissionPacket.owned_paths and respects persona path restrictions."""
    assert_operation_allowed(packet, "WRITE_OWNED")
    owned_prefixes = packet.get("owned_paths", [])
    persona = packet.get("assigned_persona", "")
    validated: list[str] = []

    for raw in changed_paths:
        norm = normalize_rel_path(raw)
        if not allow_protected_governance and norm in PROTECTED_GOVERNANCE_PATHS:
            raise PolicyViolationError(f"Protected governance file {norm!r} cannot be modified by worker.")

        if not any(path_matches_prefix(norm, pref) for pref in owned_prefixes):
            raise PolicyViolationError(
                f"Out-of-scope file mutation denied: {norm!r} is not inside owned_paths {owned_prefixes}"
            )

        if persona == "Antigravity-Scribe" and not (
            norm.endswith((".md", ".json", ".txt")) or "/adr/" in f"/{norm}" or "/evidence/" in f"/{norm}"
        ):
            raise PolicyViolationError(f"Antigravity-Scribe is restricted to documentation/capsule paths, denied: {norm!r}")

        if persona == "Antigravity-Lucien" and not (
            norm.endswith((".md", ".schema.json", ".json")) or "/adr/" in f"/{norm}" or "/schemas/" in f"/{norm}"
        ):
            raise PolicyViolationError(f"Antigravity-Lucien is restricted to architecture/ADR/schema paths, denied: {norm!r}")

        if persona == "Antigravity-QA":
            if packet.get("formal_role") != "Code Writer":
                raise PolicyViolationError("Antigravity-QA requires explicit Code Writer role transition to write test files.")
            if not ("test" in norm.lower() or "benchmark" in norm.lower()):
                raise PolicyViolationError(f"Antigravity-QA test-writer scope forbids non-test path: {norm!r}")

        validated.append(norm)

    return validated


def scan_untrusted_text_for_injection(text: str) -> list[str]:
    """Detect prompt-injection or authority-escalation instructions embedded in untrusted data."""
    detections: list[str] = []
    for pat in PROMPT_INJECTION_PATTERNS:
        m = pat.search(text)
        if m:
            detections.append(m.group(0))
    return detections
