# Kirion Skill Arsenal — Mission and Handoff Examples

These are **illustrative templates**, not preapproved work orders or claims that any named client repository has been tested. Replace every placeholder from actual GitHub, product authority, owner decisions and available tools. A sample SHA is not an authority anchor.

[Arsenal handbook](README.md) · [Adoption runbook](ADOPTION.md) · [ChatGPT worker start](adapters/chatgpt/WORKER_START.md).

## Example A — Scoped static frontend showcase

**Intent:** improve an explicitly approved, frontend-only fictional demonstration without inventing production backend infrastructure.

**Select:** kirion-core + kirion-dispatch + kirion-session-host (ChatGPT); specialists **kirion-frontend**, **kirion-qa**.

~~~text
MISSION: STATIC-DEMO-MOBILE-POLISH
ROLE: bounded frontend writer
TARGET: Example/OfficeShowcase
START SOURCE: <observed source SHA>
OWNED PATHS: the approved CSS/component/test allowlist
CONTRACT: fictional UI and sample data are explicitly permitted
PROHIBITED: real login, database, issuing official documents, deploying
PROOF: representative desktop/mobile screenshots, keyboard/focus,
       navigation, simulated roles, truthful SAMPLE markings,
       build and browser errors
NEXT: hand off exact candidate SHA to nonauthor review
~~~

**Do not claim:** a simulated role chooser is enforcement, a sample PDF is an authentic certificate, or the UI demonstrates a working production office backend.

## Example B — Cash/accounting workflow correction

**Intent:** repair an already-approved financial rule in a transactional application.

**Select:** kirion-core, dispatch, session-host; specialists **kirion-business-logic**, **kirion-worker**, **kirion-qa**. Add security/review only where project risk or real boundary warrants it; separate reviewer session later.

~~~text
MISSION: CASH-SESSION-VALIDATION
ROLE: single bounded code writer
TARGET: Example/PointOfSale
SOURCE: <actual SHA and current issue>
ACTORS: contract-approved cashier, manager, other roles
OWNERSHIP: exact service/test paths
INVARIANTS: no cash posting without accountable active shift,
            no cross-owner mutation, no duplicated ledger entries
SAFE DATA: disposable DB only
PROOF: accepted cash path, denied/no-shift path,
       replay/concurrency, reports/totals, restart,
       exact commands/logs at final SHA
FORBIDDEN: client DB reset, invented refund policy, force push, release
~~~

**Do not claim:** source inspection alone proves money was not duplicated. Required persistence and retry evidence comes from actual executed tests.

## Example C — Independent security/financial review

**Intent:** independently evaluate a frozen code candidate, not produce a patch.

**Select:** core + dispatch + session-host; specialists **kirion-review**, **kirion-business-logic**, **kirion-security** where applicable.

~~~text
MISSION: PR-EXACT-SHA-REVIEW
ROLE: READ_ONLY independent reviewer
TARGET: Example/Service PR #12
CANDIDATE SHA: <full commit>
BASE SHA: <full commit>
REVIEWER: <actually authenticated different account and session>
PROOF: changed-dependent caller and negative paths;
       distinguished executed versus reported CI/runtime;
       path/line/violation/mechanism for each defect
OUTPUT: formal review with severity, verdict, exact SHA
FORBIDDEN: source edits, self-approval, merge, production modifications
~~~

A formal review from a different GitHub login is still **not independent** if the same authoring conversation wrote the code. Use a genuine separate session.

## Example D — Windows installation and license-preservation repair

**Intent:** validate an approved runtime correction without destroying client retained state.

**Select:** core, dispatch, session-host; **kirion-runtime**, **kirion-qa**, **kirion-security** when permissions or retained credentials are involved.

~~~text
MISSION: WINDOWS-INSTALL-REOPEN
ROLE: bounded runtime/QA operator
TARGET: Example/DesktopApp
SOURCE: exact installed build SHA or UNKNOWN
PRECHECK: machine context, writable paths, license, backups
SCOPE: approved repair without client-data reset
PROOF: non-elevated install/reopen, SQLite write access,
       license retention, API/browser behavior, relevant logs
NOT_RUN: any host or device not actually available
STOP: backup/license ambiguity, destructive data migration
~~~

**Do not claim:** installer tests on a disposable machine prove an unrelated customer laptop was repaired.

## Example E — Fresh-session source reconstruction

**Intent:** replace a stale chat handoff with real source truth.

**Select:** core, dispatch, session-host; **kirion-cognition**, **kirion-evidence**.

~~~text
MISSION: RESUME-ACTIVE-WORK
ROLE: READ_ONLY Maintainer/reconciler
TARGET: Example/Product
REPOSITORY: current GitHub connection
INPUT: old handoff or historical issue
RECONCILE: live main, active PRs, latest Engineer decisions,
           accepted vs superseded work, current review/QA evidence
OUTPUT: compact durable capsule, no invented assignments
STOP: missing current authority or unverified SHA
~~~

A previously approved SHA remains historical evidence, not automatically the current remote branch head.

## Example F — Two-writer integration

**Intent:** combine accepted, bounded nonoverlapping changes without losing either writer's work.

**Select:** core, dispatch, session-host; **kirion-integrator**, **kirion-qa**, **kirion-evidence**. Add business-logic/security when the combined behavior creates a protected risk.

~~~text
MISSION: BOUNDED-BRANCH-INTEGRATION
ROLE: authorized Integration Writer
INPUTS: each donor repo, branch, exact SHA, owned paths and reviews
BASE: actual integration branch and authority
CHECK: ancestry, overlapping files and semantic consumers
PROOF: merge-tree or equivalent conflict analysis,
       integrated positive/negative user flows, full final SHA
HOLD: unresolved ownership, dependency or acceptance
FORBIDDEN: arbitrary "ours" overwrite, force push, main promotion
~~~

A successful text merge is not proof of the combined product contract.

## Minimal evidence capsule to copy

~~~text
Mission:
Actual connected GitHub login:
Role and authorization source:
Project / approved contract:
Repo / branch / source SHA:
Forge source commit / loaded skills:
Owned paths / files changed:
Executed commands, exit codes, environment:
Screenshots, logs or other artifact pointers:
Source-only observations:
Reported external checks:
UNKNOWN / NOT_RUN:
Findings or blockers:
Formal review/acceptance status:
Exact final SHA / durable GitHub pointer:
Next permitted actor and action:
~~~

## Decision examples — do and do not

| Situation | Correct action | Incorrect action |
| --- | --- | --- |
| PR's head changed after reviewer inspected an older SHA | Re-evaluate the changed-dependent delta | Reuse old approval as current |
| New frontend is explicitly fictional/static | Validate demo UX with labeled sample records | Demand real login and database implementation |
| Real financial endpoint hides a button | Verify server authorization and denied writes | Treat UI hiding as security |
| Local checkout unavailable, GitHub connector works | Read/source-write through connector only if authorized; report local tests NOT_RUN | Invent a local build or claim host QA |
| Nox session is the same chat as code author | Refuse independent acceptance claim | Swap accounts and self-approve |
| User requests global skill adoption | Separate source merge, host configuration and project policy decisions | Assume one PR automatically installs all hosts |
| A disposable capsule is generated | Use temporary directory and retire it after the mission | Assume auto deletion or shared VM persistence |

## Scope of these examples

Examples intentionally avoid private credentials, real customer data, fake GitHub approvals and asserted results for existing projects. Use them to form a properly bounded mission only **after** real Engineer/target-project authorization exists. None grants independent acceptance or production deployment rights.
