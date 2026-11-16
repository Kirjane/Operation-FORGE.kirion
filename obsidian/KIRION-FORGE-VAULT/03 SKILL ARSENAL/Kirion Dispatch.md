---
id: "forge.skill.kirion-dispatch"
source_repo: "Kirch-Nairu/Operation-FORGE.kirion"
source_ref: "eabbfbabdbb22d8684fb2c3d80767b8547852b83"
source_path: ".agents/skills/kirion-dispatch/SKILL.md"
source_status: "CANDIDATE"
source_blob_sha: "ab65104357eaa9d07218aac07e2d22c97129e8a7"
tags: [forge, arsenal, candidate]
---

# Kirion Dispatch

**CANDIDATE / OPT_IN_ONLY.** Full canonical skill text at pinned PR #7 SHA. Reading this is not authority or automatic host installation.

[Exact SKILL.md](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/blob/eabbfbabdbb22d8684fb2c3d80767b8547852b83/.agents/skills/kirion-dispatch/SKILL.md) · [[00 Skill Index]] · [[Specialist Selection]] · [[00 HOME]]

## Canonical contract

# Skill dispatcher
Start with kirion-core. Use kirion-session-host when the task executes in a ChatGPT GitHub-connected worker conversation. Load at most 1–3 work specialists unless separate active risks require more:
- kirion-cognition: source and decision reconstruction, stale memory and conflicting authority.
- kirion-worker: implementing quality code; kirion-architecture: new design/interface boundaries; kirion-debug: root cause.
- kirion-business-logic: money, stock, procurement, account settlement, documents and workflow invariants.
- kirion-security: auth/privacy/retained state/irrevocable actions.
- kirion-qa: actual tests, browser, database and print QA; kirion-review: independent frozen-SHA judgment.
- kirion-frontend: UI/navigation/accessibility; kirion-integrator: collision/ancestry/integration.
- kirion-runtime: installation, offline, server and recovery; kirion-evidence: precise reports.
Create a temporary task skill with kirion-skill-smith only if the work has a narrow unusual multistep protocol, existing skills do not cover it, it demonstrably saves coordination, and authorized temporary storage exists. Don't create an extra approval layer for skill selection or confuse skill loading with task completion.
