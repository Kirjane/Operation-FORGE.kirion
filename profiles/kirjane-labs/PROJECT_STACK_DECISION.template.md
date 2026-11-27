# Kirjane Labs — Project Stack Decision (template)

**Project:** [name]  
**Issue / ADR:** [link]  
**Project state:** GREENFIELD / EXISTING / RECOVERY  
**Class:** MOCKUP / STATIC / INTERNAL / TRANSACTIONAL / SAAS / WORKER  
**Owner / reviewer:** [identity]  
**Date / status:** [date] — PROPOSED / ACCEPTED / EXCEPTION

## Scope

Describe the real user workflows and whether this is **frontend-only simulation** or a **production system**.

## Technology decision

| Layer | Selected | Reason |
| --- | --- | --- |
| UI | React + Vite / Razor Pages / Blazor / static / other | |
| Backend | None (simulation) / C# + ASP.NET Core / .NET Worker / exception | |
| Storage | None / seeded mock data / PostgreSQL / SQLite / exception | |
| Hosting | Vercel preview / controlled production host | |
| Identity / roles | Mocked for demo / implemented server-side | |
| API contract | None / defined contract | |

## Risk and control review

- [ ] Mockups use fictional data and communicate simulated behavior.
- [ ] Production rules, authorization, secrets and monetary operations are server-owned.
- [ ] DB constraints, transactions, concurrency and idempotency considered when applicable.
- [ ] Observability, backup/recovery and deployment ownership specified when applicable.
- [ ] Build/test/security evidence and release gates defined.
- [ ] Existing architecture preserved or migration separately authorized.

## Exception (if relevant)

**Baseline deviation:** [detail / none]  
**Alternatives and evidence:** [detail]  
**Security / reliability / maintenance cost:** [detail]  
**Approval reference:** [issue / ADR / decision link]  
**Reassessment trigger:** [date / condition]

## Release boundary

**Delivery class:** CLIENT PREVIEW / PRODUCTION  
**What the demonstration actually does:** [explicit]  
**What requires real backend integration before launch:** [explicit]  
**Acceptance authority:** [identity / evidence link]

> This record is a proposal until the authorized reviewer explicitly accepts it. A successful Vercel preview is not production acceptance.
