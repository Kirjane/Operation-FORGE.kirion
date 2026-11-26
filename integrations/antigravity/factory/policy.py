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
    "second-brain/AGENTS.md",
    "second-brain/SYSTEM_BOUNDARY.md",
    "second-brain/EVIDENCE_CROSSWALK.md",
    "second-brain/SHARED_DOCS.sha256",
}

PROTECTED_GOVERNANCE_PATHS_LOWER = {p.lower() for p in PROTECTED_GOVERNANCE_PATHS}

MUTATING_OPERATIONS = {"WRITE_OWNED", "INTEGRATE_BRANCH", "DELIVER_DRAFT_PR"}

PROHIBITED_BRANCH_NAMES_LOWER = {"main", "master", "head", "production", "release"}

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


QA_TEST_DIR_SEGMENTS = {"test", "tests", "__tests__", "spec", "specs", "benchmark", "benchmarks"}
QA_TEST_FILENAME_RE = re.compile(
    r"^(?:test_|spec_|benchmark_)"
    r"|(?:_test|_tests|_spec|_benchmark|\.test|\.tests|\.spec|\.benchmark)(?:\.[^.]+)+$"
    r"|(?:Test|Tests|Spec|Specs|Benchmark|Benchmarks)\.[A-Za-z0-9]+$"
)


def _is_qa_test_or_benchmark_path(norm_path: str) -> bool:
    """Segment- and filename-boundary matcher for QA-writable test/benchmark paths."""
    parts = PurePosixPath(norm_path).parts
    if not parts:
        return False
    if any(seg.lower() in QA_TEST_DIR_SEGMENTS for seg in parts[:-1]):
        return True
    return bool(QA_TEST_FILENAME_RE.search(parts[-1]))


def is_prohibited_branch(branch: str) -> bool:
    """Case-insensitive, refspec-rejecting check denying protected branches, refspecs, tags, globs, and invalid names."""
    if not isinstance(branch, str):
        return True
    raw = branch.strip()
    if not raw or raw != branch or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return True
    if any(tok in raw for tok in (":", "+", "~", "^", "?", "*", "[", "\\", "@{", "//", "..")):
        return True
    if raw.startswith(("-", "/", ".")) or raw.endswith(("/", ".", ".lock")):
        return True
    segments = raw.split("/")
    if any(not seg or seg.startswith(".") or seg.endswith(".lock") for seg in segments):
        return True

    low = raw.lower()
    if low.startswith(("refs/tags/", "tags/")):
        return True
    low = re.sub(r"^(?:refs/heads/|refs/remotes/[^/]+/|remotes/[^/]+/)", "", low)
    if low in PROHIBITED_BRANCH_NAMES_LOWER:
        return True
    if "/" in low:
        # Reject <remote>/<protected> (e.g., origin/main, upstream/main, fork/master)
        _first, rest = low.split("/", 1)
        if rest in PROHIBITED_BRANCH_NAMES_LOWER:
            return True
    return False


def is_protected_governance_path(rel_path: str) -> bool:
    """Case-insensitive governance path check (critical on Windows NTFS/macOS APFS), including .git metadata."""
    cleaned = rel_path.replace("\\", "/").strip()
    if any(part.lower() == ".git" for part in cleaned.split("/")):
        return True
    norm = normalize_rel_path(rel_path)
    return norm.lower() in PROTECTED_GOVERNANCE_PATHS_LOWER


def normalize_rel_path(raw_path: str) -> str:
    cleaned = raw_path.replace("\\", "/").strip()
    if not cleaned:
        raise PolicyViolationError("Empty relative path forbidden.")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if not cleaned or cleaned == ".":
        raise PolicyViolationError(f"Repository root path {raw_path!r} is overbroad and forbidden.")
    if cleaned.startswith("/") or re.match(r"^[A-Za-z]:", cleaned):
        raise PolicyViolationError(f"Absolute path forbidden in relative path check: {raw_path!r}")
    if any(ch in cleaned for ch in ("*", "?", "\x00", "\n", "\r")):
        raise PolicyViolationError(f"Wildcard or control character forbidden in path: {raw_path!r}")
    parts = cleaned.split("/")
    if ".." in parts:
        raise PolicyViolationError(f"Parent directory traversal ('..') forbidden: {raw_path!r}")
    if any(part.lower() == ".git" for part in parts):
        raise PolicyViolationError(f"Git metadata path ('.git') forbidden: {raw_path!r}")
    norm = str(PurePosixPath(cleaned))
    if norm in (".", "") or any(part.lower() == ".git" for part in PurePosixPath(norm).parts):
        raise PolicyViolationError(f"Overbroad or .git path forbidden: {raw_path!r}")
    return norm


