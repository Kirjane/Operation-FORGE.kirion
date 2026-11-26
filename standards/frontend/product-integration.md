# Product integration and transaction safety
Sources P1–P4. The frontend is a consumer of domain authority, not a substitute for it.

## P1 — Contract fidelity (MUST)
For each action specify endpoint, actor, permission, current state, input/output, validation, concurrency/idempotency semantics, confirmation and error contract. Use generated or explicit typed wire DTOs plus runtime validation at uncertain boundaries. Normalize names, enum values, date/time and money units in one adapter, not dozens of components. Preserve unknown/unavailable fields as such; reject malformed responses rather than silently default. Server projections (allowedActions, permissions, navigation) guide affordances but every protected route and mutation independently authorized. Never send hidden sensitive fields merely to suppress in UI. Do not alter backend policy to accommodate an aesthetic. Use integer minor units/approved decimal representation for display and exact input; server decides financial totals, tax, rounding and eligibility. Client estimates clearly provisional.

## P2 — Explicit state model (MUST)
Represent distinct outcomes, e.g.:
```ts
type Read<T> =
 | { kind: 'loading' }
 | { kind: 'ready'; data: T; freshness: 'fresh' | 'stale' }
 | { kind: 'empty' }
 | { kind: 'denied' }
 | { kind: 'redacted'; reason: string }
 | { kind: 'provisional'; data: T; reason: string }
 | { kind: 'error'; retryable: boolean; message: string };
```
A genuine empty collection means successful authorized response; zero is a numeric fact, not absence. Partial response may contain separately classified fields. Preserve safe input on 422/400 field validation; 401 reauth, 403 deny/revoke, 409 conflict or uncertain idempotency (per actual error code), 429 respect retry guidance, 5xx/network outcome unknown where mutation could commit. Never auto-retry a non-idempotent write blindly. A success message requires confirmed response/readback per contract. Session/host change cancels requests, purges scoped caches, fences pending work; reveal no sensitive detail in copy or logs. License/bootstrap only where actual product requires, sequence before operational mount. Surface-specific APIs must not probe unauthorized host/network origins.

## P3 — Browser persistence reconciliation (MUST)
ONE TALIBON prohibited local business stores in its canonical server-backed pages. Salryn records pending intent to recover an uncertain transaction. Invariant: no client store is authoritative business persistence or proof of permission/commit. Preference, safe draft, cache and prepared intent have distinct policy. Default to transient state; durable recovery only if explicitly required and approved, with data classification, retention, threat model (XSS, shared device, actor/host changes, tampering, clock change, storage failure) and server idempotency. Avoid sensitive/credential/payment secrets; localStorage is readable by same-origin script, not secure storage. Browser storage is not mandatory or inherently safe; native platform secure storage may have different contracts.
For consequential operations that need recovery, design this state machine:
1. Prepare stable operation key, canonical payload including timestamps/line IDs, scope, authenticated actor, target host/tenant, schema version, creation/expiry; persist minimal recoverable fields BEFORE dispatch. If required storage fails, do not send.
2. Synchronously prevent local double click; acquire cross-context exclusion if supported, check authority and lease ownership again; server must deduplicate atomically by scope/key and compare payload fingerprint. Web Locks can assist same-origin concurrency, not other devices. A storage compare/readback lease is not atomic or a security boundary; two tabs may both believe they own it or lease can expire mid-request. Test races/expiry; require authoritative server idempotency even with lock; otherwise fail closed when no proven exclusion.
3. Dispatch exact payload/key; mark awaiting confirmation. On ambiguous timeout/reload preserve pending, show explicit uncertain status, query authoritative receipt or retry same key/payload only under same current verified authority. No newly generated IDs/time or lost line items.
4. On confirmation validate returned receipt, reconcile read state then clear safely. Rejection/conflict requires policy-specific resolution; never silently dismiss unresolved money movement. Audit-dismiss only authorized and distinguishes dismissal from settlement. Corrupt/legacy/mismatched actor/host and expiry fence replay, do not simply delete unresolved intent; provide safe manual reconciliation without disclosing other actor data.
5. Offline queue only with explicit product policy, bounded size/expiry and reconciliation; no fake completed checkout. Logout/role revocation fences, retention policy handles safe purge; no replay under another user.
Tradeoff: durable intent adds complexity/storage exposure; simple idempotent preference edits may need only retry/refetch. Strong server contracts or receipt lookup may avoid persisting payload entirely.

## P4 — Real platform boundary (MUST)
Validate live adapter against actual engine, session, origin and permission states; test production artifact and platform-specific storage/network semantics rather than only in-memory doubles. Test native clear/write/empty/lock/unavailable, app suspension/restart and device identity where relevant. For attachments enforce authorized server bytes and provenance; generated Blob is fine for approved client-generated export, not substitute for official files. External maps/analytics/fonts require approved privacy/network and correct provenance; schematic must be labeled. 
Acceptance: positive/negative action matrix; direct unauthorized requests denied; no leaked redacted data; confirmed outcome and persisted server invariants; stale/unknown states visible; retry exact identity and payload; double click, multi-context, replay, storage failure, expiry, actor/host swap, conflict and real adapter cases as applicable. Record untested cases.
