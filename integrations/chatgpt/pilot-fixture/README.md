# R5 synthetic PHP inventory debit pilot

Offline only; deliberately contains a seeded negative-debit defect in `src/Stock.php`.

`php tests/public.php` passes before repair. `php oracles/hidden.php` fails before repair and passes after the correct repair.

The hidden oracle is available ONLY to the trusted gate runner, not to Jane/Nox model tools. No client code, external credentials, financial/production data, API calls, or remote pushes. Tests and hidden oracles are immutably frozen across patch proposals. This directory is a fixture template copied into a disposable local Git repo by R5 CI tests; it is not a live connected repository or genuine provider runtime.
