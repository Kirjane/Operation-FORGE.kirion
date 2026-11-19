# ADR-0005: PHP/C# Stack Version Selection and Progressive Skill Packaging

- **Status:** ACCEPTED FOR R1 FACTORY CANDIDATE
- **Mission:** `F00` (`FORGE-ANTIGRAVITY-F00-FOUNDATION-R1`)
- **Date:** `2026-11-19`

## Context
1. `ENGINEERING_PROFILES.md` proposed greenfield defaults of `.NET 10 LTS`, `PHP 8.5`, and `Laravel 13` contingent on F00 host verification, while requiring brownfield projects to use pinned repository versions.
2. F00 host probes observed:
   - `.NET SDK 10.0.401` with `Microsoft.AspNetCore.App 10.0.12` (`.NET 10.0` is active and verified on host).
   - `PHP 8.4.25 (cli) (ZTS Visual C++ 2022 x64)` and `Composer 2.10.3` with `pdo_pgsql` built-in and `pdo_sqlite`/`sqlite3` dynamically loadable from `ext/` (`PHP 8.4.25` is active on host; `PHP 8.5` is not installed on host).
3. `PR #7` (`proposal/kirion-skill-arsenal-multihost-v0-2`) owns `.agents/skills/` with exactly 16 skills enforced by `arsenal/tests/test_skill_manifest.py` and `obsidian/scripts/build_vault.py --check`.

## Decision
1. **Verified Stack Profiles (`integrations/antigravity/profiles/`):**
   - **C# / ASP.NET Core Profile (`csharp_aspnet.json`):** Targets `.NET 10.0` (`net10.0`, SDK `10.0.401`) by default on this host (with `net8.0` supported for brownfield projects), enforcing `<Nullable>enable</Nullable>`, explicit `CancellationToken` propagation, exact `decimal` / integer minor-unit money, bounded `DbContext` lifetimes, transactional idempotency, and real HTTP + database integration tests.
   - **PHP / Laravel Profile (`php_laravel.json`):** Targets `PHP >= 8.4` (`8.4.25` verified on host; `8.5` compatible) and `Laravel 11/12/13` conventions (modular monolith, `declare(strict_types=1);`, Form Request validation, object-level Policy/Gate authorization, explicit mass-assignment allowlists, integer minor-unit money, transactional row locking, after-commit idempotent queue jobs, and real HTTP + PDO database tests). Automatically passes `-d extension_dir=<php_ext_dir> -d extension=pdo_sqlite -d extension=sqlite3` when running disposable SQLite tests on Windows hosts where `php.ini` has not enabled `pdo_sqlite` globally.
2. **Progressive 16+16 Skill Packaging (`integrations/antigravity/plugins/kirion-forge/skills/`):**
   - The 16 base skills in `.agents/skills/` remain untouched so `PR #7` and `PR #12` validators pass without modification.
   - The 16 new specialization skills (`kirion-php`, `kirion-laravel`, `kirion-eloquent`, `kirion-laravel-security`, `kirion-laravel-runtime`, `kirion-csharp`, `kirion-aspnet`, `kirion-efcore`, `kirion-concurrency`, `kirion-database`, `kirion-api`, `kirion-observability`, `kirion-performance`, `kirion-design-engineering`, `kirion-test-engineering`, `kirion-devsecops`) are packaged inside `integrations/antigravity/plugins/kirion-forge/skills/<skill_name>/SKILL.md`.
   - When the `kirion-forge` plugin is discovered via `.agents/plugins.json`, Antigravity natively ingests the 16 plugin specialization skills alongside the 16 workspace skills (32 total skills), and `factory/dispatcher.py` enforces progressive loading (selecting `kirion-core` + `kirion-dispatch` + at most 1–4 task-relevant specialization skills per worker invocation).

## Consequences
- Both C# (`.NET 10.0.401`) and PHP (`8.4.25`) execute real build, static analysis, database migration, concurrency, negative authorization, and HTTP runtime tests on this host.
- Zero regression on `arsenal/tests/test_skill_manifest.py` and `obsidian/scripts/build_vault.py --check`.
