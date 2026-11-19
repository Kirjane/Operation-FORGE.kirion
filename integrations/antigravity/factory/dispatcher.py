"""F01 & F02 — Native plugin packaging verifier, 10-persona Kirion Fleet registry, and progressive skill dispatcher."""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from . import PLUGIN_ROOT, REPO_ROOT
from .authority import AuthorityError, is_valid_git_sha, verify_mission_packet
from .policy import PERSONA_PERMISSIONS, PolicyViolationError

SKILL_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}\Z")

ALLOWED_PLUGIN_MANIFEST_KEYS = {
    "name",
    "description",
    "logo",
    "suggestedPrompts",
    "displayName",
    "version",
    "author",
    "homepage",
    "repository",
    "disabled",
}

EXPECTED_FLEET_AGENTS = {
    "antigravity-maintainer": "Antigravity-Maintainer",
    "antigravity-lucien": "Antigravity-Lucien",
    "antigravity-jane": "Antigravity-Jane",
    "antigravity-nox": "Antigravity-Nox",
    "antigravity-argon": "Antigravity-Argon",
    "antigravity-iris": "Antigravity-Iris",
    "antigravity-qa": "Antigravity-QA",
    "antigravity-aegis": "Antigravity-Aegis",
    "antigravity-integrator": "Antigravity-Integrator",
    "antigravity-scribe": "Antigravity-Scribe",
}

EXPECTED_PLUGIN_SPECIALIZATION_SKILLS = {
    "kirion-php",
    "kirion-laravel",
    "kirion-eloquent",
    "kirion-laravel-security",
    "kirion-laravel-runtime",
    "kirion-csharp",
    "kirion-aspnet",
    "kirion-efcore",
    "kirion-concurrency",
    "kirion-database",
    "kirion-api",
    "kirion-observability",
    "kirion-performance",
    "kirion-design-engineering",
    "kirion-test-engineering",
    "kirion-devsecops",
}

STACK_SKILL_BUNDLES: dict[str, list[str]] = {
    "csharp_aspnet": ["kirion-csharp", "kirion-aspnet", "kirion-efcore", "kirion-concurrency"],
    "php_laravel": ["kirion-php", "kirion-laravel", "kirion-eloquent", "kirion-laravel-security", "kirion-laravel-runtime"],
    "salryn_high_integrity": ["kirion-business-logic", "kirion-concurrency", "kirion-database", "kirion-runtime"],
    "frontend_web": ["kirion-frontend", "kirion-design-engineering", "kirion-test-engineering"],
    "review_nox": ["kirion-review", "kirion-security", "kirion-test-engineering"],
    "security_aegis": ["kirion-security", "kirion-devsecops"],
    "integration": ["kirion-integrator", "kirion-test-engineering"],
    "documentation": ["kirion-evidence", "kirion-cognition"],
}


def _resolve_plugin_root(repo_root: Path) -> Path:
    """Resolve the kirion-forge plugin root under repo_root when present, falling back to canonical PLUGIN_ROOT."""
    local_plugin = repo_root / "integrations" / "antigravity" / "plugins" / "kirion-forge"
    if local_plugin.is_dir():
        return local_plugin
    return PLUGIN_ROOT


