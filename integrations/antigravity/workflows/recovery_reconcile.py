# Native Antigravity run_workflow script: Crash Recovery & Sandbox Capsule Reconstruction
phase("Recovery-Capsule-Reconciliation")
mission_id = args.get("mission_id", "F13")
interruption_point = args.get("interruption_point", "PRE_BROKER_RECEIPT")

res = await agent(
    f"You are Antigravity-Scribe reconciling interrupted mission {mission_id} at {interruption_point}. "
    "Verify idempotent delivery key and determine safe next allowed action.",
    schema={
        "type": "object",
        "properties": {
            "mission_id": {"type": "string"},
            "interruption_point": {"type": "string"},
            "duplicate_remote_effect_prevented": {"type": "boolean"},
            "next_allowed_action": {"type": "string"}
        },
        "required": ["mission_id", "interruption_point", "duplicate_remote_effect_prevented", "next_allowed_action"]
    },
    role="Antigravity-Scribe (Recovery)",
    type_name="research"
)
print(res)