def path_matches_prefix(candidate_rel: str, owned_prefix: str) -> bool:
    norm_cand = normalize_rel_path(candidate_rel)
    norm_pref = normalize_rel_path(owned_prefix.rstrip("/"))
    if norm_cand.lower() == norm_pref.lower():
        return True
    return norm_cand.lower().startswith(norm_pref.lower() + "/")


def assert_operation_allowed(
    packet: dict[str, Any],
    operation: str,
    *,
    actor_persona: str | None = None,
) -> None:
    """Deny-by-default check for any requested factory operation."""
    if operation in UNCONDITIONALLY_DENIED_OPERATIONS:
        raise PolicyViolationError(f"Operation {operation!r} is unconditionally denied by Forge factory policy.")

    if packet.get("work_mode") == "PAUSED" and operation in MUTATING_OPERATIONS:
        raise PolicyViolationError(f"Operation {operation!r} is forbidden while work_mode is 'PAUSED'.")

    if packet.get("formal_role") == "Reviewer" and operation in MUTATING_OPERATIONS:
        raise PolicyViolationError(
            f"formal_role='Reviewer' is read-only and cannot perform mutating operation {operation!r}."
        )

    if packet.get("schema_version") == 2 and actor_persona is not None and actor_persona != packet.get("assigned_persona"):
        raise PolicyViolationError("Contract actor override denied; no live delegation bridge.")
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



# Lane B: these are eligibility constraints, not an authentication provider.
# The native boundary must supply an independently resolved grant and observation.
FRONTEND_PERSONAS = frozenset({"Antigravity-Lucien", "Antigravity-Iris"})
CANONICAL_FRONTEND_REPO_ID = 1377058358
CANONICAL_FRONTEND_REPO = "Kirjane/Operation-FORGE.kirion"
LUCIEN_GITHUB_ID = "359299805"
SUSPENDED_LUCIEN_GITHUB_ID = "339001004"
FRONTEND_SUFFIXES = (".tsx", ".ts", ".jsx", ".js", ".mjs", ".css", ".scss",
                     ".sass", ".less", ".html", ".vue", ".svelte", ".razor",
                     ".cshtml", ".blade.php", ".svg", ".png", ".jpg", ".jpeg",
                     ".webp", ".avif", ".ico", ".woff", ".woff2", ".json", ".md",
                     ".kt", ".swift", ".xml", ".dart", ".xaml")
# Reject protected/operational segments even when nested inside a UI tree.
FRONTEND_DENIED_SEGMENTS = frozenset({
    "backend", "server", "controllers", "middleware", "migrations", "database",
    "secrets", "credentials", "security", "policies", "governance", "infra",
    "infrastructure", "deploy", "deployment", "scripts", "node_modules",
    "vendor", ".github", ".forge", ".agents", ".git", "dist", "build",
})
FRONTEND_DENIED_NAMES = frozenset({
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "composer.json", "composer.lock", "tsconfig.json", "vite.config.ts",
    "vite.config.js", "next.config.js", "next.config.ts", "firebase.json",
    "google-services.json", "googleservice-info.plist", "androidmanifest.xml",
    "agents.md", "dockerfile", "web.config", "appsettings.json",
})
# Approved structural conventions. New conventions require explicit policy review;
# a generic src/, app/, apps/ or repository-wide ownership is not a UI grant.
FRONTEND_ROOTS = (
    "frontend", "web", "client", "ui", "src/frontend", "src/client", "src/ui",
    "src/components", "src/pages", "src/features", "src/styles", "src/assets",
    "src/routes", "src/screens", "src/navigation", "src/hooks", "src/lib/ui",
    "resources/js", "resources/css", "resources/views", "public/assets",
    "views", "pages", "components", "wwwroot/css", "wwwroot/js", "wwwroot/images",
    "tests/frontend", "tests/e2e", "tests/browser", "e2e", "playwright",
)
ARCHITECTURE_ROOTS = ("docs/architecture", "docs/adr", "architecture", "adr",
                      "integrations/antigravity/adr", "integrations/antigravity/schemas")


