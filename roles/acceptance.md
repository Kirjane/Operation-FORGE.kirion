# Acceptance Role

Acceptance determines whether a candidate has sufficient evidence and satisfies the defined criteria for promotion.

The Maintainer may perform Acceptance, but the role remains conceptually separate from implementation.

## Inputs

Acceptance may consider:

- exact candidate SHA;
- expected parent/base state;
- diff and scope review;
- automated tests;
- build/static-analysis results;
- CI results tied to the exact candidate;
- runtime/browser/device evidence;
- security or authorization checks;
- deployment evidence when required;
- known limitations;
- unresolved risks;
- explicit product acceptance criteria.

Resolve the authorized Forge [bootstrap](../BOOTSTRAP.md) and canonical [semantic naming rule](../AGENTS.md#semantic-naming-and-readability), and apply the [Acceptance Checklist](../checklists/acceptance.md) to the exact candidate. If canonical authority is unavailable or mandatory naming-review evidence is missing, record `REWORK` with the reason `ADDITIONAL EVIDENCE REQUIRED` and identify the missing authority or evidence. A confirmed unresolved material naming violation introduced by the candidate requires `REWORK` with the reason `MATERIAL NAMING VIOLATION` and exact candidate/path/identifier evidence. If both conditions apply, record both reasons. Neither condition permits acceptance. Do not infer runtime or product acceptance from naming compliance.

## Outcomes

Record one of the four existing outcomes in the [Acceptance Report](../templates/ACCEPTANCE_REPORT.template.md):

- `ACCEPTED` (ACCEPT, or ACCEPT WITH RECORDED LIMITATION when permitted by the criteria);
- `REWORK` (including ADDITIONAL EVIDENCE REQUIRED as a reason, not a separate outcome);
- `REJECTED` (REJECT);
- `QUARANTINED` (QUARANTINE).

A recorded limitation cannot waive mandatory evidence, unresolved material naming violations, or any other blocking acceptance criterion. Naming evidence alone is not sufficient for `ACCEPTED`.

## Evidence discipline

Passing one evidence layer must not be silently generalized into another.

For example:

- build success does not prove runtime correctness;
- runtime correctness does not prove deployment;
- green CI proves only the workflows and assertions that actually ran;
- static inspection is not execution evidence.

## Promotion

Acceptance itself may authorize promotion only when the current handoff or project authority grants that power. Otherwise, return the acceptance result to the Maintainer or human technical authority for promotion.