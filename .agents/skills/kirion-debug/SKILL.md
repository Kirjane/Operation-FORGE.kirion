---
name: kirion-debug
description: Reproduce and classify defects across code, tests, environment, contracts and Git drift before narrow repair with targeted regression tests.
---

# Root cause before code
Observe actual symptom, environment, expected approved behavior, exact SHA. Reproduce in a safe disposable setup, follow the first violated invariant, and use a discriminating negative case. Classify stale test, implementation defect, integration mismatch, environment/tool failure, authority drift, or missing business decision; a red test alone does not tell which side is wrong.
Modify the smallest authorized surface. Retest impacted consumers and relevant positive/denied/edge paths. Do not delete assertions or disable checks merely for green CI; do not re-review unrelated accepted surfaces. Record actual command outputs and NOT_RUN when unavailable.
