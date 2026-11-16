---
id: "forge.skill.kirion-architecture"
source_repo: "Kirch-Nairu/Operation-FORGE.kirion"
source_ref: "eabbfbabdbb22d8684fb2c3d80767b8547852b83"
source_path: ".agents/skills/kirion-architecture/SKILL.md"
source_status: "CANDIDATE"
source_blob_sha: "e47da0edcd885e83925c63e3f8f1252eb1748b33"
tags: [forge, arsenal, candidate]
---

# Kirion Architecture

**CANDIDATE / OPT_IN_ONLY.** Full canonical skill text at pinned PR #7 SHA. Reading this is not authority or automatic host installation.

[Exact SKILL.md](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/blob/eabbfbabdbb22d8684fb2c3d80767b8547852b83/.agents/skills/kirion-architecture/SKILL.md) · [[00 Skill Index]] · [[Specialist Selection]] · [[00 HOME]]

## Canonical contract

# Minimal architecture
Start from actual user outcome and current repo. Trace the vertical path **only through existing or explicitly approved layers** (UI, API, domain, storage, auth and runtime as applicable), with relevant boundaries and protected invariants. An approved static/frontend-only showcase does not require a new backend, authentication, persistence or production workflow engine. Trace actual upstream and downstream consumers before altering interfaces.
Reuse existing code before adding abstractions, dependencies, microservices or second frameworks. A new component must solve a demonstrated problem and define acceptance/rollback. Don't infer business approval from screenshots or one historical note.
Return a small decision record: verified starting source, approved contract, chosen simple design, affected interfaces/files, alternatives rejected, explicit unknowns and testable conditions. Architecture is not implementation or release authority.
