# ChatGPT host port — R1 diagnostic candidate

Mission: FORGE-CHATGPT-SOFTWARE-FACTORY-PORT-R1; authority: Issue #15.
Source commit `0e8765de6e0e87ea9b4503714f08fa650e1a79c6`, tree `80eaa7a4f879871e5df533203b8b60b563f8b782` (unmerged PR #14).
No self-acceptance, merge, release or production mutation.

## Inheritance
The parent commit is the full original factory. All original core and specialist skills, ten personas, workflows, profiles, schemas, tests, benchmarks, hooks and governance remain in place. The source inventory records exact Git blob IDs. This adapter does not replace any canonical factory module.

## Host boundaries
- connector_adapter.mjs authenticates a selected connection by exact login and immutable numeric actor ID, checks repository permissions and pins a branch head AND tree. Role and authority must still be validated by the inherited core. No secret or connection IDs are stored in the adapter.
- The adapter deliberately has no remote mutation capability. The canonical broker requires a durable bridge between its verified local state and connector operations; until that is available, delivery is blocked rather than simulated. The Issue #15 diagnostic publication itself is a narrow operator-authorized bootstrap, not evidence of a working general purpose broker.
- No native launcher, isolated context ID, lifecycle hook, credential sandbox or durable cross-chat journal has been verified. Do not map logical persona to a fabricated session. Use separately authorized, sequential handoffs; no reviewer acceptance from the author's context. Explicit total cap three including primary; if isolation or active count is unknown, block concurrent dispatch.
- Source packets, schemas, scheduler, ownership, evidence, QA and recovery must be handled by the original Python implementation. See host_bridge.py and qualification.py. Never mark a mock as a runtime or enforcement gate.
- Original Antigravity workflows remain source contracts; their native agent()/phase() calls are not portable. Each phase requires a real separate session and recorded evidence. Any native hook requirement stays blocked until demonstrated.
- Account release 0.2.0 remains unchanged. The v0.2.1 advisory checks and subsequent repair are supplemental, not the baseline engine.

## Reproduce
With an authenticated full checkout, freeze the exact source and use an isolated worktree without client credentials. Run unchanged baseline and candidate tests via qualification.py; inspect raw results and no skipped gate may be reported PASS. Run `node integrations/chatgpt/connector_adapter.test.mjs` for offline adapter tests. Use package.py only on a verified full checkout and the exact extracted account release; do not install or promote without separate acceptance.

## Current status
HOLD / diagnostic candidate. The GitHub connector can fetch source and actor identity but cannot supply a full filesystem checkout to the current execution sandbox. DNS clone failure and missing PHP DB/.NET runtimes block comparative A–E execution. The JSON evidence contains live read probes and mock results. No qualification, runtime parity or independent review claim.
