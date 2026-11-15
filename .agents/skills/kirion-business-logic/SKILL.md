---
name: kirion-business-logic
description: Audit and implement transactional business rules for procurement, cash, payments, inventory, supplier/customer accounts, printing and approvals without guessing product policy.
---

# Business logic integrity
Before algorithm, establish approved actors/permissions, entities, lifecycle transitions, precision/currency, source of truth, audit trail, idempotency, failure recovery, and protected invariants. Material missing policy stays UNKNOWN for Engineer approval.
Money: store exact minor units/decimal, reconcile totals, discounts, tax, refunds, shift cash, tender types and partial payments. AP/AR: distinguish PR, PO, receiving, invoices, supplier credit, settlement and returns; forbid cross-supplier allocation and duplicate payments. Stock: movement-ledger conservation, unit conversions/BOM, atomic sale/return/cancellation, denied negative/phantom stock unless approved. Documents: correct role custody and actual rendered print/PDF bytes, not raw source or markup.
Write disposable DB tests for positive/denied/duplicate/partial/concurrent/restart paths; use PostgreSQL when PG semantics matter, SQLite only when valid. Check persisted rows and reports against ledger. HIGH/CRITICAL financial changes need independent exact-SHA review and real host acceptance as required by the project.

## Transaction and document truth checklist
Before editing, trace **trigger → actor permission → state transition → persisted ledger/row → report → user-visible document → retry/restart effect**. Identify the approved feature contract/issue that defines each event; unresolved decisions go to the Engineer, not the model.

- **Distinct events stay distinct.** A requested/planned payment date, the actual funds-transfer date, and the later confirmation timestamp are potentially different facts. Do not infer one from another, backfill unknown history, or say money cleared at a provider from an operator's declaration. Whether these fields exist and their precise definitions come from the project's approved contract.
- **Exact reconciliation.** For each accepted financial event, prove signed minor-unit/decimal amounts, original liability/stock balance, resulting balance, ledger posting count, and report totals from persisted state; compare voucher/receipt content to the same state. A bank *name* is not an account identifier.
- **Negative invariants.** Unauthorized actor, wrong supplier/tenant/owner, stale balance, future/invalid actual date (when forbidden by contract), replay and concurrent settlement must not yield partially applied records or duplicated ledger entries. A pending/unposted record must not inflate disbursed/paid metrics.
- **Temporal and offline boundaries.** Use the approved business-local calendar for date-only fields; separately preserve exact timestamps and UTC offsets. Test restart/rollback, historical unknown values, old API clients and schema migration from a disposable prior-version DB.
- **Document output.** Generate and inspect real rendered PDF/receipt/voucher bytes, labels, totals and pagination when document behavior is in scope. Do not confuse HTML, source code or a screenshot of a modal with physical print correctness.

**Evidence mini-matrix:** approved rule/reference | user/API action | expected persisted effect | actual query/test result and SHA | denied/replay/edge proof | remaining UNKNOWN. Risk-scaled implementation remains under `kirion-worker`; the business logic skill supplies domain-specific checks, not a new approval or automatic release gate.
