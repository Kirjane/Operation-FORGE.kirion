# Skill Arsenal Adoption, Promotion and Recovery

**Purpose:** an operational runbook for distributing and adopting the existing Kirion Skill Arsenal v0.2 without overriding Forge's canonical authority, adding new approval layers, rewriting history or accidentally installing a draft candidate into client environments.

**Primary authority:** [Forge AGENTS](../AGENTS.md), [authority record](../.forge/AUTHORITY.md), [promotion protocol](../protocols/promotion.md), [promotion checklist](../checklists/promotion.md). This document explains their application to the Skill Arsenal; it does not replace them.

**Back to:** [Arsenal handbook](README.md) · [Forge home](../README.md) · [Examples](EXAMPLES.md).

## 1. Do not conflate adoption states

| State | Exactly what is authorized | What it does NOT authorize |
| --- | --- | --- |
| **CANDIDATE / DRAFT** | An immutable proposed skill tree may be inspected or used only for explicitly authorized opt-in missions | Claiming main contains it; global host install; change to client acceptance |
| **SOURCE ACCEPTED** | Independent source review and Engineer acceptance of an exact candidate SHA | Moving main without a separate promotion operation |
| **REPOSITORY DISTRIBUTED** | An authorized non-force merge or fast-forward places the accepted source on Forge main | Automatic configuration in ChatGPT, Codex, Antigravity or client repos |
| **HOST CONFIGURED** | An authorized person configures the relevant host to discover/pin skills | Cross-host credential sharing or new GitHub rights |
| **DEFAULT WORKFLOW ADOPTED** | Engineer-approved project/role guidance makes a specific skill bootstrap the default | Superseding explicit project feature policy or legacy client review gates |
| **CLIENT RELEASED** | A separate client application's accepted code has been released under its own project rules | Inferred from the Forge repo merge |

A single PR can contain code, docs, tests and manifest metadata, but no line in that PR can install a ChatGPT Project setting or grant a GitHub permission.

## 2. What is included in the v0.2 source package

