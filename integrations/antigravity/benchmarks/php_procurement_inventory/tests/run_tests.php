<?php
declare(strict_types=1);

require_once __DIR__ . '/../src/ProcurementEngine.php';

use Kirion\BenchmarkA\DomainHttpException;
use Kirion\BenchmarkA\ProcurementEngine;

$assertionsExecuted = 0;

function assertSame(mixed $expected, mixed $actual, string $label): void
{
    global $assertionsExecuted;
    if ($expected !== $actual) {
        throw new RuntimeException("ASSERTION FAILED [{$label}]: expected " . var_export($expected, true) . ", got " . var_export($actual, true));
    }
    $assertionsExecuted++;
}

function assertThrowsStatus(callable $fn, int $expectedStatus, string $label): void
{
    try {
        $fn();
    } catch (DomainHttpException $e) {
        assertSame($expectedStatus, $e->httpStatus, $label);
        return;
    }
    throw new RuntimeException("ASSERTION FAILED [{$label}]: expected HTTP {$expectedStatus}, but no exception was thrown.");
}

$dbFile = sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'kirion_bench_a_' . bin2hex(random_bytes(6)) . '.sqlite';
if (file_exists($dbFile)) {
    @unlink($dbFile);
}

$reqA = ['tenant_id' => 1, 'user_id' => 101, 'role' => 'requester'];
$appA = ['tenant_id' => 1, 'user_id' => 102, 'role' => 'approver'];
$selfAppA = ['tenant_id' => 1, 'user_id' => 101, 'role' => 'approver'];
$clerkA = ['tenant_id' => 1, 'user_id' => 103, 'role' => 'stock_clerk'];
$auditA = ['tenant_id' => 1, 'user_id' => 104, 'role' => 'auditor'];

$reqB = ['tenant_id' => 2, 'user_id' => 201, 'role' => 'requester'];
$appB = ['tenant_id' => 2, 'user_id' => 202, 'role' => 'approver'];
$auditB = ['tenant_id' => 2, 'user_id' => 204, 'role' => 'auditor'];

// 1. Seed on Schema V1, then migrate V1 -> V2 and verify data preservation
$engine = new ProcurementEngine($dbFile);
$engine->initSchemaV1();
assertSame(1, $engine->getSchemaVersion(), 'schema v1 init');
assertThrowsStatus(fn() => $engine->createSupplier(['tenant_id' => 0, 'user_id' => 101, 'role' => 'requester'], 'SUP-ZERO', 'Zero Tenant'), 403, 'Zero tenant_id cannot create supplier');
assertThrowsStatus(fn() => $engine->createSupplier($reqA, '   ', ''), 422, 'Blank supplier code/name rejected with 422');
$supA = $engine->createSupplier($reqA, 'SUP-A1', 'Apex Industrial Supplies');
$supB = $engine->createSupplier($reqB, 'SUP-B1', 'Beacon Logistics');

$newVer = $engine->migrateV1ToV2();
assertSame(2, $newVer, 'schema v1->v2 upgrade');

// 2. Create PO in Tenant A and Tenant B (verify mass assignment ignores injected status/tenant_id)
$poA = $engine->createAndSubmitPurchaseOrder($reqA, [
    'supplier_id' => $supA['id'],
    'po_number' => 'PO-2026-0001',
    'status' => 'APPROVED', // should be ignored (mass assignment defense)
    'tenant_id' => 999,     // should be ignored
    'items' => [
        ['sku' => 'VALVE-10MM', 'ordered_qty' => 10, 'unit_price_minor' => 25000],
        ['sku' => 'GAUGE-PRO', 'ordered_qty' => 4, 'unit_price_minor' => 125000],
    ],
]);
assertSame('SUBMITTED', $poA['status'], 'PO A initial status is SUBMITTED');
assertSame(750000, (int)$poA['total_minor'], 'PO A exact minor unit total (10*25000 + 4*125000)');

