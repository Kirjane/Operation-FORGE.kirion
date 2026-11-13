---
name: kirion-architecture
description: Plan minimal end-to-end feature architecture grounded in existing source, approved domain rules, real consumers and reversible risk boundaries.
---

# Minimal architecture
Start from actual user outcome and current repo. Trace the vertical path **only through existing or explicitly approved layers** (UI, API, domain, storage, auth and runtime as applicable), with relevant boundaries and protected invariants. An approved static/frontend-only showcase does not require a new backend, authentication, persistence or production workflow engine. Trace actual upstream and downstream consumers before altering interfaces.
Reuse existing code before adding abstractions, dependencies, microservices or second frameworks. A new component must solve a demonstrated problem and define acceptance/rollback. Don't infer business approval from screenshots or one historical note.
Return a small decision record: verified starting source, approved contract, chosen simple design, affected interfaces/files, alternatives rejected, explicit unknowns and testable conditions. Architecture is not implementation or release authority.
