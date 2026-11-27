# Kirjane frontend engineering standard
Status: authorship candidate, acceptance HOLD; not installed or runtime-enforced. Owner: Lucien (Kirion-Luci3n, 359299805). Authority: [Issue 31](https://github.com/Kirjane/Operation-FORGE.kirion/issues/31), [activation](https://github.com/Kirjane/Operation-FORGE.kirion/issues/31#issuecomment-7184179763).

## Purpose
Build interfaces that are recognizably designed for their operators, complete in behavior, coherent across surfaces, and grounded in the real executable product. Visual excellence and engineering integrity are joint acceptance dimensions. A beautiful unmounted screen and an ugly functioning screen are both incomplete.

MUST = proposed normative requirement (existing controlling project/security requirements remain binding now); SHOULD = default with reasoned deviation; MAY = optional technique. Case examples are not prescriptions. An engineer cannot waive authority, safety, accessibility or truthful evidence through an exception. Escalate conflicting instructions to Maintainer with affected scope; record alternative and evidence. No new permission is conferred by reading this package.

## Activation and progressive loading
At authorized frontend mission start, resolve product, role, owned paths, exact base, target runtime, approved design and backend contract. Read this entrypoint and the existing core/dispatch/frontend skills required by the current host profile. Use only the active approved skill revisions. Load the following by task rather than dumping the entire library.

| Trigger | Read next | Output |
|---|---|---|
| New visual direction or redesign | [Discovery](design-discovery.md), [Visual system](visual-system.md) | Brief, reference decomposition, representative screen |
| Navigation, forms, transitions, touch | [Interaction](interaction-and-motion.md), [Responsive](responsive-accessibility.md) | Interaction/state matrix, usable layouts |
| New routes or migration | [Architecture](frontend-architecture.md), [Workflow](implementation-workflow.md) | Entrypoint/consumer map and mounted vertical slice |
| Live API, money, offline, permissions | [Integration](product-integration.md), architecture | Authority map, typed adapter, recovery policy |
| Every acceptance | [Evidence](acceptance-and-evidence.md) | Exact candidate evidence and limitations |
| Specific defect or precedent | [Patterns](patterns/catalog.md), [Anti-patterns](patterns/anti-patterns.md) | Applicable decision with counterexample |
| Research or skill selection | [Provenance](provenance.md), [Skills](skill-adoption.md) | Evidence classification and load record |
| Future host wiring | [W5 integration](w5-integration.md) | Separate authorized implementation |

## Non-negotiable invariants
1. Discover operator tasks and approved product intent; don't replace them with generic dashboards or narrow them to current API convenience.
2. Trace launcher to actual route, rendered tree and build; keep prototype evidence separate.
3. Design semantics, states, hierarchy, and interactions before styling every screen; preserve coherent brand and accessible responsive behavior.
4. Server owns protected state, decisions and authorization. Client can present, cache or prepare bounded intent, never manufacture confirmation.
5. Preserve legitimate contract and migration boundaries; use a thin mounted vertical slice and iterate on real feedback.
6. Test discriminating outcomes and visual fidelity on the actual target; never claim more than executed. 
7. Keep skills selective and provenance pinned. Full qualification and host activation require separate authority.

Sources: [evidence register](provenance.md) (OT, SC, F); principles D1–D3, V1–V3, I1–I3, A1–A3, P1–P4, R1–R2, W1, E1–E2 in domain documents. Existing Second Brain is conceptual knowledge; this package operationalizes it, not replaces it.

## Lane B runtime declaration
`activation.json` is the machine-readable frontend-specific declaration. Both personas use the same mandatory entrypoint and evidence domain; explicit domain IDs select only relevant documents in declared order. The generic loader owns source/digest verification, actual byte limits, required coverage and load receipts. Native execution owns observed identity and grant custody. This branch adds policy and declarations, not installed activation. The original authorship candidate remains frozen. Only active Lucien may modify canonical standard under a separately authorized mission.
