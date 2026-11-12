---
name: kirion-business-logic
description: Audit and implement transactional business rules for procurement, cash, payments, inventory, supplier/customer accounts, printing and approvals without guessing product policy.
---

# Business logic integrity
Before algorithm, establish approved actors/permissions, entities, lifecycle transitions, precision/currency, source of truth, audit trail, idempotency, failure recovery, and protected invariants. Material missing policy stays UNKNOWN for Engineer approval.
Money: store exact minor units/decimal, reconcile totals, discounts, tax, refunds, shift cash, tender types and partial payments. AP/AR: distinguish PR, PO, receiving, invoices, supplier credit, settlement and returns; forbid cross-supplier allocation and duplicate payments. Stock: movement-ledger conservation, unit conversions/BOM, atomic sale/return/cancellation, denied negative/phantom stock unless approved. Documents: correct role custody and actual rendered print/PDF bytes, not raw source or markup.
Write disposable DB tests for positive/denied/duplicate/partial/concurrent/restart paths; use PostgreSQL when PG semantics matter, SQLite only when valid. Check persisted rows and reports against ledger. HIGH/CRITICAL financial changes need independent exact-SHA review and real host acceptance as required by the project.
