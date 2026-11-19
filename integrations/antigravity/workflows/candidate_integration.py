# Native Antigravity run_workflow script: Multi-Candidate Integration Wave
phase("Integration-Ancestry-And-Collision-Audit")
candidates = args.get("candidates", [])
integration_branch = args.get("integration_branch", "feat/antigravity-software-factory-r1")

res = await agent(
    f"You are Antigravity-Integrator combining candidates {candidates} onto {integration_branch}. "
    "Check commit ancestry, shared routes/migrations/lockfiles, and report integration readiness.",
    schema={
        "type": "object",
        "properties": {
            "persona": {"type": "string"},
            "integration_branch": {"type": "string"},
            "semantic_collisions_detected": {"type": "boolean"},
            "status": {"type": "string"}
        },
        "required": ["persona", "integration_branch", "semantic_collisions_detected", "status"]
    },
    role="Antigravity-Integrator",
    type_name="research"
)
print(res)
