# Native Antigravity run_workflow script: Fresh-Context Antigravity-Nox & Antigravity-Aegis Adversarial Audit
# No trusted native preflight bridge is shipped. Do not use args, flags or role labels
# to infer authority. Preserve intended workflow for later explicit bridge qualification.
native_preflight = {"status": "BLOCKED", "reason": "TRUSTED_NATIVE_PREFLIGHT_BRIDGE_UNAVAILABLE"}
if native_preflight["status"] != "AUTHORIZED":
    print(native_preflight)
else:
    import json
    from pathlib import Path

    phase("Adversarial-Frozen-SHA-Audit")
    frozen_sha = args["frozen_sha"]
    mission_id = args["mission_id"]
    author_context_id = args["author_context_id"]
    scope = args["inspected_scope"]
    evidence_refs = args["evidence_inspected"]

    nox_schema_path = Path("integrations/antigravity/schemas/nox-result.schema.json").resolve()
    nox_schema = json.loads(nox_schema_path.read_text(encoding="utf-8"))

    nox_audit = await agent(
        f"You are Antigravity-Nox performing a fresh-context adversarial review at frozen SHA {frozen_sha} "
        f"for mission {mission_id} covering {scope}. "
        f"The author_context_id is '{author_context_id}'; set reviewer_context_id to a distinct non-empty identifier for your fresh review session. "
        f"Set schema_version=1, reviewer_persona='Antigravity-Nox', evidence_inspected={evidence_refs} (plus any files/commands you inspect). "
        "Inspect the actual files in the repository, verify schema/test/policy/security completeness, and return a JSON object strictly matching nox-result.schema.json.",
        schema=nox_schema,
        role=f"Antigravity-Nox @ {frozen_sha[:12]}",
        type_name="research"
    )
    log("Antigravity-Nox Verdict:", nox_audit["verdict"])
    print(nox_audit)
