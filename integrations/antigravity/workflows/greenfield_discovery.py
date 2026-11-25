# Native Antigravity run_workflow script: Greenfield Discovery & Architecture Decomposition
# No trusted native preflight bridge is shipped. Do not use args, flags or role labels
# to infer authority. Preserve intended workflow for later explicit bridge qualification.
native_preflight = {"status": "BLOCKED", "reason": "TRUSTED_NATIVE_PREFLIGHT_BRIDGE_UNAVAILABLE"}
if native_preflight["status"] != "AUTHORIZED":
    print(native_preflight)
else:
    phase("1-Intake-And-Authority")
    repo = args["repo_name"]
    base_sha = args["base_sha"]
    objective = args["objective"]
    log(f"Starting greenfield discovery for {repo} @ {base_sha}")

    intake = await agent(
        f"You are Antigravity-Maintainer. Classify origin=GREENFIELD, work_mode=DISCOVERY for {repo} @ {base_sha}. "
        f"Objective: {objective}. Return a bounded mission decomposition plan with risk_class and required_gates.",
        schema={
            "type": "object",
            "properties": {
                "project_origin": {"type": "string"},
                "work_mode": {"type": "string"},
                "risk_class": {"type": "string"},
                "sub_missions": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["project_origin", "work_mode", "risk_class", "sub_missions"]
        },
        role="Antigravity-Maintainer (Intake)",
        type_name="research"
    )
    log("Intake decomposition:", intake)

    phase("2-Architecture-And-Threat-Model")
    arch_and_sec = await parallel(
        ["Antigravity-Lucien", "Antigravity-Aegis"],
        lambda persona: agent(
            f"You are {persona}. For objective '{objective}' on {repo} @ {base_sha}, define key contracts and boundaries.",
            schema={
                "type": "object",
                "properties": {
                    "persona": {"type": "string"},
                    "invariants": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["persona", "invariants"]
            },
            role=f"{persona} (Discovery)",
            type_name="research"
        )
    )
    print({"intake": intake, "architecture_and_security": arch_and_sec})
