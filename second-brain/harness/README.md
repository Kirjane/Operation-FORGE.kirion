# Project Second Brain — Cognition Harness Runtime V1

This directory turns Project Second Brain from a passive engineering reference into an executable routing and evidence protocol for software agents.

The runtime does **not** depend on Obsidian. Obsidian remains the human editing and graph-visualization surface. The Markdown/Git repository is the knowledge authority consumed by the harness.

## Contract

An agent is not expected to decide which parts of the brain it feels like reading. The harness must establish a deterministic route before design or implementation:

1. normalize the task;
2. classify the task;
3. score risk and choose adaptive-rigor mode;
4. select required semantic lanes from the 23-lane mesh;
5. resolve exact source notes from the repository;
6. compile a bounded, hash-addressed context pack;
7. activate stage gates and evidence requirements;
8. block unsupported delivery claims;
9. emit reusable failure/learning candidates without silently editing doctrine.

The runtime is intentionally fail-closed. Missing required source notes, ambiguous classification, missing primary journeys for build tasks, and failed BLOCK gates stop the run.

## Quick start

```powershell
node tools/harness/cli.js doctor
node tools/harness/cli.js bootstrap --task harness/examples/sentinelops-greenfield.task.json
node tools/harness/cli.js evaluate --task harness/examples/sentinelops-greenfield.task.json --evidence path/to/evidence.json
```

`bootstrap` writes ephemeral run artifacts under `.harness/runs/<run-id>/`. `.harness/` is ignored by Git.

## Output

A bootstrap run emits `task.normalized.json`, `classification.json`, `risk.json`, `route.json`, `context.manifest.json`, `CONTEXT.md`, `gates.json`, and `RUN.md`.

Every context source carries a SHA-256 content digest. Unresolved expansion links are warnings; unresolved **required seed sources** are blocking failures.

### FCI-M01: source completeness (isolated proposal)

The GIT semantic provider now reserves **all required control-root and active-lane seed files before any optional graph expansion**. If even one required seed is absent or the required sources exceed the configured document/byte budget, the result is `BLOCKED` at **every rigor tier**, rather than a possibly misleading `RESOLVED`. Optional graph neighbours that cannot fit remain nonblocking for LOW/MEDIUM/HIGH subject to existing truncated-context gates, but are explicitly listed as `omitted_optional` with `BYTE_BUDGET` or `DOCUMENT_BUDGET` and surfaced as `NOT LOADED` in the generated context. The existing CRITICAL truncation BLOCK gate remains in effect.

These controls validate **source inclusion only**. They do not prove that a remembered business approval is current, that a Git SHA is the latest remote HEAD, that an optional linked note is safe to ignore for a particular action, or that application tests/runtime claims are true. Those problems require additional provenance and role-specific context work. The Notion semantic snapshot provider and existing `RESOLVED`/`BLOCKED` contract are unchanged in this slice.

Run `node tools/harness/test/run.js` for the fixture regression suite and `python tools/entity_check.py` for integrated repository validation. Do not promote the documentation-only KirionForge R2 proposal to active project authority based on this change alone.

**Independent-review rework (FCI-R1-01–04):** The shipped-mesh completeness check now requires `RESOLVED`, zero required/optional omissions, and valid SHA-256 hashes for every mandatory source; a `BLOCKED` fixture must fail that assertion. CRITICAL capacity coverage includes **all 19 configured routing signals and all 23 routed lanes** at PRE_DESIGN, PRE_IMPLEMENTATION, PRE_DELIVERY and POST_DEPLOY. In the 2026-11-12 exact-candidate root CI run, maximum CRITICAL use at POST_DEPLOY was **224/256 documents** and **286094/393216 bytes**, leaving **32 document slots and 107122 bytes** of measured headroom for the shipped mesh (not a guarantee for future content growth). The MCP bootstrap now labels omitted optional files `NOT LOADED` in both machine-readable metadata and the agent-facing text; it can still say `gate=PASS` for a permitted non-CRITICAL partial context, so agents must heed that warning. Root entity validation now executes the six-test Notion snapshot adversarial suite and MCP adapter syntax check as well as GIT harness tests. These tests do not include a full external MCP protocol transport session or live Notion credentials.

## Agent boundary

The harness is not allowed to manufacture runtime evidence. `TESTED`, `OBSERVED`, `DURABLE`, `DEPLOYED`, and `VERIFIED` are explicit evidence capabilities attached to claims. A commit SHA does not prove runtime behavior. A unit test does not prove a browser route rendered. Documentation does not outrank observation.

See `ENTRYPOINT.md` for the mandatory operating sequence.