def _frontend_root(norm: str) -> str | None:
    low = norm.lower()
    parts = low.split("/")
    if any(p.startswith(".") or p in FRONTEND_DENIED_SEGMENTS for p in parts):
        return None
    # Explicitly named frontend application under a monorepo, not arbitrary apps/.
    roots = list(FRONTEND_ROOTS)
    if len(parts) >= 3 and parts[0] == "apps" and (
        parts[1] in {"web", "frontend", "client", "mobile"} or
        parts[1].endswith(("-web", "-frontend", "-client", "-mobile"))
    ):
        roots.extend(f"apps/{parts[1]}/{p}" for p in ("src", "assets", "public", "tests", "e2e"))
    # Native presentation folders, not entire Android/iOS applications.
    if len(parts) >= 5 and parts[0] in {"android", "ios", "app", "apps"}:
        for i, part in enumerate(parts[:-1]):
            if i >= 2 and part in {"ui", "screens", "views", "presentation"}:
                roots.append("/".join(parts[:i + 1]))
    return next((root for root in sorted(roots, key=len, reverse=True)
                 if low.startswith(root + "/")), None)


def _explicit_owned_file(packet: dict[str, Any], norm: str, root: str) -> bool:
    # Require the actual ownership prefix to be within the frontend/architecture
    # root, rather than relying on an overbroad parent grant.
    return any(path_matches_prefix(prefix, root) and path_matches_prefix(norm, prefix)
               for prefix in packet.get("owned_paths", []))


def _frontend_path_allowed(packet: dict[str, Any], norm: str) -> bool:
    root = _frontend_root(norm)
    name = PurePosixPath(norm).name.lower()
    if root is None or name in FRONTEND_DENIED_NAMES:
        return False
    if name.startswith(("vite.config.", "next.config.", "webpack.config.", "rollup.config.",
                        "tsconfig.", "eslint.config.", "babel.config.", "metro.config.",
                        "playwright.config.", "appsettings.", "secret", "credential")):
        return False
    return norm.lower().endswith(FRONTEND_SUFFIXES) and _explicit_owned_file(packet, norm, root)


def assert_frontend_actor_binding(
    packet: dict[str, Any], *, trusted_grant: dict[str, Any] | None,
    observed_actor: dict[str, Any] | None,
) -> None:
    """Check a frontend writer's host-observed identity against a resolved grant.

    Inputs MUST originate outside packet ingress, in the trusted native boundary;
    this pure check does not establish that trust or validate grant freshness.
    No default, packet fallback, or caller-provided persona string is authority.
    """
    if type(packet.get("schema_version")) is not int or packet["schema_version"] != 2:
        raise PolicyViolationError("Frontend mutation requires protocol v2.")
    if packet.get("formal_role") != "Code Writer" or packet.get("assigned_persona") not in FRONTEND_PERSONAS:
        raise PolicyViolationError("Frontend mutation requires assigned Code Writer.")
    if not isinstance(trusted_grant, dict) or not isinstance(observed_actor, dict):
        raise PolicyViolationError("Trusted frontend actor binding unavailable.")
    # Import lazily to avoid the existing mission_contract -> policy import cycle.
    from .mission_contract import contract_digest
    expected = {"contract_sha256": contract_digest(packet), "revision": packet.get("revision"),
                "persona": packet["assigned_persona"], "formal_role": "Code Writer"}
    if any(type(trusted_grant.get(k)) is not type(v) or trusted_grant.get(k) != v
           for k, v in expected.items()):
        raise PolicyViolationError("Frontend actor grant contract binding mismatch.")
    keys = ("actor_id", "worker_id", "host_id", "identity_provider")
    for key in keys:
        val = trusted_grant.get(key)
        if not isinstance(val, str) or not val or val != val.strip() or observed_actor.get(key) != val:
            raise PolicyViolationError("Frontend actor observation mismatch.")
    if observed_actor.get("persona") != packet["assigned_persona"] or observed_actor.get("formal_role") != "Code Writer":
        raise PolicyViolationError("Frontend actor persona or role mismatch.")
    actor_id = trusted_grant["actor_id"]
    provider = trusted_grant["identity_provider"]
    if actor_id == SUSPENDED_LUCIEN_GITHUB_ID or actor_id == "github:" + SUSPENDED_LUCIEN_GITHUB_ID:
        raise PolicyViolationError("Suspended Lucien identity denied.")
    if provider == "github":
        if packet["assigned_persona"] != "Antigravity-Lucien" or actor_id != LUCIEN_GITHUB_ID:
            raise PolicyViolationError("No matching approved frontend GitHub identity.")
    elif provider == "native":
        if not actor_id.startswith("native:") or len(actor_id) <= len("native:"):
            raise PolicyViolationError("Native frontend identity must be host-namespaced.")
    else:
        raise PolicyViolationError("Unknown frontend identity provider.")


