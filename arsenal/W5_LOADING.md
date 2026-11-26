# Arsenal W5 loading contract (draft, not adopted)

The existing Arsenal manifest is the sole candidate registry. A pinned manifest
commit identifies a set of candidate entries; it does not activate them. Every
entry carries a repository ID/name, exact source commit, canonical Markdown path,
Git blob SHA, SHA-256, byte count, dependency IDs and host compatibility modes.
The original 16 portable and 16 specialist candidates remain distinct. No
external code, license grant, global installation or project adoption is implied.

## Generic consumer interface

- **Availability:** SkillRegistry.inventory() lists metadata only.
- **Selection/retrieval:** resolve_skill_plan(profile_key, skill_source_sha=...,
  sources=..., host=..., stage=..., task=..., max_bytes=..., context_used_bytes=...).
  The existing STACK_SKILL_BUNDLES remain required floors; explicit required
  extra IDs are never silently truncated. Required dependency closure comes
  first; stage/task and explicit optional IDs are attempted in deterministic
  order. Omitted optional groups include a reason.
- **W1 projection:** select_skills_for_mission returns only skill_source_sha and
  ordered files for the existing v2 packet. The SHA now identifies the registry
  commit, not a working-tree alias. Per-entry source commits remain in the
  pinned registry. A legacy commit lacking a versioned registry is denied.
- **Context preparation:** FleetDispatcher.prepare_worker_skills(raw, runtime)
  checks the authorized packet against independently configured profile/stage,
  actor/context, budget, registry and actual W3B stage documents. This is
  RETRIEVED_NOT_LOADED. Budget counts raw UTF-8 bytes of selected skill files
  plus prior verified Brain document bytes and configured other context bytes;
  no token-count, prompt framing or native host-limit claim.
- **Actual consumption:** FixtureSkillRuntime supplies a bounded read-only
  FixtureSkillInput; reads deliver text and establish fixture-only consumption.
  Dependencies must have been read before their dependents; required missing
  reads deny the receipt. A separate receipt authenticates the exact plan,
  mission/run/revision, grant/actor/context/attempt, actual reads and outcome.
  This does not prove model comprehension or product correctness.
- **Existing dispatch custody:** FleetDispatcher.dispatch_skill_fixture uses
  the existing ContractJournal and FixtureDispatchAdapter. The signed receipt
  and result digest are part of the actual completion result. Readback uses
  inspect_skill_fixture, never grants replay or promotion. Cached attempts
  do not rerun or automatically reverify the receipt. An older generic fixture
  without this loading composition remains NOT_VERIFIED_BY_GENERIC_DISPATCH.

## Generic canonical standard reference (Lucien interface)

The registry supports kind=reference entries, using the same pinned source
identity and dependency/host metadata. A reference may point to another commit
or authorized local object store, even when absent in the current worktree.
The existing v2 source_authorities must cover its exact repository, commit
and canonical path. Independently configured required_extra selects the
reference ID when applicable; optional_extra is discretionary. Missing source
objects, an unauthorized scope or an incompatible required host deny use.
No fallback, copying or implicit discovery of PR #33 is implemented. Lucien's
actual frontend standard and role policy remain outside Lane A. A later
integration writer must explicitly register approved source pins and reconcile
profile requirements before real frontend activation.

## Host semantics

MANUAL means a human or host may retrieve the text but no native consumption
has been verified. ADVISORY_ONLY means the required load cannot be satisfied.
UNAVAILABLE denies required loading. FIXTURE is the only supported observed
consumption mode here. Native ChatGPT, Codex and Antigravity load attestations
remain unimplemented; availability or retrieval never establishes host rights.
An in-process trusted test callback is not a security boundary against arbitrary
Python execution. Nox owns the independent native composition and later wiring.

## Failure-to-intervention ledger (#19 / #25)

| Finding | Existing mechanism / gap | W5 decision and falsifiable check |
| --- | --- | --- |
| HF-05 / P-001a | 16+16 candidates; SHA syntax and working-tree fallback | ADAPT existing manifest/dispatcher: wrong commit/blob/path/digest, duplicate IDs and dependencies must deny; exact commit bytes must survive dirty worktree. |
| HF-06 / P-001c | Overlapping skills, silent eight-file truncation | ADAPT progressive dependency closure, actual byte limits and optional omission. Required budget overflow denies, optional overflow cannot displace required inputs. |
| HF-08 / P-001a | Discovery/selection conflated with loading | ADAPT receipt semantics, verify actual fixture reads; missing reads/native capability deny. Native host bridge DEFER to Lane C. |
| HF-09 / P-001e | No controlled comparative skill ROI | DEFER adoption: later controlled business-task comparison, defect/rework, time and cost with existing safety floors. |
| HF-10 / P-001b | Project-specific guidance can become global policy | ADAPT scoped pinned references; exact source authority must cover path and revision. Frontend standard content DEFER to Lane B/convergence. |
| HF-11 / P-001c | Overengineering and context overload | ADAPT existing W3B context accounting; external Ponytail benchmark remains DEFER, no code import and no claims of measured savings. |
| External Agent Skills, Superpowers, Anthropic skills / knowledge-work plugins, Open SWE, OpenHands, Microsoft agent framework | Research candidates only; exact licensing/source/adoption and incremental value not independently accepted | DEFER all imports/installations; existing Markdown, stdlib Git and Factory contracts suffice for this slice. Qualification must compare actual product task outcomes, not candidate counts. |

All ADAPT decisions here are implementation hypotheses, not independent
adoption or promotion decisions. See issues #19 and #25 and the existing
Arsenal ADOPTION.md for promotion constraints.
