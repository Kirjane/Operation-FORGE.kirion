# Native Antigravity run_workflow script: Fresh-Context Antigravity-Nox & Antigravity-Aegis Adversarial Audit
phase("Adversarial-Frozen-SHA-Audit")
frozen_sha = args.get("frozen_sha", "a864b88bda5f26c44709c9239dc73ae63abc78ad")
mission_id = args.get("mission_id", "FORGE-ANTIGRAVITY-SOFTWARE-FACTORY-R1")
scope = args.get("inspected_scope", ["integrations/antigravity/"])

nox_audit = await agent(
    f"You are Antigravity-Nox performing a fresh-context adversarial review at frozen SHA {frozen_sha} "
    f"for mission {mission_id} covering {scope}. Inspect the actual files in the repository, verify schema/test/policy "
    "completeness, and return a JSON object matching nox-result.schema.json.",
    schema={
        "type": "object",
        "properties": {
            "mission_id": {"type": "string"},
            "frozen_sha": {"type": "string"},
            "reviewer_persona": {"type": "string"},
            "inspected_scope": {"type": "array", "items": {"type": "string"}},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "severity": {"type": "string"},
                        "path": {"type": "string"},
                        "line": {"type": "integer"},
                        "contract_violated": {"type": "string"},
                        "reproduction": {"type": "string"},
                        "requested_correction": {"type": "string"},
                        "disposition": {"type": "string"}
                    },
                    "required": ["id", "severity", "path", "line", "contract_violated", "reproduction", "requested_correction", "disposition"]
                }
            },
            "verdict": {"type": "string", "enum": ["PASS", "REWORK", "QUARANTINED"]}
        },
        "required": ["mission_id", "frozen_sha", "reviewer_persona", "inspected_scope", "findings", "verdict"]
    },
    role=f"Antigravity-Nox @ {frozen_sha[:12]}",
    type_name="research"
)
log("Antigravity-Nox Verdict:", nox_audit["verdict"])
print(nox_audit)
