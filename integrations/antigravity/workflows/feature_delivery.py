# Native Antigravity run_workflow script: Bounded Feature Implementation, QA, and Fresh-Context Nox Review
phase("1-Feature-Implementation")
mission_id = args.get("mission_id", "F-FEATURE")
base_sha = args.get("base_sha", "a864b88bda5f26c44709c9239dc73ae63abc78ad")
owned_paths = args.get("owned_paths", ["integrations/antigravity/"])

writer_res = await agent(
    f"You are Antigravity-Jane executing bounded mission {mission_id} from base SHA {base_sha} on owned_paths={owned_paths}. "
    "Verify writer preflight and summarize your bounded implementation candidate.",
    schema={
        "type": "object",
        "properties": {
            "mission_id": {"type": "string"},
            "persona": {"type": "string"},
            "status": {"type": "string"},
            "authority_returned": {"type": "boolean"}
        },
        "required": ["mission_id", "persona", "status", "authority_returned"]
    },
    role=f"Antigravity-Jane ({mission_id})",
    type_name="research"
)

phase("2-Fresh-Context-Nox-Review")
nox_res = await agent(
    f"You are Antigravity-Nox in a fresh read-only context reviewing mission {mission_id} at frozen SHA {base_sha}. "
    "Evaluate scope compliance and return a structured Nox verdict.",
    schema={
        "type": "object",
        "properties": {
            "frozen_sha": {"type": "string"},
            "reviewer_persona": {"type": "string"},
            "verdict": {"type": "string"}
        },
        "required": ["frozen_sha", "reviewer_persona", "verdict"]
    },
    role=f"Antigravity-Nox ({mission_id})",
    type_name="research"
)
print({"writer": writer_res, "nox": nox_res})
