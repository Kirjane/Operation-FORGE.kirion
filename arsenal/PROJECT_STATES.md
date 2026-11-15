# Project-state routing for KIRION Forge

Forge already distinguishes NEW and EXISTING projects. For a ChatGPT-first engineering operation, keep that authority model while using **two independent routing dimensions**. They determine what context to retrieve, not whether code may be changed.

## Axis A: codebase origin

| Origin | Meaning |
| --- | --- |
| GREENFIELD | A new product with no meaningful previous accepted implementation; an empty or skeletal repository is still greenfield |
| BROWNFIELD | Existing software, accepted behavior, migrations, source or running infrastructure that must be preserved/reconciled |
| UNKNOWN | Evidence insufficient to determine whether meaningful implementation already exists |

A project can begin GREENFIELD and later become BROWNFIELD as accepted implementation constrains subsequent work. Repository age is not sufficient evidence.

## Axis B: current work mode

| Mode | Meaning | Context that matters most |
| --- | --- | --- |
| DISCOVERY | Problem/users/workflows and approved direction still being established | Brief, operator needs, material open decisions |
| IN_FLIGHT | Active implementation/integration/review across live issues and branches | Accepted contract, current PRs, ownership, exact commits, test/review blockers |
| MAINTENANCE | Fixing defects or improving accepted features | Reproduction, known behavior, regression/consumer compatibility |
| RECOVERY | Incident, retained-data, license, outage or security restoration | Severity, evidence, backups, owner approval, verified safe rollback |
| PAUSED | Dormant work being reactivated | Historical handoff versus current Git and active decisions |
| UNKNOWN | No reliable evidence of work mode | Safe reconnaissance and uncertainty |

**TAKEOVER** describes a join context for unfamiliar inherited software; normally BROWNFIELD with an initial read-only pass. **INCIDENT** is an urgency/risk overlay, not a replacement for the project's permanent origin. Production/deployment environment, Forge NEST maturity and risk level are **separate attributes**, not synonyms for GREENFIELD/BROWNFIELD.

## Routing rules

1. For GREENFIELD + DISCOVERY, understand actual user/domain needs and approved scope before major architecture or implementation.
2. For GREENFIELD + IN_FLIGHT, honor approved early work. Do not reset planning merely because the product is young.
3. For BROWNFIELD + IN_FLIGHT, query the live issue/PR and merge/review state, then continue the exact accepted mission. Do not repeat a Forge nest or re-open accepted decisions.
4. For BROWNFIELD + MAINTENANCE, preserve established contracts, source and retained data; test the narrow impacted behavior.
5. For BROWNFIELD + RECOVERY, protect actual backups, credentials, licenses and client data before repair.
6. For BROWNFIELD + PAUSED, reconcile the last handoff with live Git and classify stale or superseded work.
7. For BROWNFIELD + TAKEOVER, inspect existing governance read-only before requesting any **new** Nest Authorization; do not override inherited project rules automatically.
8. For UNKNOWN, explain what could not be observed. Continue permitted discovery rather than inventing a SHA or approval.

## Minimal evidence record

~~~text
Target repository: <owner/repo or NEW_PROJECT>
Project origin: <GREENFIELD/BROWNFIELD/UNKNOWN>
Work mode: <DISCOVERY/IN_FLIGHT/MAINTENANCE/RECOVERY/PAUSED/UNKNOWN>
Join context: <NEW/CONTINUATION/TAKEOVER>
Observed target SHA: <full SHA, NOT_APPLICABLE or UNKNOWN>
Approved project contract: <reference or UNKNOWN>
Active issue/PR and owners: <source pointers>
Next authorized task: <one outcome>
~~~

These routing labels are changeable **per mission**, not a rigid new Forge governance state machine. An ongoing project may temporarily enter incident recovery and then resume in-flight development. Risk, roles, source custody, review and promotion still follow [AGENTS.md](../AGENTS.md), [BOOTSTRAP.md](../BOOTSTRAP.md), the relevant role protocol and the target project's current authority.

For the actual ChatGPT procedure, use [CHATGPT_BOOTSTRAP.md](CHATGPT_BOOTSTRAP.md).
