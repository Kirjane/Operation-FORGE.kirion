---
name: kirion-qa
description: Produce risk-scaled source/API/database/browser/installed-host/print verification and exact-SHA evidence that cannot confuse a test with real runtime behavior.
---

# Fit-for-purpose QA
Pin SHA, feature contract, test environment and primary user journeys. Run the relevant unit, API/integration, disposable DB, real browser/host, responsive/accessibility, print/document and recovery checks. Test denied, duplicate, retry, empty, concurrent and rollback paths for affected invariants.
For UI with **real authentication**, use authenticated role-based Playwright to exercise permitted and denied paths. For an **authorized static frontend showcase without authentication**, use a real browser to exercise navigation, clearly simulated role switches and representative client-side interactions; do not invent login infrastructure or backend rules just for the demo. In either case check meaningful viewports, screenshots, keyboard/focus, empty/error states and browser errors. For actual PDF/receipt output inspect rendered bytes, pagination and totals; for mock document previews inspect the rendered SAMPLE / INVALID presentation rather than asserting production issuance.
Classify failures before changing code: stale expectation, app defect, integration mismatch, runner/environment, source/authority drift, missing evidence. Preserve exact commands, exits, artifact IDs and NOT_RUN. Re-run changed-dependent tests rather than entire unrelated historical suites.
