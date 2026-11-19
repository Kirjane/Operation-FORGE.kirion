---
name: kirion-laravel-runtime
description: Use this skill for PHP/Laravel runtime execution, after-commit idempotent queue jobs, worker retry/backoff supervision, PDF byte verification, and disposable HTTP runtime testing.
---

# Kirion Laravel Runtime & Queue Specialization (`kirion-laravel-runtime`)

## 1. Versioned Official References
- Laravel Queues & After-Commit Dispatch: `https://laravel.com/docs/queues#transactions-and-queued-jobs`
- PHP Built-in Web Server & CLI Runtime: `https://www.php.net/manual/en/features.commandline.webserver.php`

## 2. Concrete Workflow
1. Dispatch side-effect jobs (audit notifications, PDF generation, supplier webhooks, ledger projections) strictly **after database transaction commit** (`afterCommit()` or transactional outbox table).
2. Make every queued job idempotent using a unique `idempotency_key` (`job_key`) recorded in a durable `processed_jobs` table so retries do not duplicate effects.
3. Verify generated PDF documents by inspecting actual `%PDF-1.` magic bytes, trailer `%%EOF`, byte size, and embedded reference identifiers.
4. Execute real HTTP runtime tests against a live disposable server process (not mocked classes alone).

## 3. Canonical Example
```php
<?php
declare(strict_types=1);

// Transactional outbox + after-commit worker execution
$pdo->beginTransaction();
try {
    $pdo->prepare('UPDATE purchase_orders SET status = ? WHERE id = ?')->execute(['APPROVED', $poId]);
    $pdo->prepare('INSERT INTO outbox_jobs (job_key, payload_json, status) VALUES (?, ?, ?)')
        ->execute(["po-approved-{$poId}", json_encode(['po_id' => $poId]), 'PENDING']);
    $pdo->commit();
} catch (\Throwable $e) {
    $pdo->rollBack();
    throw $e;
}
```

## 4. Validation Commands
```bash
php -d extension=pdo_sqlite -d extension=sqlite3 tests/run_tests.php
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Queue Dispatch Before Commit):** Dispatching a worker job inside an uncommitted transaction so the worker reads missing/uncommitted state or executes even when the transaction rolls back (`LARAVEL-QUEUE-BEFORE-COMMIT`).
- **Negative Case 2 (Non-Idempotent Job Retry):** Retrying a failed job that increments stock or balance twice on the second attempt.

## 6. Tests & Qualification Evidence
- Verified in Benchmark A (after-commit queue worker retry idempotency + PDF byte inspection) and Benchmark C (`LARAVEL-QUEUE-BEFORE-COMMIT`, `BOTH-DUPLICATE-POSTING`).
