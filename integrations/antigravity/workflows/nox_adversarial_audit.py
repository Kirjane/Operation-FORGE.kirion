# Native Antigravity run_workflow script: Fresh-Context Antigravity-Nox & Antigravity-Aegis Adversarial Audit
import json
from pathlib import Path

phase("Adversarial-Frozen-SHA-Audit")
frozen_sha = args.get("frozen_sha", "a864b88bda5f26c44709c9239dc73ae63abc78ad")
mission_id = args.get("mission_id", "FORGE-ANTIGRAVITY-SOFTWARE-FACTORY-R1")
author_context_id = args.get("author_context_id", "ctx-antigravity-maintainer-parent")
scope = args.get("inspected_scope", ["integrations/antigravity/"])
evidence_refs = args.get("evidence_inspected", ["tools/entity_check.py", "integrations/antigravity/tests"])

nox_schema_path = Path("integrations/antigravity/schemas/nox-result.schema.json").resolve()
nox_schema = json.loads(nox_schema_path.read_text(encoding="utf-8"))

nox_audit = await agent(
    f"You are Antigravity-Nox performing a fresh-context adversarial review at frozen SHA {frozen_sha} "
    f"for mission {mission_id} covering {scope}. "
    f"The author_context_id is '{author_context_id}'; set reviewer_context_id to a distinct non-empty identifier for your fresh review session. "
    f"Set schema_version=1, reviewer_persona='Antigravity-Nox', evidence_inspected={evidence_refs} (plus any files/commands you inspect). "
    "Inspect the actual files in the repository, verify schema/test/policy/security completeness, and return a JSON object strictly matching nox-result.schema.json.",
    schema=nox_schema,
    role=f"Antigravity-Nox @ {frozen_sha[:12]}",
    type_name="research"
)
log("Antigravity-Nox Verdict:", nox_audit["verdict"])
print(nox_audit)
