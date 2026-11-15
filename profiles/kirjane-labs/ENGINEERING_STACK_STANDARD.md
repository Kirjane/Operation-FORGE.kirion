# Kirjane Labs — Engineering Stack Standard

**Policy ID:** KIRJANE-ENG-STACK-001  
**Version:** 1.0 proposed  
**Status:** CANDIDATE — not effective until human technical authority accepts and promotes it  
**Owner / approval authority:** Kirjane technical authority (KIRCH)  
**Scope:** New Kirjane-controlled product and client-delivery projects; existing-project migrations require separate authorization  
**Relationship to Forge:** This is a *Kirjane-specific policy profile*, not a global KIRION Forge law or a replacement for project-specific accepted architecture.

## Decision

**C# with ASP.NET Core is the default production backend stack.** Deliberate backend specialization is preferred to routinely adding new backend language/runtime ecosystems. Frontend choice stays problem-dependent. **React + Vite may be deployed independently on Vercel for isolated, frontend-only client demos or showcase previews.**

This is a **default-with-reviewed-exceptions** policy, not a claim that TypeScript/Node.js cannot support concurrent production systems.

## Workload classification and required defaults

| Workload | UI default | Production backend default | Deployment profile |
| --- | --- | --- | --- |
| Sales prototype / client mockup | React + Vite; JavaScript or TypeScript | No backend required if simulation-only | Isolated static Vercel preview |
| Internal office / administrative system | Razor Pages/MVC or React as justified | ASP.NET Core / C# | Controlled production host |
| Transactional POS, inventory, finance, ERP | React where rich interaction is needed; otherwise Razor | ASP.NET Core / C# | Controlled production host with durable DB |
| Business service / automation | Optional UI | C# / .NET Worker or ASP.NET Core | Service/runtime appropriate to workload |
| SaaS / customer-facing platform | React or other justified UI | ASP.NET Core / C# | Dedicated production infrastructure |
| Static corporate site | Static or React | None unless actual server functionality is needed | Static hosting |

Backend language is standardized; **React, Razor, and Blazor are presentation choices** and are not universal mandates. Prefer Razor Pages/MVC for straightforward server-rendered workflows and React for interaction-heavy interfaces. A shared frontend/backend project is allowed when justified.

## Production engineering baseline

1. **Backend authority.** Authentication, authorization, data validation, business rules, transaction processing, monetary calculations, persistence, auditing, secret handling, and privileged integration must be enforced server-side. Client-side checks are usability aids, not security boundaries.
2. **Default architecture.** Begin with a maintainable modular monolith and explicit module boundaries; introduce distributed services only after evidence-based justification.
3. **Persistence.** PostgreSQL is the default multi-user server database; SQLite is allowed for appropriate embedded, offline/local-first, or bounded standalone workloads. Choose based on concurrency, operations, sync, and deployment requirements, not branding.
4. **Data integrity.** For transactions, explicitly design database constraints, isolation/locking strategy, idempotency for retries, optimistic concurrency where appropriate, conflict/error semantics, and rollback. Never rely solely on UI restrictions.
5. **Performance.** Engineer and measure concurrent-user capacity through workload models, DB index and query analysis, connection-pool sizing, timeouts, load tests, and p95/p99 latency/throughput/error metrics. Neither C# nor TypeScript by itself proves scalability.
6. **Security.** Enforce least privilege, secret management, input validation, safe error surfaces, audit trails, dependency review, and secure deployment. Adopt project-specific threat modeling for sensitive systems.
7. **Quality.** Minimum candidate verification includes reproducible build, static analysis/formatting, unit/integration tests appropriate to risk, migration verification, and security checks. Record evidence rather than claiming tests that were not run.
8. **Runtime.** Prefer a currently supported .NET release; choose LTS for long-lived enterprise delivery unless a documented decision states otherwise. Version-pin dependencies and record deployment environment.
9. **Frontend independence.** An API-backed React app must communicate through explicit, versioned or otherwise governed contracts; no frontend-owned authority over privileged production state.

