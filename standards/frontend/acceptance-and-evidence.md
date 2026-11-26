# Acceptance and evidence
Sources E1–E2. Read for every delivery. Existing Forge evidence/review/QA policies govern actual authority.

## E1 — Evidence ladder (MUST)
Label each check and its actual environment, not just PASS.
| Tier | Proves | Does not prove |
|---|---|---|
| SOURCE | source inspection, types, unit, static rules | rendered tree, live operation |
| MOCKED_UI / authorized SHOWCASE | interaction/design using fixture | real backend, auth, money |
| DIST_PREVIEW_E2E | compiled bundle routes, geometry, startup in preview | installed/entitled protected workflows |
| INTEGRATED_HOST | actual service, disposable real DB, browser interaction | production entitlement, installed hardware |
| RELEASE_ENTITLED | exact Release artifact with approved entitlement in sandbox | admin installer, actual hardware/customer acceptance |
| PHYSICAL / HUMAN_REQUIRED | actual installer/device/printer/operator when executed | unrelated targets |
Separate source-inspected, runtime executed, operator-reported, inference, and NOT_RUN; a report can describe observed runtime but is not independent execution by its reader. No zero-test PASS. Screenshots require role/route/state/viewport/theme/locale, actual URL/launcher and candidate build, sanitized data and before/after if relevant. Record artifact digest, source SHA, build manifest, environment/tool versions, commands, exit and counts, raw logs/captures in authorized storage. Do not claim SHA alone proves artifact lineage. Hosted blockers and untested devices remain explicit; no invented pass.

## E2 — Discriminating acceptance (MUST)
- Verify target identity before tests: route tree/import reachability, artifact actually served, observed feature marker not stale shell, alias parity; confirm tests fail against known wrong implementation or negative case. Native dialog test checks actual open state and focus, not unused role attribute. Verify computed theme, not just storage key.
- Test product journey outcomes: allowed actor can complete and observe authoritative receipt/persisted change; denied actor cannot use direct route/API; invalid/unknown/retry behavior preserves integrity; inspect relevant DB or authoritative readback in disposable environment.
- Visual acceptance: compare against approved reference in equivalent states, evaluate hierarchy, spacing, fonts, color, density, interaction and secondary pages. Screenshots plus human inspection; geometry checks (overflow, clipping, image loading, focus, console/network errors) complement but do not replace judgment.
- Check accessibility across applicable routes/states, manual keyboard, zoom, reduced motion, screen reader sample; report actual axe scope. Check performance with production build, representative devices/data, cold/warm and interaction measurement; frontend_web profile budgets LCP 2500 ms, INP 200 ms, CLS 0.1 where applicable; record methodology and distinguish lab proxies from field INP. Track bundle/assets, request fanout and rendering; no universal kB cap.
- Static mock marker/banned-option scan of emitted artifacts SHOULD complement live network and action tests; neither string absence nor source regex proves zero mock behavior. Source anchors can protect migration but require behavioral oracle. Do not change approved acceptance just to satisfy old tests or vice versa; record contradictions.
- For critical operations check repeated/concurrent actions, server invariants, failure/retry, storage/platform parity; full review at exact SHA by authorized nonauthor where required. 

Receipt template: objective | base/head | actual target and artifact | role/state/viewport | assertion and expected result | command / evidence link | executed count | PASS/FAIL/NOT_RUN/BLOCKED/HUMAN_REQUIRED | limitations | disposition. Include what was NOT tested. Source-only documentation work does not qualify client products.