- Sixteen canonical .agents/skills/*/SKILL.md entries.
- Manifest defining the version, source status, default core, dispatcher and generator.
- Host adapter fragments: ChatGPT launch/project instructions, Codex AGENTS pointer, Antigravity GEMINI pointer.
- Standard-library disposable mission-skill generator with opt-in workspace guard.
- Automatic-discovery tests checking manifest count, frontmatter, skill paths, adapter references and generator adversarial behavior.
- User and Maintainer documentation, including README and this runbook.
- Existing Forge and entity validators; no separate control-plane service.

Packaging **does not** include a preconfigured external worker instance, credentials, a global filesystem installation, a new reviewer account or a deployed application.

## 3. Candidate readiness checklist

Use one *exact* candidate source SHA throughout the readiness review. If anything changes, reclassify prior tests/reviews by their observed SHA and assess the new delta.

- [ ] Current PR, branch and exact 40-character commit observed from authenticated GitHub.
- [ ] Candidate is a descendant of its declared predecessor; no force-pushed or unexplained historical replacement.
- [ ] Target main SHA verified and integration conflicts checked.
- [ ] All sixteen SKILL.md files exist at the candidate and frontmatter directory names match.
- [ ] Host adapter references, README links, and manifest entrypoints resolve.
- [ ] No instruction pretends to override the target project, grant runtime rights or create automatic global installs.
- [ ] CI: repository structure, schemas, links, NEST mechanical, all arsenal tests.
- [ ] CI: integrated entity shared-contract checks.
- [ ] Any relevant defect-specific negative regression test exists and genuinely rejects the faulty case.
- [ ] Independent nonauthor reviewer inspects exact candidate and consumers; formal result recorded.
- [ ] Explicit Engineer acceptance identifies exact source and intended **scope of adoption**.
- [ ] Promotion operation, target ref and main precondition explicitly authorized.
- [ ] Source change has no hidden release/deployment side effect; if merging triggers deployment, check separate release authority.
- [ ] Safe non-force promotion selected; post-merge remote SHA will be read back.
- [ ] Durable record and follow-up on host-specific adoption assigned.

This is an operational unpacking of existing Forge promotion requirements, **not** a new set of independent approvals or a second acceptance bureaucracy.

## 4. Review discipline

**Separate source authorship from independent judgment.** A reviewer must actually inspect the latest candidate and its changed-dependent behavior, with a real nonauthor GitHub identity and an independent review context. Switching to a different linked GitHub account inside the same chat that authored the patch is not sufficient independence.

An old request-changes review on a previous SHA does not magically become an approval after a writer pushes a fix. Conversely, it does not prove that the new version still has that defect; an explicit delta re-review resolves the question.

A proper review record includes:

~~~text
Repository / PR / exact candidate SHA:
Authenticated reviewer account:
Author and reviewer separation:
Changes and affected consumers actually inspected:
Relevant project / Forge authority:
CI and test evidence independently checked:
Findings: severity, source, mechanism, required correction:
Tests and runtime NOT_RUN:
Formal verdict:
What this verdict does not authorize:
~~~

A review limited to a two-file correction must not be reinterpreted as independent acceptance of every earlier pilot or of a full client application. The acceptance authority decides whether the reviewed scope is sufficient for the pending promotion.

## 5. Prepare a promotion packet

Use an issue/PR record linked to the source, not a temporary conversation-only note.

~~~text
PROMOTION TARGET: Forge main
CANDIDATE: <exact 40-character SHA>
EXPECTED MAIN: <actual observed main SHA>
PR: <number and URL>
CHANGED FILES: <reviewed scope>
APPROVED ACCEPTANCE: <independent review URL and Engineer decision>
CI: <exact-SHA run IDs / conclusions>
RISKS: <known limitations, status>
OPERATIONS: non-force merge or fast-forward only
POSTCHECK: main SHA and tree, PR merged state, workflow health
ADOPTION: source distributed only / optional worker defaults separately
ROLLBACK: approved safe follow-up or revert, not history rewrite
~~~

Avoid hardcoding a current mutable SHA into documentation with language claiming that it will remain current indefinitely. GitHub's live refs control promotion.

## 6. Non-force Git promotion

This is a **procedure**, not a command to merge without verified prerequisites.

1. Confirm the Engineer authorized the actual destination branch, candidate and intended source-distribution scope.
2. Check the candidate's full ancestry and conflicts with current main, including relevant external checks and branch rules.
3. Verify the independent acceptance result is for the correct SHA or explicitly scopes its review to the final integrated state.
4. Re-read remote main immediately before the authorized operation. If it drifted, stop to assess integration and acceptance.
5. Use the repository's normal approved **non-force PR merge** operation, or a bounded fast-forward when specifically authorized and safe. Do not use a force push, direct default-branch overwrite or hidden rebase that erases candidate history.
6. Re-read remote main, resulting commit, PR state, files and workflow checks. A merge tool returning a success message is not by itself a verified published state.
7. Record source/base/resulting SHA, actor, reviewer, approval, operation, timestamp, validation and any unresolved limits.
8. Update the durable source-of-truth memory under an authorized Maintainer operation and close the appropriate handoff issue if its completion criteria are met.

If a check cannot be observed, **promotion is NOT PERFORMED** under the existing [Forge promotion protocol](../protocols/promotion.md). Do not bypass a reviewer or acceptance gate by relabeling a source-write action.

## 7. Post-promotion: documentation and status hygiene

After an actual verified promotion to main:

- Verify the README landing page and Skill Arsenal handbook render and all relative links resolve.
- Verify manifest version, status and adoption claim are consistent with the accepted source-only scope. A source merge may justify **repository-distributed / opt-in available** language, **not** automatically project-wide or user-wide adoption.
- Keep the historical pilot and pre-promotion review evidence in place; do not rewrite GitHub comments or old commit IDs as if they came from the new version.
- Preserve signed-off client application contracts and their independent release requirements.
- If additional host installation is desired, treat it as a separately authorized configuration action by the relevant user or organization.
- Do not declare Forge NEST-3/NEST-4 or stable platform maturity merely because skills were merged.

For a future version, create a distinct candidate, exact-SHA test/review record and scoped adoption decision. Changing main does not auto-upgrade already-running sessions pinned to earlier commits.

## 8. Host rollout — separate from repository promotion

**ChatGPT:** the connected worker can explicitly fetch pinned SKILL.md content. User-configurable Project instructions are optional. No repository action edits the user's account settings or creates a distinct Nox/Jane conversation automatically.

**Codex:** repository-local skills may be discovered depending on Codex configuration. User-wide installation needs separate local authorization and verification.

**Antigravity:** GEMINI pointer and optional local user skills are independent of Codex and ChatGPT. A directory being present does not prove its host loaded it or followed it.

Verify exact loaded source for each host, and do not claim account-specific capability that was not observed. If a host cannot retrieve the private repository, do not paste credentials into source instructions as a workaround.

## 9. Rollback and recovery

If the accepted skill source later causes confusion, unauthorized scope expansion or unsafe advice:

1. Stop only the affected worker mutation or skill loading; keep evidence.
2. Pin known-good immutable source while the incident is examined. Existing project law still governs.
3. Identify whether the fault is in the skill text, host adapter, incorrect role/authority, stale Git pin, missing context or underlying application.
4. Prepare an explicit bounded correction/revert with independent review and exact-SHA validation. Do not rewrite the accepted Git history.
5. Treat any production client consequences under **that client's separate incident and recovery process**; Forge skill rollback is not a database rollback.
6. Recheck remote main after authorized repair, update release notes and handoff pointers.

Do not auto-reset client data/licenses, disable branch checks or purge evidence just to regain green CI.

## 10. When not to promote

Hold promotion if:

- the only reviewer is the code author or the author's same reasoning conversation;
- the latest source differs from the independently accepted SHA and changed-dependent risk has not been judged;
- the CI cited belongs to an old commit or relevant checks did not actually run;
- a manifest/adapter path or skill count is broken;
- remote main moved since the authorized merge precondition;
- the change implicitly configures external hosts or deploys applications without their approvals;
- applicable project authority or an active source conflict is unresolved.

An explicit user request can authorize work on the promotion packet, docs and bounded implementation. It is **not proof that the technical preconditions have passed**. Source honesty and permission discipline remain part of Forge's purpose.

## 11. Final engineer decision record

A useful explicit adoption statement is:

~~~text
DECISION: Approve / Hold / Reject
SOURCE: Forge PR and exact SHA
SCOPE: repo distribution only / ChatGPT starter default / specific project / other
REVIEW: separate reviewer result and known limitations
CHECKS: exact-SHA Actions evidence
MAIN PRECONDITION: exact source branch and observed main SHA
MERGE: authorized non-force method (or NOT AUTHORIZED)
HOST CONFIG: separately authorized or unchanged
CLIENT PROJECTS: no automatic policy migration or release
MEMORY: destination for durable accepted-state update
~~~

If the final decision is **HOLD**, keep the draft branch and record the unresolved gate without repeated benchmarks or speculative deadlines.
