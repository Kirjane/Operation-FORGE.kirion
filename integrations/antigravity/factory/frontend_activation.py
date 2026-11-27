"""Translate Lucien's pinned declaration to the existing generic loader.
No frontend policy or native identity is created here.
"""
from .skill_registry import require, parse_json, unique_strings, MAX_REFERENCE_FILES
from .policy import FRONTEND_PERSONAS

DECLARATION = "standards/frontend/activation.json"
PROFILE = "integrations/antigravity/profiles/frontend_web.json"


def frontend_selection(registry, packet, cfg, required_skills):
    pins = registry.frontend_activation()
    require(type(pins) is dict and set(pins) == {"declaration", "profile"},
            "FRONTEND_DECLARATION_UNAVAILABLE")
    declaration, profile = pins["declaration"], pins["profile"]
    require(declaration["path"] == DECLARATION and profile["path"] == PROFILE and
            all(declaration[k] == profile[k] for k in ("repository_id", "repository_name", "commit_sha")),
            "FRONTEND_DECLARATION_PIN_MISMATCH")
    authorities = [a for a in packet["source_authorities"] if a["authority_kind"] in {"CONSTRAINT", "FUNCTIONAL"}]
    raw, declaration_identity = registry.read_declared_source(declaration, authorities)
    profile_raw, profile_identity = registry.read_declared_source(profile, authorities)
    decl, prof = parse_json(raw), parse_json(profile_raw)
    require(decl["schema_version"] == 1 and decl["profile_id"] == prof["profile_id"] == "frontend_web"
            and decl["source_revision"] == "mission_pinned"
            and decl["source_repository"] == {"id": declaration["repository_id"],
                                               "name": declaration["repository_name"]}
            and set(decl["personas"]) == set(prof["eligible_frontend_personas"]) == FRONTEND_PERSONAS
            and packet["assigned_persona"] in FRONTEND_PERSONAS
            and prof["required_skills"] == required_skills
            and prof["frontend_standard"]["required"] is True
            and prof["frontend_standard"]["declaration_path"] == DECLARATION
            and prof["frontend_standard"]["entrypoint"] == decl["entrypoint"],
            "FRONTEND_PROFILE_DECLARATION_MISMATCH")
    require(decl["rules"]["explicit_selected_domains_required"] is True and
            decl["rules"]["unknown_domain"] == "DENY" and decl["rules"]["required_missing"] == "DENY"
            and decl["rules"]["deduplicate"] == "first_occurrence", "FRONTEND_DECLARATION_RULE_MISMATCH")
    order, domains, mandatory = decl["selection_order"], decl["domains"], decl["required_domains"]
    chosen, optional = cfg.get("frontend_domains"), cfg.get("optional_frontend_domains", [])
    require(unique_strings(order) and type(domains) is dict and set(order) == set(domains)
            and unique_strings(mandatory) and "evidence" in mandatory and set(mandatory) <= set(domains)
            and unique_strings(chosen) and bool(chosen) and unique_strings(optional)
            and not set(chosen).intersection(optional) and not set(mandatory).intersection(optional)
            and set(chosen + optional) <= set(domains), "FRONTEND_EXPLICIT_DOMAINS_REQUIRED")
    required, discretionary = [decl["entrypoint"]], []
    for name in order:
        paths = domains[name]
        require(unique_strings(paths) and bool(paths) and all(p.startswith("standards/frontend/") for p in paths),
                "FRONTEND_DOMAIN_INVALID")
        if name in set(chosen + mandatory):
            required.extend(paths)
        elif name in optional:
            discretionary.extend(paths)
    required = list(dict.fromkeys(required))
    discretionary = [p for p in dict.fromkeys(discretionary) if p not in required]
    require(len(required) + len(discretionary) <= MAX_REFERENCE_FILES, "FRONTEND_REFERENCE_CEILING")
    ids = [registry.reference_for(declaration, path) for path in required]
    optional_ids = [registry.reference_for(declaration, path) for path in discretionary]
    return ids, optional_ids, {"declaration": declaration_identity, "profile": profile_identity,
                               "domains": [n for n in order if n in set(chosen + mandatory)],
                               "optional_domains": [n for n in order if n in optional],
                               "required_paths": required, "optional_paths": discretionary,
                               "metadata_bytes": len(raw) + len(profile_raw)}
