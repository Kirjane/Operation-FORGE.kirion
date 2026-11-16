---
id: "forge.skill.kirion-qa"
source_repo: "Kirch-Nairu/Operation-FORGE.kirion"
source_ref: "eabbfbabdbb22d8684fb2c3d80767b8547852b83"
source_path: ".agents/skills/kirion-qa/SKILL.md"
source_status: "CANDIDATE"
source_blob_sha: "37ce76213345b1cbb396539441261699825d1dba"
tags: [forge, arsenal, candidate]
---

# Kirion QA

**CANDIDATE / OPT_IN_ONLY.** Full canonical skill text at pinned PR #7 SHA. Reading this is not authority or automatic host installation.

[Exact SKILL.md](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/blob/eabbfbabdbb22d8684fb2c3d80767b8547852b83/.agents/skills/kirion-qa/SKILL.md) · [[00 Skill Index]] · [[Specialist Selection]] · [[00 HOME]]

## Canonical contract

# Fit-for-purpose QA
Pin SHA, feature contract, test environment and primary user journeys. Run the relevant unit, API/integration, disposable DB, real browser/host, responsive/accessibility, print/document and recovery checks. Test denied, duplicate, retry, empty, concurrent and rollback paths for affected invariants.
For UI with **real authentication**, use authenticated role-based Playwright to exercise permitted and denied paths. For an **authorized static frontend showcase without authentication**, use a real browser to exercise navigation, clearly simulated role switches and representative client-side interactions; do not invent login infrastructure or backend rules just for the demo. In either case check meaningful viewports, screenshots, keyboard/focus, empty/error states and browser errors. For actual PDF/receipt output inspect rendered bytes, pagination and totals; for mock document previews inspect the rendered SAMPLE / INVALID presentation rather than asserting production issuance.
Classify failures before changing code: stale expectation, app defect, integration mismatch, runner/environment, source/authority drift, missing evidence. Preserve exact commands, exits, artifact IDs and NOT_RUN. Re-run changed-dependent tests rather than entire unrelated historical suites.
