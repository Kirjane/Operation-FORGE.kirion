---
id: "forge.skill.kirion-worker"
source_repo: "Kirch-Nairu/Operation-FORGE.kirion"
source_ref: "eabbfbabdbb22d8684fb2c3d80767b8547852b83"
source_path: ".agents/skills/kirion-worker/SKILL.md"
source_status: "CANDIDATE"
source_blob_sha: "af8f21c82a6e6a065f73d9d36ec22483b3351eab"
tags: [forge, arsenal, candidate]
---

# Kirion Worker

**CANDIDATE / OPT_IN_ONLY.** Full canonical skill text at pinned PR #7 SHA. Reading this is not authority or automatic host installation.

[Exact SKILL.md](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/blob/eabbfbabdbb22d8684fb2c3d80767b8547852b83/.agents/skills/kirion-worker/SKILL.md) · [[00 Skill Index]] · [[Specialist Selection]] · [[00 HOME]]

## Canonical contract

# High-quality code writer
Read accepted behavior, actual source and tests, owned files, consumers, exact SHA, adjacent authorization and data invariants. Choose the smallest coherent vertical change; avoid speculative frameworks and drive-by refactors.
Validate inputs at trust boundaries, use clear errors, handle cancellation, concurrency, retries and idempotency correctly, isolate external services, use DB transactions for related changes, preserve data model contracts and backwards compatibility. Make failing states observable; don't swallow errors or fabricate PASS.
Prove at least the applicable positive journey, invalid/denied path, edge/retry/state-change path, and original regression. Use real host/browser/DB/print evidence where risk requires it. If no runtime tool is available, label NOT_RUN.
Return repo@SHA, changed paths, executed commands and exit outcomes, impacted consumers, remaining risk. No self-promotion, merge or deployment without authority.

## Reviewable definition of high-quality code
Judge only the changed and dependent behavior against the approved contract; do not invent new business policies. A candidate is not considered implementation-complete merely because its diff looks clean.

| Dimension | Minimal proof | Failure that blocks a completion claim |
| --- | --- | --- |
| Business correctness | Explicit before/after states and approved positive, denied and edge journeys | Changed an unapproved transition or invented a default |
| Data integrity | Atomic related writes, precise units, safe migration and retry/replay coverage when applicable | Partial write, duplicate effect, data loss or unreviewed migration |
| Security | Backend permission/trust-boundary test appropriate to changed endpoint or resource | Only hid an unauthorized action in the UI |
| Interfaces | Downstream callers and serialized contracts remain compatible or explicitly migrated | Consumer silently breaks or output shape drifts |
| Reliability | Deterministic errors, recoverable failure, concurrency/idempotency tests where material | Swallowed error, inconsistent restart, or double posting |
| Maintainability | Readable cohesive small changes, no speculative abstraction or unrelated dependency churn | Cleanup increases complexity without evidence |
| Evidence | Actual command, environment, exit and exact source SHA; runtime/host proof where required | A claimed PASS from source inspection or an unexecuted test |

For a **LOW-risk** styling/isolated correction, run focused contracts/build and actual visual or behavior check as relevant; do not require irrelevant financial or security suites. For **HIGH/CRITICAL protected** financial, auth, retained-data or irreversible changes, verify negative, concurrency/replay and relevant real-runtime boundaries and follow the target project's independent review rules. Keep independent acceptance and release distinct from implementation. A missing essential check is NOT_RUN/QA_BLOCKED, not a fabricated implementation PASS.
