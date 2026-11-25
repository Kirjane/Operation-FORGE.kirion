# Native Antigravity run_workflow script: Crash Recovery & Sandbox Capsule Reconstruction
# No trusted native preflight bridge is shipped. Do not use args, flags or role labels
# to infer authority. Preserve intended workflow for later explicit bridge qualification.
native_preflight = {"status": "BLOCKED", "reason": "TRUSTED_NATIVE_PREFLIGHT_BRIDGE_UNAVAILABLE"}
if native_preflight["status"] != "AUTHORIZED":
    print(native_preflight)
else:
    import json
    from pathlib import Path

    phase("Recovery-Capsule-Reconciliation")
    mission_id = args["mission_id"]
    interruption_point = args["interruption_point"]
    recovery_schema = json.loads(
        Path("integrations/antigravity/schemas/recovery-capsule.schema.json").resolve().read_text(encoding="utf-8")
    )

    res = await agent(
        f"You are Antigravity-Scribe reconciling interrupted mission {mission_id} at {interruption_point}. "
        "Verify journal hash chain, idempotent delivery key, and remote branch head read-only before determining safe next_allowed_action. "
        "Return a JSON object strictly matching recovery-capsule.schema.json.",
        schema=recovery_schema,
        role="Antigravity-Scribe (Recovery)",
        type_name="research"
    )
    print(res)
