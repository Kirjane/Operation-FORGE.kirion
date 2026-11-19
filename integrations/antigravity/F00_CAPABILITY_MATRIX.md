# F00 — Foundation Reconnaissance, Host Capability Matrix, and Source Reconciliation

**Mission ID:** `FORGE-ANTIGRAVITY-F00-FOUNDATION-R1`  
**Program Authority:** [Issue #13](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/issues/13) · [PR #14](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/pull/14)  
**Active Role:** Maintainer / Principal Factory Architect  
**Authenticated Remote Actor:** `Kirch-Nairu` (GitHub User ID `291564617`, verified via `gh api user`)  
**Starting Candidate SHA:** `a864b88bda5f26c44709c9239dc73ae63abc78ad` (`feat/antigravity-software-factory-r1`)  
**Observed Date (UTC):** `2026-11-19`

---

## 1. Source Custody and Dependency Reconciliation

All repository references were verified directly against live Git and GitHub (`Kirch-Nairu/Operation-FORGE.kirion`):

| Reference | Branch / PR | Observed Exact 40-char SHA | State & Disposition |
| --- | --- | --- | --- |
| **Genesis Authority** | `main` root | `a1f7c0414b06729256cd4a9664bb723aa3eaa1cf` | Immutable Genesis anchor ([AGENTS.md](../../AGENTS.md)). |
| **Accepted Forge Main** | `main` | `ac7285d7cd866b4728c28d64a7c145a6bc43f812` | Current accepted authority (`NEST-2 — Governed (Genesis)`). |
| **Skill Arsenal v0.2** | `proposal/kirion-skill-arsenal-multihost-v0-2` ([PR #7](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/pull/7)) | `eabbfbabdbb22d8684fb2c3d80767b8547852b83` | Open upstream candidate (16 core skills under `.agents/skills/`). Preserved unmodified; not auto-merged. |
| **Kirjane C# Stack Standard** | `policy/kirjane-csharp-backend-standard-r1` ([PR #10](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/pull/10)) | `b0355f326bd96bcb29db40e3e358cc8a7bac058e` | Open draft policy proposal off `main`. Reconciled as opt-in profile; not merged by this program. |
| **Obsidian Knowledge Vault** | `feat/forge-obsidian-vault-r2` ([PR #12](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/pull/12)) | `ffffa7e16137ce191d74be0fadd0fe18c2eae2f9` | Open draft parent branch of `feat/antigravity-software-factory-r1`. Derived reference only; vault not regenerated. |
| **Factory Planning Baseline** | `feat/antigravity-software-factory-r1` ([PR #14](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/pull/14)) | `a864b88bda5f26c44709c9239dc73ae63abc78ad` | Exact starting candidate SHA verified before F00 execution. |

### Promotion and Review Order
1. `PR #7` (Skill Arsenal v0.2) → independent acceptance → non-force promotion to `main`.
2. `PR #12` (Obsidian Vault R2) → rebase/verify against accepted `PR #7` → independent acceptance → promotion.
3. `PR #10` (Kirjane Stack Standard) → independent policy acceptance → opt-in profile adoption per project.
4. `PR #14` (`feat/antigravity-software-factory-r1`) → F00–F17 implementation, qualification (Benchmarks A–E), fresh-context `Antigravity-Nox` review at frozen SHA, and separate non-author Engineer acceptance before promotion.

---

## 2. Host Capability Matrix (Antigravity 2.0 Windows Host)

Probed on the live authorized Antigravity 2.0 host (`Microsoft Windows NT 10.0.26300.0`, PowerShell `7.6.6`, Language Server Connect RPC endpoint `ANTIGRAVITY_LS_ADDRESS`):

| Capability | Status | Evidence Level | Observed Details & Constraints |
| --- | --- | --- | --- |
| **Host OS & Shell** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | Windows NT `10.0.26300.0` (x64), PowerShell `7.6.6`, `cmd.exe` available for hook execution. |
| **Antigravity Language Server RPC** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | Active on local Connect endpoint (`/healthz` returned `{"status":"ok"}`); `GetAllPlugins` RPC verified with CSRF token. |
| **Model Entitlement & Quotas** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | Verified via `swarm{action:"models", all:true}`: `gemini-4-argon-high/medium/low` (36% remaining), `gemini-3.8-flash-high/medium/low` (100%), `gemini-4-hydrogen-*` (100%), `gemini-4-neon-*` (100%), `claude-opus-5-5-*` (100%), `claude-sonnet-5-5-*` (100%). |
| **Native Plugin Discovery (`.agents/plugins/`)** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | `GetAllPlugins` discovers `<workspace>/.agents/plugins/<name>/plugin.json` along with bundled `skills/*/SKILL.md`, `agents/*.md`, `rules/AGENTS.md`, and root `hooks.json`. |
| **Declarative Plugin Config (`.agents/plugins.json`)** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | `GetAllPlugins` discovers plugins declared in `<workspace>/.agents/plugins.json` (`{"entries": [{"path": "integrations/antigravity/plugins"}]}`). |
| **Language Server Mutation RPCs from Subprocess** | `DOCUMENTED` / `RESTRICTED` | `E1` (`DIRECTLY_OBSERVED`) | `JetboxWriteState`, `DeletePlugin`, and `InstallCustomization` are blocked from `run_command` subprocesses by host security policy; workspace discovery via `.agents/plugins.json` requires no global config mutation. |
| **Native Dynamic Workflows (`run_workflow`)** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | Executed `run_workflow` with `agent(..., schema=..., role="Antigravity-Nox-Smoke", type_name="research")`; isolated agent conversation `b5ff0f29-5fcc-4a6d-92b6-7ce9485a757e` returned schema-validated JSON `{"context_isolated": true, "role": "Antigravity-Nox-Smoke"}`. |
| **Subagent Delegation (`invoke_subagent`)** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | Supports `self`, `research` (read-only sandbox, no network), `browser`, and `define_subagent` custom personas with `Workspace` modes `inherit`, `branch`, `share`. |
| **Lifecycle Hooks (`hooks.json`)** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | Loaded strictly from plugin root (`<plugin_dir>/hooks.json`). Supports `SessionStart`, `PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`, `Stop` via synchronous `type: "command"` (`cmd /c` on Windows) with camelCase JSON stdin/stdout. |
| **Antigravity CLI (`agy`)** | `UNAVAILABLE` | `E5` (`DIRECTLY_OBSERVED`) | `agy` binary is not on `PATH` on this host (`MISSING agy`). Factory CLI operations must run through deterministic Python entrypoints (`python -m integrations.antigravity.factory.cli`). |
| **Public Python SDK (`google-antigravity`)** | `UNAVAILABLE` | `E5` (`DIRECTLY_OBSERVED`) | `pip show google-antigravity` returned `Package(s) not found`. Orchestration uses deterministic stdlib Python + native `run_workflow` / `invoke_subagent` adapters. |
| **Python Runtime & SQLite WAL** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | Python `3.13.5` (`C:\Users\arane\AppData\Local\Programs\Python\Python313\python.exe`), `sqlite3` `3.49.1` with verified `PRAGMA journal_mode=WAL`. |
| **.NET / C# Toolchain** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | `.NET SDK 10.0.401`; runtimes `Microsoft.AspNetCore.App` & `Microsoft.NETCore.App` `10.0.12`, `8.0.19`, `6.0.25`. |
| **PHP & Composer Toolchain** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | `PHP 8.4.25 (cli) (ZTS Visual C++ 2022 x64)` + `Composer 2.10.3`. Built-in PDO drivers: `pdo_pgsql`; `pdo_sqlite` and `sqlite3` DLLs present in `ext/` and dynamically loadable via `-d extension_dir=... -d extension=pdo_sqlite -d extension=sqlite3`. PHP 8.5 is not installed on this host. |
| **Node.js & npm Toolchain** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | `Node.js v24.22.1`, `npm 11.10.1`. |
| **Git & Worktree Isolation** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | `git version 2.55.0.windows.3`. Parallel `git worktree add` verified in disposable repo. **Critical Windows finding:** global `core.autocrlf=true` converts LF to CRLF on checkout, breaking `SHARED_DOCS.sha256` unless `git config core.autocrlf false` is enforced. |
| **GitHub Broker Identity (`gh`)** | `OBSERVED` | `E5` (`DIRECTLY_OBSERVED`) | `gh version 2.101.0` authenticated as `Kirch-Nairu` (ID `291564617`, `Kirch Ivan Balite`), protocol `https`, scopes `gist, read:org, repo, workflow`. |
| **PostgreSQL / MySQL Live Server Daemon** | `UNAVAILABLE` / `NOT_RUN` | `E5` (`DIRECTLY_OBSERVED`) | Local PostgreSQL/MySQL server processes are not running on the disposable host environment; SQLite WAL (`3.49.1`) is available and verified for local transactional reference persistence, while engine-specific PostgreSQL/MySQL migration semantics are explicitly marked `NOT_RUN` when a live server daemon is absent. |

---

## 3. F00 Disposable Smoke Test Proof

Executed in a disposable repository outside the project tree (`f00_probe.py`):

- **Smoke Results Artifact SHA-256:** `adcad145b924ceba3f177d0c65c0b60629b18b79c815e58056877281e9ad25c7`
- **Disposable Repo Base SHA:** `e9fb74be63bbca83aa6b2ebd40215df7d90f32a6`
- **Plugin Discovery (`.agents/plugins/kirion-forge-smoke`):** Discovered (`count=1`, `isGlobal=false`, `skills=["smoke-skill"]`, `agents=["smoke-agent"]`, `rules_count=1`, `hooks_loaded=true`).
- **Plugin Discovery (`.agents/plugins.json` → `integrations/antigravity/plugins/kirion-forge-smoke`):** Discovered (`count=1`, `skills=["smoke-skill"]`, `hooks_loaded=true`).
- **Plugin Clean Uninstall:** Removed `.agents/` and `integrations/` in disposable repo; `GetAllPlugins` confirmed `count=0` with zero global config mutation.
- **Parallel Worktree Isolation:** Created `wt_lane_a` (`smoke/lane-a`, commit `824f12a193f3e97aa16967bd517c10385eb96113`) and `wt_lane_b` (`smoke/lane-b`, commit `f0b62ff3c8f9bea26d7f2324a71f98c838156dc4`); verified `isolated=true` (zero file cross-contamination) and clean removal via `git worktree remove`.
- **Fail-Closed Hook Verification:** Tested `PreToolUse` handler via `cmd /c python hook_guard.py`:
  - Safe command (`pytest`) → `{"decision": "allow"}`
  - Forbidden command (`git push --force origin main`) → `{"decision": "deny", "reason": "Forbidden destructive command denied by Forge hook"}`
  - Malformed JSON on stdin (`{not-valid-json`) → `{"decision": "deny", "reason": "Fail-closed hook parse error: ..."}`
- **Isolated Agent Context Proof:** Executed native `run_workflow` step spawning `research` agent `Antigravity-Nox-Smoke` in isolated conversation `b5ff0f29-5fcc-4a6d-92b6-7ce9485a757e` with strict JSON Schema output `{"context_isolated": true, "role": "Antigravity-Nox-Smoke"}`.

---

## 4. Canonical Repository & Entity Validation Baseline

1. **Initial Windows Checkout (`core.autocrlf=true`):**
   - `tools/forge_check.py shared` and `tools/entity_check.py` failed on `SYSTEM_BOUNDARY.md` and `EVIDENCE_CROSSWALK.md` SHA-256 pins because Windows Git converted LF line endings to CRLF.
2. **Canonical LF Checkout (`git config core.autocrlf false && git reset --hard HEAD`):**
   - `python tools/forge_check.py repo` → `FORGE REPO: PASS (checked_files=17 required_dirs=16)`
   - `python tools/forge_check.py schemas` → `FORGE SCHEMAS: PASS (6 schema files parse and have core structure)`
   - `python tools/forge_check.py links` → `FORGE LINKS: PASS (203 internal path references checked)`
   - `python tools/forge_check.py shared` → `FORGE SHARED: PASS`
   - `python tools/forge_check.py nest` → `NEST: PASS (CLAIMED_MATURITY: NEST-2)`
   - `python tools/entity_check.py` → `ENTITY VALIDATION: PASS` (including Second Brain graph 1045 notes / 0 errors, 35/35 harness tests, 6/6 Notion semantic provider tests, and MCP syntax check)
   - `python -m unittest discover -s arsenal/tests -v` → `Ran 10 tests ... OK`
   - `python -m unittest discover -s obsidian/tests -v` → `Ran 4 tests ... OK`
   - `python obsidian/scripts/build_vault.py --repo-root . --check` → `{"result": "PASS", "notes": 57, "skills": 16, "wiki_links": 287, "mode": "git-verified"}`

---

## 5. Stack Policy Reconciliation (PR #10 vs Factory Engineering Profiles)

- **PR #10 (`b0355f326bd96bcb29db40e3e358cc8a7bac058e`)** defines `KIRJANE-ENG-STACK-001` as an **opt-in Kirjane Labs organization profile** where C# / ASP.NET Core is the default production backend and React + Vite on Vercel is bounded to isolated simulation/demo previews unless backed by a real server authority.
- **Factory Reconciliation:**
  1. C# / ASP.NET Core (`.NET 10.0` observed on host: SDK `10.0.401`, runtime `10.0.12`) is the default enterprise/high-integrity backend where `KIRJANE-ENG-STACK-001` is adopted.
  2. PHP / Laravel (`PHP 8.4.25` + `Composer 2.10.3` observed on host; compatible with PHP 8.4/8.5 and Laravel 11/12/13 per project lockfile) is a **first-class, independently qualified production stack** with equal gate rigor, security, transaction, queue, and runtime verification.
  3. **No unsolicited framework rewrites** and **no automatic merge of PR #10**. Existing project contracts prevail.

---

## 6. Architecture Decision Records (ADRs)

- [ADR-0001: Native Antigravity vs Deterministic Python Orchestration](adr/ADR-0001-orchestration-boundary.md)
- [ADR-0002: Deny-by-Default Policy Enforcement, Worktree Sandbox, and Fail-Closed Hooks](adr/ADR-0002-policy-isolation-and-hooks.md)
- [ADR-0003: Nairu Delivery Broker and Verified Actor Gateway](adr/ADR-0003-nairu-delivery-broker.md)
- [ADR-0004: SQLite WAL Durable Event Journal and Crash Recovery](adr/ADR-0004-durable-journal-and-recovery.md)
- [ADR-0005: PHP/C# Stack Version Selection and Progressive Skill Packaging](adr/ADR-0005-stack-versions-and-skill-packaging.md)

---

## 7. Narrowed F01 and F06 Implementation Scope

- **F01 (Native Plugin Packaging):**
  - Package native Antigravity plugin at `integrations/antigravity/plugins/kirion-forge/` containing `plugin.json` (strictly conforming to verified host schema: `name`, `displayName`, `description`, `version`, `author`, `repository`, `logo`, `suggestedPrompts`), `rules/AGENTS.md`, root `hooks.json`, `hooks/forge_guard.py`, `assets/logo.svg`, and `README.md`.
  - Provide workspace discovery registration via `.agents/plugins.json` and a deterministic manifest/discovery validator (`integrations/antigravity/factory/plugin_packaging.py`) without mutating `~/.gemini/config/`.
- **F06 (Mission and Authority Contracts):**
  - Author JSON Schema Draft 2020-12 contracts under `integrations/antigravity/schemas/` (`mission-packet.schema.json`, `writer-result.schema.json`, `nox-result.schema.json`, `evidence-envelope.schema.json`, `journal-event.schema.json`, `recovery-capsule.schema.json`).
  - Implement `integrations/antigravity/factory/authority.py` and `integrations/antigravity/factory/policy.py` enforcing exact 40-char SHA pins, untrusted input validation, deny-by-default operation guards, and canonical lifecycle state transitions (`PLANNED` → `AUTHORIZED` → `ACTIVE` → `READY` → `UNDER_REVIEW` → `ACCEPTED`/`REWORK`/`REJECTED`/`QUARANTINED` → `INTEGRATED` → `PROMOTED` → `OBSERVED`, plus `BLOCKED`).
