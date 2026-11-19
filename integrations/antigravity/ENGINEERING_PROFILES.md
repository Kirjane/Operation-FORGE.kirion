# Engineering specialization contracts (proposed)

C#/ASP.NET Core remains preferred for new enterprise/high-integrity systems; PHP/Laravel is a first-class independently qualified production ecosystem, not a fallback. Choose based on domain, hosting, team, workload, deployment, data integrity and maintenance. Existing contracts prevail; no unsolicited rewrite. PR #10 is a separate unmerged stack policy proposal and must be reconciled before organization-wide adoption. Greenfield candidate defaults .NET 10 LTS, PHP 8.5 and Laravel 13 contingent on F00 verification of support lifecycle, hosting and package compatibility. Pin runtimes and lockfiles; use project versions in brownfield. PostgreSQL/MySQL/MariaDB for server systems, SQLite for justified embedded/offline, Redis where measured. No inferred client rules.

## Laravel/PHP
Reference modular monolith; ordinary Laravel conventions for simple applications. HTTP controllers orchestrate, Form Requests validate, policies/gates enforce object-level backend authorization, resources shape API, Actions/domain/services encapsulate business transitions, Eloquent handles persistence deliberately. Jobs idempotent with retry/backoff/timeout/failure visibility and dispatch after commit when needed; scheduler overlap prevention; event/outbox durability when required. Native Blade/Livewire or Inertia/React according to contract. Use PHP typed parameters/properties/returns, strict types in compatible new domain files, enums/immutable values where useful. Avoid generic repositories and architecture layers without a concrete need.
- Explicit mass assignment, escaped output, bound SQL, CSRF/session configuration, Sanctum/token lifecycle if actual API contract, rate limiting, file content/type/size and authorization, private storage, safe redirects, no debug in production. Verify tenant and ownership denial independently across routes, queues, cached resources and Livewire actions.
- Transactions, constraints/indexes, row locks/optimistic concurrency appropriate to engine, deterministic order and bounded retry for deadlocks, exact money (integer minor units/decimal), no unsafe floating-point money; duplicate submission and state-transition protection. Persist audit history and totals; flush caches and dispatch side effects only when safe.
- Detect N+1 and unbounded fetch, pagination, query plans against representative fixture; queues and workers require actual runtime, not fakes alone. Migrations fresh and version-to-version with data-preservation checks on representative production DB engine, not SQLite substitution for PostgreSQL/MySQL-specific semantics. Plan recovery, backups verified before production separately authorized.
- Runtime: PHP-FPM/OPcache or approved host, health checks, production config/cache, queue process supervision, scheduler, dependency support, no sensitive data in logs.

Proposed validation commands (resolve executable and package versions from repo; do not add tools/deps without authorization):
    php --version
    composer --version
    composer validate --strict
    composer install --no-interaction --prefer-dist
    composer check-platform-reqs
    composer audit
    php artisan about
    php artisan route:list
    php vendor/bin/pint --test
    php vendor/bin/phpstan analyse --no-progress
    php artisan test
Use Pest/PHPUnit and compatible Larastan/PHPStan; record absent checks as NOT_RUN with blocker when required. Review Composer scripts before execution, isolate install, require lockfile unchanged; no composer update unless authorized. Run npm ci/build and Playwright only where applicable. Start disposable app and test real HTTP, login roles, cross-tenant denial, persistence, DB upgrade/rollback/recovery, concurrent/replayed requests, job failure/retry and PDF bytes where relevant. Compare pre/post persisted invariants. Use Infection mutation testing on critical logic when feasible.

## ASP.NET Core/C#
Reference projects Domain/Application/Infrastructure/Api/Web only when justified; smaller systems conventional MVC/Razor/minimal APIs. Nullable reference types, explicit async cancellation for I/O, service lifetimes and EF DbContext confinement, safe concurrency, exact decimal or integer money, transaction and idempotency boundaries, Problem Details, policy and resource authorization, structured redacted logs, UTC and domain timezone, bounded background services and graceful cancellation. EF Core tracking/translation/index/query plan inspection, constraints and concurrency tokens; no in-memory DB substitute for engine-specific semantics. Review sync-over-async, fire-and-forget, lifetime violations, race conditions, unsafe serialization, resource leaks, excessive allocations and unbounded retrieval.
    dotnet --info
    dotnet restore --locked-mode
    dotnet build --no-restore -c Release
    dotnet format --verify-no-changes --no-restore
    dotnet test --no-build -c Release --logger trx --results-directory artifacts/test-results
    dotnet list package --vulnerable --include-transitive
Use locked restore only where repo lockfiles configured; otherwise plan reproducible pinned strategy without secretly modifying lockfiles. xUnit or approved equivalent, WebApplicationFactory/actual HTTP and real disposable DB, Stryker.NET where supported; distinguish build from actual runtime.

## Salryn/high-integrity profile
Test ledger reconciliation, stock movements, AP/AR, lifecycle dates, supplier/customer settlement, reversal and refund, atomicity/rollback, repeat/concurrent request, offline SQLite WAL/locking, retained schema upgrade, license and non-elevated restart, installer identity, document/receipt bytes. Do not reset client data or licensing; installed-device QA is NOT_RUN when absent. Financial policy ambiguity stops affected mutation.

## Frontend profile
React/TypeScript, Blade/Livewire or Razor by contract; Vite/React isolated Vercel previews only when authorized and simulated data clearly labeled. No mock as live evidence, no fake login in deliberately static showcase, no production secrets. Test actual browser flows, accessibility WCAG 2.2 AA where applicable, keyboard and focus, errors/loading/empty/denied, reduced motion, mobile nav, no horizontal overflow. Viewports 1440x900, 1280x720, 1024x768, 768x1024, 390x844, 320x568. Use screenshots, axe and Playwright; visual composition, asset license, typography, animation and information hierarchy judged against user-approved design. Performance budgets baseline/target recorded with measured environment, not arbitrary claims. New corporate web target LCP <=2.5s, INP <=200ms, CLS <=0.1 when applicable and measured in appropriate context.

## Proposed specialization packs
Extend existing 16 candidate skills only after acceptance/reconciliation. Sixteen additions: kirion-php, kirion-laravel, kirion-eloquent, kirion-laravel-security, kirion-laravel-runtime, kirion-csharp, kirion-aspnet, kirion-efcore, kirion-concurrency, kirion-database, kirion-api, kirion-observability, kirion-performance, kirion-design-engineering, kirion-test-engineering, kirion-devsecops. Each includes versioned official references, concrete workflow, examples, commands, misuse/negative cases, tests and qualification evidence. Load progressively; no indiscriminate all-skill context. Candidate 32 total, not globally installed.
