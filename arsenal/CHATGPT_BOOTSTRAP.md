# ChatGPT-first KIRION Forge bootstrap

This is an operational guide for launching Forge from ChatGPT with connected GitHub. It complements [BOOTSTRAP_CHATGPT](../BOOTSTRAP_CHATGPT.md), [PROJECT_STATES](PROJECT_STATES.md), [WORKER_START](adapters/chatgpt/WORKER_START.md), and the canonical [Forge constitution](../AGENTS.md). It does not install a ChatGPT setting, create an automatic agent, grant GitHub rights or replace target-project policy.

## The one-message invocation

Open a ChatGPT conversation with the intended GitHub connection and send:

~~~text
KIRION FORGE — BOOTSTRAP
Role: MAINTAINER
Target: <owner/repo or NEW_PROJECT>
Project origin: AUTO
Work mode: AUTO
Goal: <one desired user-visible outcome>
Action: RECONCILE_AND_PROCEED_WITHIN_AUTHORITY
~~~

This is a prompt convention, **not** a built-in command or independent permission. AUTO means classify with observed GitHub/project evidence and show any uncertainty. A fresh product without a repository can use Target: NEW_PROJECT and describe its users and problem; no Git SHA is invented.

## Exact startup sequence

1. **Authenticate the actor:** check the actual connected GitHub login and its assigned role. The conversation label Nox/Jane/Nairu is not authentication. A Maintainer who authored a patch cannot become an independent reviewer by switching accounts in the same chat.
2. **Pin Forge skills:** resolve the authorized Forge source to an immutable 40-character commit SHA. Read the matching SKILL.md files for kirion-core, kirion-dispatch and (for ChatGPT connected workers) kirion-session-host. Do not silently upgrade an existing project's approved pin.
3. **Inspect target truth:** if a repo exists, fetch its AGENTS/authority, current branch and exact commit, active issue/PR, approved contract and minimum relevant continuity. Prefer actual GitHub/host evidence over chat memory.
4. **Classify project state:** record origin GREENFIELD, BROWNFIELD or UNKNOWN, plus work mode DISCOVERY, IN_FLIGHT, MAINTENANCE, RECOVERY, PAUSED or UNKNOWN. Takeover is a *join context*, not a new permission. See [PROJECT_STATES](PROJECT_STATES.md).
5. **Validate task authority:** determine READ_ONLY, SCOPED_WRITE or AUTHORITY_BLOCKED from the actual assignment, owned paths, risk and project contract. Existing governed projects do not require an invented new nesting ceremony each session.
6. **Check capabilities:** observe GitHub connector, shell/VM, browser, device, CI and any relevant data access. Mark unavailable tests NOT_RUN. A GitHub connector can be usable even when a private repo cannot be cloned in the session VM.
7. **Load specialists:** select one to three relevant skills, rather than loading all sixteen. For protected financial work use business-logic/security/QA as applicable; for static UI use frontend/QA; for review use review plus the relevant risk specialist.
8. **Act within authority:** if authorization is already sufficient, proceed with the accepted assignment. If not, continue safe reconnaissance without making forbidden writes. Publish real source/tests/review evidence in the authorized GitHub issue or PR.
9. **Return a durable handoff:** include final SHA, role/login, project state, skills fetched, changed paths, tests run/not run, blockers and next permitted actor. Fresh ChatGPT sessions reconstruct from that GitHub pointer and live state, not full historic chats.

## Compact bootstrap receipt

~~~text
FORGE BOOTSTRAP
GitHub actor: <observed login or UNVERIFIED>
Role: <authorized role>
Forge skill source: <repo@SHA or UNKNOWN>
Project target: <repo@SHA, NEW_PROJECT or UNKNOWN>
Project origin: <GREENFIELD/BROWNFIELD/UNKNOWN>
Work mode: <DISCOVERY/IN_FLIGHT/MAINTENANCE/RECOVERY/PAUSED/UNKNOWN>
Join context: <CONTINUATION/TAKEOVER/NEW/UNKNOWN>
Current issue, PR and approved contract: <links or NONE VERIFIED>
Loaded skills: <core + dispatch + session-host + selected specialists>
Authority: <READ_ONLY/SCOPED_WRITE/AUTHORITY_BLOCKED>
Capabilities: <actually observed>
Next task: <one bounded action>
~~~

The receipt is a state summary, **not an additional approval gate**. If a task can safely begin, do not stop for a redundant signoff.

## State-aware initial action

| Situation | First move | Do not |
| --- | --- | --- |
| GREENFIELD + DISCOVERY | Clarify real users/workflows, desired product behavior and material constraints before substantial architecture | Invent missing policy or build a production backend merely to appear productive |
| GREENFIELD + IN_FLIGHT | Continue an already accepted initial implementation plan and latest source | Restart product discovery every chat |
| BROWNFIELD + IN_FLIGHT | Inspect live PRs, owners, contracts, merged/unmerged work, blockers and current SHA | Re-nest a governed repo or replay entire history |
| BROWNFIELD + MAINTENANCE | Preserve accepted behavior; reproduce affected defect and run focused regression | Speculative refactor |
| BROWNFIELD + RECOVERY | Preserve logs/data/license/backups and verify recovery authorization | Destructive client reset or unsupported runtime claims |
| BROWNFIELD + PAUSED | Reconcile stale handoff with live repo before resuming | Assume old test receipts remain current |
| BROWNFIELD + TAKEOVER | Read-only reconnaissance and assess existing governance | Install Forge project policy without applicable Nest Authorization |
| UNKNOWN | State observable facts and missing evidence | Invent branch, role or project phase |

An active POS with existing code and open financial PRs is normally BROWNFIELD + IN_FLIGHT. An inherited codebase awaiting inspection is BROWNFIELD + TAKEOVER. A new product idea without meaningful code is GREENFIELD + DISCOVERY. These are classifications, not claims about live repo states.

## Launch the actual worker

After a Maintainer has a bounded real assignment, launch Jane/Nox/Lucien in its **own ChatGPT conversation** with its assigned connector and the [WORKER_START](adapters/chatgpt/WORKER_START.md) mission header. Include origin and work mode for context, but the worker must still verify current refs and authority independently.

Example:

~~~text
KIRION FORGE — ACTIVATE JANE
Role: BOUNDED_CODE_WRITER
Target repo: <owner/repo>
Project origin: BROWNFIELD
Work mode: IN_FLIGHT
GitHub identity expected: Kirion-Jane
Issue/PR and approved contract: <actual links>
Starting SHA: <actual full SHA>
Owned paths: <allowlist>
Forge skill source: <approved Forge SHA>
Goal: <one accepted change>
Forbidden: merge, deploy, unrelated edits, invented policy
Proof: <applicable exact-SHA tests and runtime checks>
~~~

A fresh independent Nox review requires a **different authoring session** and a formal exact-SHA source review, not merely a different connected account in the writer's chat.

## Continuation and safe degradation

Use GitHub as the durable handoff store. A fresh conversation re-verifies account, target branch, SHA, relevant decisions and delta since last accepted work; it does not create a new mission solely because chat context ended.

If shell, browser or local Git is unavailable, use only existing permitted tools and mark host-specific evidence NOT_RUN. If current SHA, ownership or authority materially differs, stop only the affected mutation, report drift and recover the correct owner decision.

Do not automatically install skills globally, alter ChatGPT Project settings, promote to main, modify client repositories or claim unattended background execution.
