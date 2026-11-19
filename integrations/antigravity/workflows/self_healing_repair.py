# Native Antigravity run_workflow script: Bounded Self-Healing Repair Loop
phase("1-Failure-Classification")
mission_id = args.get("mission_id", "F-REPAIR")
failure_summary = args.get("failure_summary", "Gate G06 failed")
candidate_sha = args.get("candidate_sha", "a864b88bda5f26c44709c9239dc73ae63abc78ad")

classification = await agent(
    f"You are Antigravity-QA classifying failure '{failure_summary}' at {candidate_sha}. "
    "Classify into canonical failure taxonomy and specify the discriminating regression test required.",
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

phase("2-Root-Cause-Repair-And-ReReview")
nox_recheck = await agent(
    f"You are Antigravity-Nox re-reviewing repaired candidate for {mission_id} after {classification['failure_class']} fix. "
    "Verify no assertions were weakened.",
    schema={
        "type": "object",
        "properties": {
            "assertions_preserved": {"type": "boolean"},
            "verdict": {"type": "string"}
        },
        "required": ["assertions_preserved", "verdict"]
    },
    role="Antigravity-Nox (Post-Repair Review)",
    type_name="research"
)
print({"classification": classification, "nox_recheck": nox_recheck})
