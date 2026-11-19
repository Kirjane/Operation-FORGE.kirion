# Native Antigravity run_workflow script: Bounded Feature Implementation, QA, and Fresh-Context Nox Review
import json
from pathlib import Path

phase("1-Feature-Implementation")
mission_id = args.get("mission_id", "F-FEATURE")
run_id = args.get("run_id", f"run-{mission_id.lower()}")
base_sha = args.get("base_sha", "a864b88bda5f26c44709c9239dc73ae63abc78ad")
owned_paths = args.get("owned_paths", ["integrations/antigravity/"])

writer_schema = json.loads(Path("integrations/antigravity/schemas/writer-result.schema.json").resolve().read_text(encoding="utf-8"))
nox_schema = json.loads(Path("integrations/antigravity/schemas/nox-result.schema.json").resolve().read_text(encoding="utf-8"))

writer_res = await agent(
    f"You are Antigravity-Jane executing bounded mission {mission_id} (run_id={run_id}) from start_sha={base_sha} on owned_paths={owned_paths}. "
    "Verify writer preflight, implement within owned_paths in your isolated workspace, commit your change, and return a JSON object strictly matching writer-result.schema.json.",
    schema=writer_schema,
    role=f"Antigravity-Jane ({mission_id})",
    type_name="self",
    workspace="share"
)

if writer_res.get("status") != "READY":
    print({
        "status": "BLOCKED",
        "reason": f"Writer halted with status={writer_res.get('status')!r}; skipping Phase 2 Nox review.",
        "writer": writer_res,
        "nox": None,
    })
else:
    phase("2-Fresh-Context-Nox-Review")
    candidate_sha = writer_res["final_sha"]
    author_context_id = writer_res["worker_id"]
    nox_res = await agent(
        f"You are Antigravity-Nox in a fresh read-only context reviewing mission {mission_id} at frozen_sha={candidate_sha} "
        f"(diff {base_sha}..{candidate_sha}, author_context_id={author_context_id}). "
        "Evaluate scope compliance, defects, and evidence; return a JSON object strictly matching nox-result.schema.json.",
        schema=nox_schema,
        role=f"Antigravity-Nox ({mission_id} @ {candidate_sha[:12]})",
        type_name="research"
    )
    print({"writer": writer_res, "nox": nox_res})
