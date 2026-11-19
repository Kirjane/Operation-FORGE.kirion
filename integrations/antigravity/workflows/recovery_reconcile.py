# Native Antigravity run_workflow script: Crash Recovery & Sandbox Capsule Reconstruction
import json
from pathlib import Path

phase("Recovery-Capsule-Reconciliation")
mission_id = args.get("mission_id", "F13")
interruption_point = args.get("interruption_point", "PRE_BROKER_RECEIPT")
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
