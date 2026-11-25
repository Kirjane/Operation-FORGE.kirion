# Native Antigravity run_workflow script: Bounded Self-Healing Repair Loop
# No trusted native preflight bridge is shipped. Do not use args, flags or role labels
# to infer authority. Preserve intended workflow for later explicit bridge qualification.
native_preflight = {"status": "BLOCKED", "reason": "TRUSTED_NATIVE_PREFLIGHT_BRIDGE_UNAVAILABLE"}
if native_preflight["status"] != "AUTHORIZED":
    print(native_preflight)
else:
    import json
    from pathlib import Path

    phase("1-Failure-Classification")
    mission_id = args["mission_id"]
    run_id = args["run_id"]
    failure_summary = args["failure_summary"]
    candidate_sha = args["candidate_sha"]
    owned_paths = args["owned_paths"]

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

    non_repairable_classes = {"requirements", "drift", "resource"}
    failure_class = str(classification.get("failure_class", "")).strip().lower()

    if failure_class in non_repairable_classes:
        print({
            "status": "BLOCKED",
            "reason": f"Non-repairable stop condition ({failure_class}); halting before writer mutation.",
            "classification": classification,
            "writer": None,
            "nox_recheck": None,
        })
    else:
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

        if writer_res.get("status") != "READY":
            print({
                "status": "BLOCKED",
                "reason": f"Writer repair halted with status={writer_res.get('status')!r}; skipping Nox post-repair review.",
                "classification": classification,
                "writer": writer_res,
                "nox_recheck": None,
            })
        else:
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
