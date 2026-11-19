# Native Antigravity run_workflow script: Bounded Self-Healing Repair Loop
import json
from pathlib import Path

phase("1-Failure-Classification")
mission_id = args.get("mission_id", "F-REPAIR")
run_id = args.get("run_id", f"run-{mission_id.lower()}")
failure_summary = args.get("failure_summary", "Gate G06 failed")
candidate_sha = args.get("candidate_sha", "a864b88bda5f26c44709c9239dc73ae63abc78ad")
owned_paths = args.get("owned_paths", ["integrations/antigravity/"])

writer_schema = json.loads(Path("integrations/antigravity/schemas/writer-result.schema.json").resolve().read_text(encoding="utf-8"))
nox_schema = json.loads(Path("integrations/antigravity/schemas/nox-result.schema.json").resolve().read_text(encoding="utf-8"))

classification = await agent(
    f"You are Antigravity-QA classifying failure '{failure_summary}' at {candidate_sha}. "
    "Classify into the canonical 10-class failure taxonomy and specify the discriminating pre-fix regression test required.",
    schema={
        "type": "object",
        "properties": {
            "failure_class": {"type": "string"},
            "discriminating_regression_test": {"type": "string"}
        },
        "required": ["failure_class", "discriminating_regression_test"]
    },
    role="Antigravity-QA (Classify)",
    type_name="research"
)

phase("2-Root-Cause-Writer-Repair")
writer_res = await agent(
    f"You are Antigravity-Jane executing bounded self-healing repair for mission {mission_id} (run_id={run_id}) "
    f"from start_sha={candidate_sha} on owned_paths={owned_paths}. Failure class: {classification['failure_class']}. "
    f"Required discriminating regression test: {classification['discriminating_regression_test']}. "
    "Fix the root cause without weakening assertions, commit in your isolated workspace, and return a JSON object strictly matching writer-result.schema.json.",
    schema=writer_schema,
    role=f"Antigravity-Jane (Repair {mission_id})",
    type_name="self",
    workspace="share"
)

phase("3-Fresh-Context-Nox-Post-Repair-Review")
repaired_sha = writer_res["final_sha"]
author_context_id = writer_res["worker_id"]
nox_recheck = await agent(
    f"You are Antigravity-Nox performing a fresh-context read-only review of repaired mission {mission_id} "
    f"at frozen_sha={repaired_sha} (author_context_id={author_context_id}, diff {candidate_sha}..{repaired_sha}). "
    "Verify root-cause fix, discriminating regression test, and zero assertion weakening; return a JSON object strictly matching nox-result.schema.json.",
    schema=nox_schema,
    role=f"Antigravity-Nox (Post-Repair @ {repaired_sha[:12]})",
    type_name="research"
)
print({"classification": classification, "writer": writer_res, "nox_recheck": nox_recheck})
