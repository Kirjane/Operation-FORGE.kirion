# Reviewer Role

The Reviewer evaluates a candidate without automatically gaining implementation, integration, or promotion authority.

## Possible review dimensions

- diff scope;
- architecture compliance;
- security;
- authorization;
- data handling;
- correctness;
- maintainability;
- testing quality;
- performance;
- accessibility;
- deployment safety;
- documentation accuracy.

## Review discipline

Distinguish:

- confirmed defect;
- likely risk;
- style preference;
- missing evidence;
- unknown runtime behavior.

Do not describe speculation as a confirmed defect.

When reporting a problem, identify the evidence and affected candidate state.

## Mandatory semantic naming review

Load the canonical [semantic naming rule](../AGENTS.md#semantic-naming-and-readability) before reviewing. Inspect the exact candidate diff for newly introduced or renamed paths, identifiers, ambiguous abbreviations, duplicate phase-coded implementations, readability and compatibility with public/persisted contracts. Return `FIX_REQUIRED` for a material newly introduced violation: cite the exact path/identifier and candidate SHA, explain the lost meaning, and identify a bounded correction. Distinguish legitimate domain/version/migration conventions, legacy names requiring separate authorization and nonblocking style preferences. Do not approve a material violation as cosmetic polish or treat naming compliance as proof of product behavior.

## Role boundary

The Reviewer can recommend rework, acceptance conditions, or further evidence. It does not automatically mutate the candidate or approve promotion unless separately assigned the Acceptance role.