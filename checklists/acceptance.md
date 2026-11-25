# Acceptance Checklist

- [ ] Candidate SHA is exact and reachable.
- [ ] Writer did not self-accept by role implication.
- [ ] Acceptance criteria are explicit.
- [ ] Required evidence exists for the risk class.
- [ ] Evidence types match the claims being accepted.
- [ ] Known failures are classified.
- [ ] `NOT RUN` and unverified claims are visible.
- [ ] Scope/ownership violations are reviewed.
- [ ] Authorized Forge bootstrap and canonical [semantic naming rule](../AGENTS.md#semantic-naming-and-readability) are resolved; exact-candidate naming review is evidenced, material introduced violations are resolved, compatibility is preserved and legacy cleanup remains separately authorized.
- [ ] Authority drift is checked.
- [ ] Result is one of ACCEPTED / REWORK / REJECTED / QUARANTINED with rationale in the [Acceptance Report](../templates/ACCEPTANCE_REPORT.template.md).

Apply the [Acceptance role](../roles/acceptance.md) dispositions: unavailable canonical authority or missing mandatory naming-review evidence requires `REWORK` with reason `ADDITIONAL EVIDENCE REQUIRED`; a confirmed unresolved material naming violation requires `REWORK` with reason `MATERIAL NAMING VIOLATION`. Record both reasons if both apply. Neither may be waived as a recorded limitation. Complete naming evidence clears only the naming requirement; all other mandatory acceptance criteria must be satisfied before `ACCEPTED`.