$poB = $engine->createAndSubmitPurchaseOrder($reqB, [
    'supplier_id' => $supB['id'],
    'po_number' => 'PO-2026-B001',
    'items' => [
        ['sku' => 'PUMP-X', 'ordered_qty' => 2, 'unit_price_minor' => 300000],
    ],
]);
assertSame(600000, (int)$poB['total_minor'], 'PO B exact minor unit total');

// 3. Cross-tenant and role denial checks
assertThrowsStatus(fn() => $engine->getPurchaseOrder($reqB, (int)$poA['id']), 403, 'Tenant B cannot read Tenant A PO');
assertThrowsStatus(fn() => $engine->approvePurchaseOrder($appB, (int)$poA['id']), 403, 'Tenant B approver cannot approve Tenant A PO');
assertThrowsStatus(fn() => $engine->approvePurchaseOrder($reqA, (int)$poA['id']), 403, 'Requester role cannot approve PO');
assertThrowsStatus(fn() => $engine->approvePurchaseOrder($selfAppA, (int)$poA['id']), 403, 'Requester user_id cannot self-approve');
assertThrowsStatus(fn() => $engine->receiveGoods($clerkA, (int)$poA['id'], 'REC-UNAPPROVED', [['sku' => 'VALVE-10MM', 'qty' => 1]]), 409, 'Cannot receive before approval');

// 4. Injected fault during approval rolls back both status change and outbox job
assertThrowsStatus(fn() => $engine->approvePurchaseOrder($appA, (int)$poA['id'], true), 500, 'Injected approval fault throws 500');
$afterFault = $engine->getPurchaseOrder($reqA, (int)$poA['id']);
assertSame('SUBMITTED', $afterFault['status'], 'PO remains SUBMITTED after rollback');
$qBeforeCommit = $engine->processOutboxQueue(1);
assertSame(0, $qBeforeCommit['total_persisted_effects'], 'Zero queue jobs dispatched when approval rolled back');

// 5. Valid approval once; second concurrent/repeat approval denied with 409
$approvedA = $engine->approvePurchaseOrder($appA, (int)$poA['id'], false);
assertSame('APPROVED', $approvedA['status'], 'PO A approved once');
assertThrowsStatus(fn() => $engine->approvePurchaseOrder($appA, (int)$poA['id']), 409, 'Second approval rejected with 409');

// 6. Queue after-commit processing and retry idempotency
$q1 = $engine->processOutboxQueue(1);
assertSame(1, $q1['processed_new'], 'One outbox job processed after commit');
assertSame(1, $q1['total_persisted_effects'], 'Total queue effects == 1');
$q2 = $engine->processOutboxQueue(1);
assertSame(0, $q2['processed_new'], 'Second queue run processes 0 new jobs');
assertSame(1, $q2['idempotent_replays_skipped'], 'Second queue run skips 1 duplicate');
assertSame(1, $q2['total_persisted_effects'], 'Total queue effects remains 1 on replay');

// 7. Partial receiving, idempotency replay, injected fault rollback, and excess rejection
$part1 = $engine->receiveGoods($clerkA, (int)$poA['id'], 'REC-A-001', [
    ['sku' => 'VALVE-10MM', 'qty' => 6],
    ['sku' => 'GAUGE-PRO', 'qty' => 2],
]);
assertSame('PARTIALLY_RECEIVED', $part1['status'], 'PO A is PARTIALLY_RECEIVED');

// Replay same idempotency key -> no duplicate receipt
$part1Replay = $engine->receiveGoods($clerkA, (int)$poA['id'], 'REC-A-001', [
    ['sku' => 'VALVE-10MM', 'qty' => 6],
    ['sku' => 'GAUGE-PRO', 'qty' => 2],
]);
assertSame(6, (int)$part1Replay['items'][0]['received_qty'], 'Idempotent receipt replay does not double received_qty');

// Reject excess quantity (6 + 5 = 11 > 10)
assertThrowsStatus(
    fn() => $engine->receiveGoods($clerkA, (int)$poA['id'], 'REC-A-EXCESS', [['sku' => 'VALVE-10MM', 'qty' => 5]]),
    422,
    'Excess receipt rejected with 422'
);