def _assert_frontend_write_path(
    packet: dict[str, Any], norm: str, *, trusted_grant: dict[str, Any] | None,
    observed_actor: dict[str, Any] | None,
) -> None:
    persona = packet.get("assigned_persona")
    low = norm.lower()
    standard = low == "standards/frontend" or low.startswith("standards/frontend/")
    if standard:
        if (persona != "Antigravity-Lucien" or packet.get("repo_id") != CANONICAL_FRONTEND_REPO_ID
                or packet.get("repo_name") != CANONICAL_FRONTEND_REPO
                or not low.endswith((".md", ".json"))
                or not _explicit_owned_file(packet, norm, "standards/frontend")):
            raise PolicyViolationError("Canonical frontend standard is reserved to authorized Lucien.")
        assert_frontend_actor_binding(packet, trusted_grant=trusted_grant, observed_actor=observed_actor)
        if trusted_grant.get("identity_provider") != "github" or trusted_grant.get("actor_id") != LUCIEN_GITHUB_ID:
            raise PolicyViolationError("Canonical standard authorship requires active Lucien GitHub identity.")
        return
    if persona not in FRONTEND_PERSONAS:
        return
    if packet.get("formal_role") != "Code Writer":
        raise PolicyViolationError("Frontend persona is read-only without Code Writer authority.")
    if type(packet.get("schema_version")) is int and packet["schema_version"] == 1:
        # Historical Lucien architecture receipts remain inspectable. Do not
        # expand v1 to new UI writes or use it as live dispatch authority.
        if persona == "Antigravity-Lucien" and low.endswith((".md", ".json")):
            return
        raise PolicyViolationError("Historical protocol cannot authorize new frontend mutation.")
    assert_frontend_actor_binding(packet, trusted_grant=trusted_grant, observed_actor=observed_actor)
    if _frontend_path_allowed(packet, norm):
        return
    if persona == "Antigravity-Lucien" and low.endswith((".md", ".schema.json")):
        if any(low.startswith(root + "/") and _explicit_owned_file(packet, norm, root)
               for root in ARCHITECTURE_ROOTS):
            return
    raise PolicyViolationError(f"Path {norm!r} is not within an explicit frontend or authorized architecture scope.")


def assert_paths_within_ownership(
    packet: dict[str, Any],
    changed_paths: list[str],
    *,
    allow_protected_governance: bool = False,
    require_write_operation: bool = True,
    trusted_grant: dict[str, Any] | None = None,
    observed_actor: dict[str, Any] | None = None,
) -> list[str]:
    """Verify every touched file is inside MissionPacket.owned_paths and respects persona path restrictions."""
    if packet.get("formal_role") == "Reviewer":
        raise PolicyViolationError(
            f"formal_role='Reviewer' ({packet.get('assigned_persona')!r}) is read-only and cannot mutate repository paths."
        )
    if require_write_operation or packet.get("assigned_persona") in FRONTEND_PERSONAS:
        assert_operation_allowed(packet, "WRITE_OWNED")
    owned_prefixes = packet.get("owned_paths", [])
    persona = packet.get("assigned_persona", "")
    validated: list[str] = []

    for raw in changed_paths:
        norm = normalize_rel_path(raw)
        if packet.get("schema_version") == 2 and (
            raw != norm or any(char in norm for char in '<>:"|')
            or any(segment.endswith((" ", ".")) for segment in norm.split("/"))
            or any(ord(char) < 32 or ord(char) == 127 for char in norm)
        ):
            raise PolicyViolationError(f"Noncanonical contract path denied: {raw!r}")
        norm_low = norm.lower()
        if (not allow_protected_governance or packet.get("schema_version") == 2) and is_protected_governance_path(norm):
            raise PolicyViolationError(f"Protected governance file {norm!r} cannot be modified by worker.")

        if packet.get("schema_version") == 2 and any(path_matches_prefix(norm, pref) for pref in packet["excluded_paths"]):
            raise PolicyViolationError(f"Excluded path mutation denied: {norm!r}")
        if not any(path_matches_prefix(norm, pref) for pref in owned_prefixes):
            raise PolicyViolationError(
                f"Out-of-scope file mutation denied: {norm!r} is not inside owned_paths {owned_prefixes}"
            )

        if persona == "Antigravity-Scribe" and not norm_low.endswith((".md", ".json", ".txt")):
            raise PolicyViolationError(f"Antigravity-Scribe is restricted to documentation/capsule files (.md/.json/.txt), denied: {norm!r}")

        _assert_frontend_write_path(packet, norm, trusted_grant=trusted_grant,
                                    observed_actor=observed_actor)

        if persona == "Antigravity-QA":
            if packet.get("formal_role") != "Code Writer":
                raise PolicyViolationError("Antigravity-QA requires explicit Code Writer role transition to write test files.")
            if not _is_qa_test_or_benchmark_path(norm):
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
