---
name: kirion-qa
description: Produce risk-scaled source/API/database/browser/installed-host/print verification and exact-SHA evidence that cannot confuse a test with real runtime behavior.
---

# Fit-for-purpose QA
Pin SHA, feature contract, test environment and primary user journeys. Run the relevant unit, API/integration, disposable DB, real browser/host, responsive/accessibility, print/document and recovery checks. Test denied, duplicate, retry, empty, concurrent and rollback paths for affected invariants.
For UI use authenticated role-based Playwright with meaningful viewports, screenshots and keyboard/focus/empty/denied paths. For print inspect rendered PDF/receipt bytes and pagination/totals, not merely the build.
Classify failures before changing code: stale expectation, app defect, integration mismatch, runner/environment, source/authority drift, missing evidence. Preserve exact commands, exits, artifact IDs and NOT_RUN. Re-run changed-dependent tests rather than entire unrelated historical suites.