## React + Vercel client-mockup profile

Frontend-only demos are a **first-class delivery artifact** for sales, stakeholder validation, and showcases. They do **not** require a C# backend when all interactions are simulated.

Requirements:

- Use mock/fictional data, local state and seeded demo workflows; clearly label simulated behavior in the project README and client handoff.
- Never include real client records, real credentials, API secrets, sensitive production endpoints, or production database connections in public/preview frontend bundles.
- Do not claim fake persistence, simulated payments, approval routing, identity enforcement, or generated documents are production capabilities.
- Where useful, make UI forms, navigation, tabs, modals, tables, validation, dashboards and approval flows *interactive* using simulated state.
- Use isolated Vercel previews (or another approved static host); preview access/privacy settings must match client-data sensitivity, even though confidential data must not be bundled.
- Production conversion is a **separate scope and acceptance gate**: define an ASP.NET Core backend, persistence, identity/roles, contractual API boundaries, actual security and transaction requirements, QA, and deployment.
- A prototype should not become production merely because a preview URL works.

## Policy enforcement gates

### Gate A — New-project architecture (before implementation)

For every new Kirjane-controlled project, record:
- project class (mockup, static site, internal system, transactional system, SaaS, worker);
- UI choice and justification;
- whether a backend exists and why;
- if production backend: C# / ASP.NET Core by default, DB selection, service boundaries and host;
- authentication/authorization, sensitive data, transaction/concurrency risks, verification plan;
- any exceptions and their approval record.

Use `PROJECT_STACK_DECISION.md` alongside the project's Forge/Nest architecture record or ADR. A missing backend for a true simulation-only preview is **not** an exception.

### Gate B — PR review (when backend production code is introduced)

Reviewers verify:
- backend implementation and deployment match the accepted project stack ADR;
- use of non-C# production backend has an explicit accepted exception;
- server-side trust, persistence and transaction controls are present where required;
- build, tests, migration and security evidence are attached;
- demos are not misrepresented as production features.

### Gate C — Release/promotion

The Maintainer validates the target deployment profile: **client preview** vs **production**. A frontend-only Vercel preview cannot be promoted as a production transactional service unless the production architecture, functionality, evidence, and release gates have separately passed.

### Gate D — Exception process

Exceptions are permissible for existing accepted architecture, externally imposed client stacks, integration/SDK constraints, demonstrably unsuitable workload characteristics, maintenance cost, or documented delivery risk.

Each exception must contain alternatives considered, measurable reasons, operational/security implications, a responsible approver, an ADR/issue link, scope, and review point. Personal preference or framework popularity alone is insufficient.

## Existing project non-regression rule

**No mass rewrite or implicit migration.** Existing Laravel, Node.js, React, PHP, or other systems retain their current accepted architecture. A migration proposal requires a separate issue/ADR, budget, compatibility plan, rollback strategy, testing, and explicit approval.

## Implementation and audit plan after acceptance

1. Include this profile in the Kirjane project-start/architecture questionnaire and Forge bootstrap for *Kirjane projects only*.
2. Add a stack-decision ADR and PR checklist to **new** product repositories.
3. Where feasible, add project-local CI checks for .NET builds/tests and dependency/security gates. Do not impose C#-specific checks on mockup-only/static repositories.
4. Record and periodically review documented exceptions, project adoption, and scope drift.
5. Track prototype-to-production transitions explicitly; never silently upgrade simulated client workflows.

## Authority and change control

Approval requires the accepted Kirjane technical authority and Forge's candidate → independent review → authorized promotion process when hosted in this repository. This document cannot grant itself acceptance, alter the global Forge engine, or override an existing project's source-of-truth architecture.

Supersession must update this policy ID/version, rationale, and project adoption guidance in a reviewable change.
