---
name: kirion-laravel
description: Use this skill for Laravel 11/12/13 modular monolith architecture, thin HTTP controllers, Form Request validation, domain Actions, API Resources, and Pint/Larastan verification.
---

# Kirion Laravel Specialization (`kirion-laravel`)

## 1. Versioned Official References
- Laravel 11.x / 12.x / 13.x Architecture & Request Lifecycle: `https://laravel.com/docs/lifecycle`
- Laravel Validation & Form Requests: `https://laravel.com/docs/validation#form-request-validation`
- Laravel Pint & Larastan Static Analysis: `https://laravel.com/docs/pint`

## 2. Concrete Workflow
1. Structure applications as a clean modular monolith (`Domain`, `Actions`, `Http/Controllers`, `Http/Requests`, `Policies`) without unnecessary generic repository wrappers.
2. Keep controllers thin: authorize via Policy/Gate, validate via Form Request, delegate state transitions to transactional `Action` classes, and return typed API Resources or views.
3. Enforce idempotency keys on state-changing POST/PUT endpoints (`requisitions`, `approvals`, `receipts`, `settlements`).

## 3. Canonical Example
```php
<?php
declare(strict_types=1);

namespace App\Actions\Procurement;

use Illuminate\Support\Facades\DB;

final readonly class ApprovePurchaseOrderAction {
    public function execute(int $tenantId, int $poId, int $approverId): array {
        return DB::transaction(function () use ($tenantId, $poId, $approverId): array {
            // Row-level lock within tenant boundary
            $po = DB::table('purchase_orders')
                ->where('tenant_id', $tenantId)
                ->where('id', $poId)
                ->lockForUpdate()
                ->first();
            if ($po === null) {
                throw new \RuntimeException('Purchase order not found in tenant scope.');
            }
            if ($po->status !== 'SUBMITTED') {
                throw new \DomainException('Purchase order cannot be approved from current state.');
            }
            DB::table('purchase_orders')->where('id', $poId)->update([
                'status' => 'APPROVED',
                'approved_by' => $approverId,
            ]);
            return ['id' => $poId, 'status' => 'APPROVED'];
        });
    }
}
```

## 4. Validation Commands
```bash
php artisan about
php artisan route:list
php vendor/bin/pint --test
php vendor/bin/phpstan analyse --no-progress
php artisan test
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Business Logic in Controller/Blade):** Embedding multi-table updates directly in a Controller or Blade template without a transaction boundary.
- **Negative Case 2 (Unvalidated Input):** Passing `$request->all()` directly into model creation (`MassAssignment` vulnerability).

## 6. Tests & Qualification Evidence
- Qualified in Benchmark A (Laravel reference procurement and inventory workflow) and Benchmark C blind defect suite.
