# Forge Acceptance Report

PROJECT:
CANDIDATE_BRANCH:
CANDIDATE_SHA:
ACCEPTANCE_ROLE:
RISK_CLASS:

## Criteria

List explicit acceptance criteria.

## Evidence reviewed

For each material claim record evidence level, type, provenance, candidate SHA, environment/scenario, result, artifact, and limitations.

## Scope / authority review

EXPECTED_SCOPE:
OBSERVED_SCOPE:
AUTHORITY_DRIFT:
RESULT:

## Required gates

| Gate | Required | Result | Evidence reference |
|---|---|---|---|
| Semantic naming (authorized canonical rule and exact-candidate review) | Yes | | |
| | | | |

## Known limitations

-

## Unresolved risks

State whether each blocks promotion.

## Decision

One of:

- ACCEPTED
- REWORK
- REJECTED
- QUARANTINED

Record the decision rationale. If canonical authority is unavailable or mandatory naming-review evidence is missing, use `REWORK` with reason `ADDITIONAL EVIDENCE REQUIRED` and identify the missing authority or evidence. If a material introduced naming violation is confirmed and unresolved, use `REWORK` with reason `MATERIAL NAMING VIOLATION` and cite the exact candidate/path/identifier. Record both reasons if both apply. These are reasons, not additional report outcomes or lifecycle states.

A limitation may be accepted and recorded without inventing a separate lifecycle state, but cannot override mandatory evidence, unresolved material naming violations, or other blocking criteria. Complete naming evidence alone does not establish acceptance. Apply the [Acceptance role](../roles/acceptance.md) and [Acceptance Checklist](../checklists/acceptance.md).

## Promotion authority

State explicitly whether a separate promotion authorization exists. Acceptance alone does not imply permission to mutate the authority branch.