// Injected fault on partial receipt leaves quantities untouched
assertThrowsStatus(
    fn() => $engine->receiveGoods($clerkA, (int)$poA['id'], 'REC-A-FAULT', [['sku' => 'VALVE-10MM', 'qty' => 4]], true),
    500,
    'Injected receipt fault rolls back'
);

// Complete remaining receipt using a key containing SQL LIKE wildcard characters ('%' and '_') to verify no false collision
$closedA = $engine->receiveGoods($clerkA, (int)$poA['id'], 'REC_%_002', [
    ['sku' => 'VALVE-10MM', 'qty' => 4],
    ['sku' => 'GAUGE-PRO', 'qty' => 2],
]);
assertSame('CLOSED', $closedA['status'], 'PO A transitions to CLOSED when all items fully received');

// Cross-PO idempotency key reuse inside same tenant must fail closed with 409 Conflict
$poA2 = $engine->createAndSubmitPurchaseOrder($reqA, [
    'supplier_id' => $supA['id'],
    'po_number' => 'PO-2026-0002',
    'items' => [['sku' => 'BOLT-M8', 'ordered_qty' => 2, 'unit_price_minor' => 5000]],
]);
$engine->approvePurchaseOrder($appA, (int)$poA2['id'], false);
assertThrowsStatus(
    fn() => $engine->receiveGoods($clerkA, (int)$poA2['id'], 'REC-A-001', [['sku' => 'BOLT-M8', 'qty' => 1]]),
    409,
    'Reusing receipt idempotency key from another PO in same tenant throws 409'
);
$engine->receiveGoods($clerkA, (int)$poA2['id'], 'REC-A2-001', [['sku' => 'BOLT-M8', 'qty' => 2]]);

// 8. Durable restart simulation (open fresh ProcurementEngine connection on same SQLite WAL file)
unset($engine);
$restartedEngine = new ProcurementEngine($dbFile);
$recA = $restartedEngine->reconcileTenant($auditA);
assertSame(true, $recA['reconciled'], 'Tenant A ledger/inventory/movements reconcile after restart');
assertSame(760000, $recA['po_header_total_minor'], 'Tenant A PO header sum == 760000 (750000 + 10000)');
assertSame(760000, $recA['inventory_valuation_minor'], 'Tenant A inventory valuation == 760000');
assertSame(16, $recA['inventory_qty_on_hand'], 'Tenant A inventory qty == 16');

$recB = $restartedEngine->reconcileTenant($auditB);
assertSame(true, $recB['reconciled'], 'Tenant B reconciles independently');
assertSame(600000, $recB['po_header_total_minor'], 'Tenant B PO header sum == 600000');
assertSame(0, $recB['inventory_qty_on_hand'], 'Tenant B inventory qty == 0 (isolated from Tenant A receipts)');

// 9. PDF bytes verification
$pdfBytes = $restartedEngine->generatePurchaseOrderPdf($auditA, (int)$poA['id']);
assertSame(true, str_starts_with($pdfBytes, "%PDF-1.4\n"), 'PDF magic header');
assertSame(true, str_contains($pdfBytes, 'PO-2026-0001'), 'PDF contains PO number');
assertSame(true, str_contains($pdfBytes, 'TOTAL_MINOR: 750000'), 'PDF contains exact minor-unit total');
assertSame(true, str_ends_with($pdfBytes, "%%EOF\n"), 'PDF trailer');

unset($restartedEngine);
@unlink($dbFile);
@unlink($dbFile . '-wal');
@unlink($dbFile . '-shm');

echo json_encode([
    'benchmark' => 'A_PHP_LARAVEL_PROCUREMENT_INVENTORY',
    'status' => 'PASS',
    'assertions_verified' => $assertionsExecuted,
    'tenant_a_reconciled_minor' => 760000,
    'tenant_b_reconciled_minor' => 600000,
    'pdf_bytes_verified' => strlen($pdfBytes),
], JSON_PRETTY_PRINT) . PHP_EOL;
