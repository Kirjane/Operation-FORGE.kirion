---
name: kirion-eloquent
description: Use this skill for Eloquent and PDO relational persistence, N+1 prevention, row-level locking, optimistic concurrency, migrations, and data-preservation checks.
---

# Kirion Eloquent & Relational Persistence (`kirion-eloquent`)

## 1. Versioned Official References
- Laravel Eloquent ORM & Query Builder: `https://laravel.com/docs/eloquent`
- Laravel Database Migrations & Transactions: `https://laravel.com/docs/migrations`
- PHP PDO Prepared Statements & Transactions: `https://www.php.net/manual/en/book.pdo.php`

## 2. Concrete Workflow
1. Explicitly whitelist `$fillable` attributes on every model; never set `$guarded = []` on sensitive or tenant-owned entities.
2. Wrap multi-row writes (requisition approval, partial stock receipt, ledger posting, audit trail) in `DB::transaction()` (or `PDO::beginTransaction()`) with deterministic lock ordering.
3. Prevent N+1 queries via eager loading (`with(...)`), explicit joins, and bounded pagination; verify query counts in automated tests.
4. Test both fresh schema creation and version-to-version upgrade migrations preserving existing seeded rows.

## 3. Canonical Example
```php
<?php
declare(strict_types=1);

// Parameterized query with explicit tenant scoping and bounded limit
$stmt = $pdo->prepare(
    'SELECT id, sku, quantity_on_hand, reserved_minor
     FROM inventory_items
     WHERE tenant_id = :tenant_id AND warehouse_id = :warehouse_id
     ORDER BY id ASC
     LIMIT :limit OFFSET :offset'
);
$stmt->bindValue(':tenant_id', $tenantId, \PDO::PARAM_INT);
$stmt->bindValue(':warehouse_id', $warehouseId, \PDO::PARAM_INT);
$stmt->bindValue(':limit', 50, \PDO::PARAM_INT);
$stmt->bindValue(':offset', 0, \PDO::PARAM_INT);
$stmt->execute();
```

## 4. Validation Commands
```bash
php artisan migrate --pretend
php artisan test --filter=MigrationPreservationTest
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Raw String Interpolation SQLi):** `DB::select("SELECT * FROM items WHERE sku = '$sku'")` → `P0` SQL injection defect.
- **Negative Case 2 (Unbounded Collection Fetch):** `PurchaseOrder::all()->filter(...)` on large tables instead of indexed SQL filtering and pagination.
- **Negative Case 3 (Partial Receipt Without Transaction):** Incrementing `inventory_items` before validating excess quantity against `ordered_qty`, leaving partial state on exception.

## 6. Tests & Qualification Evidence
- Verified in Benchmark A (partial receipt reconciliation, migration upgrade, rollback on injected failure) and Benchmark C (`PHP-SQL-INJECTION`, `LARAVEL-N-PLUS-1`, `BOTH-MISSING-TRANSACTION`).