def verify_plugin_package(plugin_dir: Path = PLUGIN_ROOT, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Deterministically validate the native kirion-forge plugin structure, schema, skills, agents, rules, and hooks."""
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.is_file():
        raise AuthorityError(f"Missing plugin.json at {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    unknown_keys = set(manifest.keys()) - ALLOWED_PLUGIN_MANIFEST_KEYS
    if unknown_keys:
        raise AuthorityError(f"Unknown top-level keys in plugin.json: {sorted(unknown_keys)}")
    if manifest.get("name") != "kirion-forge":
        raise AuthorityError(f"Expected plugin name 'kirion-forge', got {manifest.get('name')!r}")

    logo_rel = manifest.get("logo")
    if not logo_rel or not (plugin_dir / logo_rel).is_file():
        raise AuthorityError(f"Missing plugin logo asset: {logo_rel!r}")

    prompts = manifest.get("suggestedPrompts", [])
    if not isinstance(prompts, list) or not (1 <= len(prompts) <= 3):
        raise AuthorityError("suggestedPrompts must contain 1 to 3 non-empty prompts.")

    # Rules check: plain markdown, no YAML frontmatter, <= 24,000 bytes
    rules_path = plugin_dir / "rules" / "AGENTS.md"
    if not rules_path.is_file():
        raise AuthorityError("Missing rules/AGENTS.md in plugin.")
    rules_bytes = rules_path.read_bytes()
    if len(rules_bytes) > 24000:
        raise AuthorityError(f"rules/AGENTS.md exceeds 24,000 byte limit ({len(rules_bytes)} bytes).")
    if rules_bytes.decode("utf-8").lstrip().startswith("---"):
        raise AuthorityError("rules/AGENTS.md must be plain markdown without YAML frontmatter.")

    # Hooks check: must be at plugin root with enabled: true and active PreToolUse command hooks
    hooks_path = plugin_dir / "hooks.json"
    if not hooks_path.is_file():
        raise AuthorityError("Missing root hooks.json in plugin.")
    hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
    if not isinstance(hooks_data, dict) or "kirion-forge-safety-gate" not in hooks_data:
        raise AuthorityError("hooks.json missing 'kirion-forge-safety-gate'.")
    gate_cfg = hooks_data["kirion-forge-safety-gate"]
    if not isinstance(gate_cfg, dict) or gate_cfg.get("enabled") is not True:
        raise AuthorityError("hooks.json 'kirion-forge-safety-gate' must be an object with enabled: true.")
    pre_entries = gate_cfg.get("PreToolUse")
    if not isinstance(pre_entries, list) or not pre_entries:
        raise AuthorityError("hooks.json 'kirion-forge-safety-gate' must define non-empty PreToolUse hooks.")
    has_cmd_hook = any(
        isinstance(entry, dict)
        and isinstance(entry.get("hooks"), list)
        and any(
            isinstance(h, dict) and h.get("type") == "command" and isinstance(h.get("command"), str) and h["command"].strip()
            for h in entry["hooks"]
        )
        for entry in pre_entries
    )
    if not has_cmd_hook:
        raise AuthorityError("hooks.json 'kirion-forge-safety-gate' PreToolUse must declare at least one command hook.")
    guard_script = plugin_dir / "hooks" / "forge_guard.py"
    if not guard_script.is_file():
        raise AuthorityError("Missing hooks/forge_guard.py in plugin.")

    # 10 Fleet agents check
    agents_dir = plugin_dir / "agents"
    agent_files = sorted(agents_dir.glob("*.md"))
    observed_agents = {f.stem for f in agent_files}
    if observed_agents != set(EXPECTED_FLEET_AGENTS.keys()):
        raise AuthorityError(f"Fleet agent mismatch: expected {sorted(EXPECTED_FLEET_AGENTS)}, got {sorted(observed_agents)}")

    # 16 Specialization skills check + 16 core skills check = 32 total
    plugin_skills_dir = plugin_dir / "skills"
    plugin_skill_files = sorted(plugin_skills_dir.glob("*/SKILL.md"))
    observed_plugin_skills = {f.parent.name for f in plugin_skill_files}
    if observed_plugin_skills != EXPECTED_PLUGIN_SPECIALIZATION_SKILLS:
        raise AuthorityError(
            f"Plugin specialization skill mismatch: expected {sorted(EXPECTED_PLUGIN_SPECIALIZATION_SKILLS)}, "
            f"got {sorted(observed_plugin_skills)}"
        )

    for sf in plugin_skill_files:
        text = sf.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            raise AuthorityError(f"Skill {sf} missing YAML frontmatter.")
        for required_section in ("Versioned Official References", "Concrete Workflow", "Validation Commands", "Misuse & Negative Cases"):
            if required_section not in text:
                raise AuthorityError(f"Skill {sf.parent.name} missing required section {required_section!r}")

    core_skills_dir = repo_root / ".agents" / "skills"
    core_skills = {f.parent.name for f in core_skills_dir.glob("*/SKILL.md")}

    plugins_json_path = repo_root / ".agents" / "plugins.json"
    if not plugins_json_path.is_file():
        raise AuthorityError("Missing .agents/plugins.json workspace registration.")
    try:
        plugins_cfg = json.loads(plugins_json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AuthorityError(f"Invalid JSON in .agents/plugins.json: {exc}") from exc
    entries = plugins_cfg.get("entries") if isinstance(plugins_cfg, dict) else None
    if not isinstance(entries, list) or not entries:
        raise AuthorityError(".agents/plugins.json must define a non-empty 'entries' list.")
    expected_parent = plugin_dir.parent.resolve()
    entry_resolved = False
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"].strip():
            raise AuthorityError(f"Invalid entry in .agents/plugins.json: {entry!r}")
        raw_entry_path = Path(entry["path"])
        candidate_dir = raw_entry_path.resolve() if raw_entry_path.is_absolute() else (repo_root / raw_entry_path).resolve()
        if candidate_dir == expected_parent:
            entry_resolved = True
            break
    if not entry_resolved:
        raise AuthorityError(
            f".agents/plugins.json entries do not register plugin parent directory {expected_parent}"
        )

    # Compute deterministic package digest sorted by normalized POSIX relative path, excluding __pycache__ / *.pyc
    hasher = hashlib.sha256()
    files_to_hash = []
    for file_path in plugin_dir.rglob("*"):
        if not file_path.is_file():
            continue
        rel_parts = file_path.relative_to(plugin_dir).parts
        if "__pycache__" in rel_parts or file_path.suffix.lower() in (".pyc", ".pyo"):
            continue
        files_to_hash.append((file_path.relative_to(plugin_dir).as_posix(), file_path))
    for rel, file_path in sorted(files_to_hash, key=lambda pair: pair[0]):
        hasher.update(rel.encode("utf-8") + b"\x00" + file_path.read_bytes() + b"\x00")

    return {
        "name": manifest["name"],
        "version": manifest.get("version"),
        "plugin_dir": str(plugin_dir),
        "agents_count": len(observed_agents),
        "plugin_skills_count": len(observed_plugin_skills),
        "core_skills_count": len(core_skills),
        "total_candidate_skills": len(observed_plugin_skills) + len(core_skills),
        "rules_size_bytes": len(rules_bytes),
        "hooks_present": True,
        "package_sha256": hasher.hexdigest(),
    }


def query_live_host_plugin_discovery(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Query the live Antigravity Language Server GetAllPlugins RPC if active on host."""
    addr = os.environ.get("ANTIGRAVITY_LS_ADDRESS")
    csrf = os.environ.get("ANTIGRAVITY_CSRF_TOKEN")
    if not addr or not csrf:
        return {"status": "NOT_RUN", "reason": "ANTIGRAVITY_LS_ADDRESS or CSRF token not present in environment."}

    req = urllib.request.Request(
        f"http://{addr}/exa.language_server_pb.LanguageServerService/GetAllPlugins",
        data=json.dumps({"workspaceUris": [repo_root.as_uri()]}).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-codeium-csrf-token": csrf},
        method="POST",
    )
    raw = urllib.request.urlopen(req, timeout=10).read().decode("utf-8")
    data = json.loads(raw)
    matches = [p for p in data.get("plugins", []) if p.get("name") == "kirion-forge"]
    if not matches:
        raise AuthorityError("kirion-forge was not discovered by Language Server GetAllPlugins.")
    p = matches[0]
    return {
        "status": "OBSERVED",
        "name": p.get("name"),
        "isGlobal": p.get("isGlobal", False),
        "disabled": p.get("disabled", False),
        "skills_count": len(p.get("skills", [])),
        "agents_count": len(p.get("agents", [])),
        "rules_count": len(p.get("rules", [])),
        "hooks_loaded": bool(p.get("hooksJson")),
    }


def select_skills_for_mission(
    profile_key: str,
    *,
    skill_source_sha: str,
    extra_specialists: list[str] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Progressive disclosure skill selector: kirion-core + kirion-dispatch + bounded specialist pack (<= 8 files)."""
    if not is_valid_git_sha(skill_source_sha):
        raise AuthorityError(f"Invalid or all-zero skill_source_sha forbidden: {skill_source_sha!r}")
    if profile_key not in STACK_SKILL_BUNDLES:
        raise AuthorityError(
            f"Unknown skill profile_key {profile_key!r}; expected one of {sorted(STACK_SKILL_BUNDLES.keys())}."
        )
    selected_names = ["kirion-core", "kirion-dispatch"]
    for name in STACK_SKILL_BUNDLES[profile_key]:
        if name not in selected_names:
            selected_names.append(name)
    for name in extra_specialists or []:
        if not isinstance(name, str) or not SKILL_SLUG_RE.fullmatch(name):
            raise AuthorityError(f"Invalid extra specialist skill slug: {name!r}")
        if name not in selected_names:
            selected_names.append(name)
    if len(selected_names) > 8:
        selected_names = selected_names[:8]

    plugin_root = _resolve_plugin_root(repo_root)
    resolved_paths: list[str] = []
    for name in selected_names:
        core_path = repo_root / ".agents" / "skills" / name / "SKILL.md"
        if not core_path.is_file():
            core_path = REPO_ROOT / ".agents" / "skills" / name / "SKILL.md"
        plugin_path = plugin_root / "skills" / name / "SKILL.md"
        if not plugin_path.is_file():
            plugin_path = PLUGIN_ROOT / "skills" / name / "SKILL.md"
        if core_path.is_file():
            resolved_paths.append(f".agents/skills/{name}/SKILL.md")
        elif plugin_path.is_file():
            resolved_paths.append(f"integrations/antigravity/plugins/kirion-forge/skills/{name}/SKILL.md")
        else:
            raise AuthorityError(f"Unknown skill requested in progressive selector: {name!r}")

    return {
        "skill_source_sha": skill_source_sha,
        "files": resolved_paths,
    }


class FleetDispatcher:
    """Dispatches bounded missions to isolated Kirion Fleet persona contexts."""

    def __init__(self, repo_root: Path = REPO_ROOT) -> None:
        self.repo_root = repo_root
        self._dispatch_history: list[dict[str, Any]] = []

    def create_isolated_context(self, persona: str, formal_role: str) -> dict[str, str]:
        if persona not in PERSONA_PERMISSIONS:
            raise PolicyViolationError(f"Cannot dispatch unknown or spoofed persona: {persona!r}")
        if formal_role not in PERSONA_PERMISSIONS[persona]["formal_roles"]:
            raise PolicyViolationError(f"Persona {persona!r} is not permitted to assume formal role {formal_role!r}")

        agent_slug = next(k for k, v in EXPECTED_FLEET_AGENTS.items() if v == persona)
        plugin_root = _resolve_plugin_root(self.repo_root)
        agent_file = plugin_root / "agents" / f"{agent_slug}.md"
        if not agent_file.is_file():
            agent_file = PLUGIN_ROOT / "agents" / f"{agent_slug}.md"
        if not agent_file.is_file():
            raise AuthorityError(f"Missing agent contract file: {agent_file}")

        try:
            contract_rel = agent_file.resolve().relative_to(self.repo_root.resolve()).as_posix()
        except ValueError:
            contract_rel = f"integrations/antigravity/plugins/kirion-forge/agents/{agent_slug}.md"

        context_id = f"ctx-{agent_slug}-{uuid.uuid4().hex[:12]}"
        return {
            "context_id": context_id,
            "persona": persona,
            "formal_role": formal_role,
            "agent_slug": agent_slug,
            "native_type_name": "research" if formal_role == "Reviewer" else "self",
            "agent_contract_path": contract_rel,
        }

    def dispatch_worker(
        self,
        packet: dict[str, Any],
        handler: Any,
        *,
        worktree_path: Path | None = None,
    ) -> dict[str, Any]:
        verify_mission_packet(packet)
        persona = packet["assigned_persona"]
        formal_role = packet["formal_role"]
        ctx = self.create_isolated_context(persona, formal_role)
        isolated_input = json.loads(json.dumps(packet))
        result = handler(isolated_input, ctx, worktree_path or self.repo_root)
        record = {
            "mission_id": packet["mission_id"],
            "run_id": packet["run_id"],
            "context_id": ctx["context_id"],
            "persona": persona,
            "formal_role": formal_role,
            "native_type_name": ctx["native_type_name"],
        }
        self._dispatch_history.append(record)
        return {"context": ctx, "result": result}

    @property
    def dispatch_history(self) -> list[dict[str, Any]]:
        return list(self._dispatch_history)
