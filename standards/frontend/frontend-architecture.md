# Frontend architecture
Sources A1–A3 in [register](provenance.md). Follow existing project stack unless explicitly authorized to change.

## A1 — Executable custody (MUST)
Write the target chain: installer/launcher or deployed URL → origin/host routing → HTML/native entry → production build config → route resolver → mounted shell/page → real client/adapter → backend endpoint. Record exact SHA, build command and artifact identity. For parallel apps, identify excluded paths and the test target. Trace dynamic imports, alias resolution in typechecker AND bundler, feature flags and runtime configuration. A route must work on initial navigation, refresh, back/forward, deep link and denied access where applicable. Demonstrate route-specific visible element and action using actual compiled product; a dev flag or preview alone is not production proof. Never equate dead exports or component test with reachable functionality. Unknown route must not silently default to unrelated privileged work.

## A2 — Cohesive components and state (MUST)
Organize by responsibilities, not arbitrary LOC: shell/navigation, semantic primitives, domain features, contract adapters, state/recovery and test fixtures. Keep components that change together together; extract when different ownership, repeated behavior or independently testable policy emerges. Do not invent generic layers or global stores by default. Primitives own styling/accessibility, feature controllers own orchestration, adapters own wire mapping; backend owns domain transitions. Use a consistent public interface; avoid barrel cycles and hidden side effects.
Classify state before implementation:
| State | Owner | Refresh/lifetime |
|---|---|---|
| Protected record, permission, total | server | refetch/reconcile after accepted mutation; cache scoped to identity |
| Route/filter/page selection | URL if shareable and non-sensitive | back/forward and refresh |
| Input/draft/overlay | nearest feature | preserve safe edits on refresh, reset intentionally |
| Derived display | pure computation from current inputs | do not duplicate into mutable truth |
| Cached read | query/cache layer | freshness, identity partition, invalidation, stale marking |
| Pending intent | approved recovery store | see integration |
| Preference | local device when authorized | no secrets, no authority |
Keep request cancellation or sequence guards for rapid changes; reject late responses from prior actor or query. Isolate per-module loading/error/permission; global startup gates only for actual shared prerequisites. Initial skeleton when no data; background refresh retains current UI and stale marker. Do not unmount forms or confirmation when refreshing. Reconcile invalid selected record after response rather than forcibly reset all state.

## A3 — Migration and integration (MUST)
Inventory existing consumers (routes, static/dynamic import graph, CSS classes, accessibility behavior, tests, external URLs, backend rules). Decide remove, migrate together, or coexist with an explicit bridge and sunset criteria. A disposable donor may permit clean replacement; canonical production often needs incremental migration. Use stateless token/primitive extraction and one thin live route to establish contract before scaling. Avoid copying mock transports, fixture storage, unauthorized assets/network calls or client permissions. Preserve legitimate approved donor affordances through actual mounting; additive compatibility is not permission to leave the obsolete screen as the actual default. If genuine backend gap exists, record contract, required capability and authorized follow-on; do not fake success, silently discard interface or mutate outside scope.
For coexistence, make route ownership, fallback conditions, flags and launcher transition explicit. Define old/new parity by user outcome, not class names. Retire only after authorized proof of all consumers and rollback plan. A framework rewrite requires explicit product/engineering rationale, not reference stack preference.

Acceptance: route/build custody demonstrable; actual new tree rendered; type/bundle aliases aligned; live states isolated; consumer inventory and residual bridge documented; deep-link, history, failure and permission regressions tested. [Workflow](implementation-workflow.md).
