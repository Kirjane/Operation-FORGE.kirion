<?php
declare(strict_types=1);

namespace Kirion\BenchmarkA;

use PDO;
use RuntimeException;

final class DomainHttpException extends RuntimeException
{
    public function __construct(string $message, public readonly int $httpStatus = 400)
    {
        parent::__construct($message, $httpStatus);
    }
}

final class ProcurementEngine
{
    private PDO $pdo;

    public function __construct(string $dbPath)
    {
        $this->pdo = new PDO('sqlite:' . $dbPath, null, null, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
        $this->pdo->exec('PRAGMA journal_mode=WAL;');
        $this->pdo->exec('PRAGMA foreign_keys=ON;');
        $this->pdo->exec('PRAGMA busy_timeout=5000;');
    }

    public function initSchemaV1(): void
    {
        $this->pdo->exec(<<<'SQL'
            CREATE TABLE IF NOT EXISTS schema_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL
            );
            INSERT OR IGNORE INTO schema_meta (id, version) VALUES (1, 1);

            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                UNIQUE(tenant_id, code)
            );

            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                po_number TEXT NOT NULL,
                supplier_id INTEGER NOT NULL,
                requester_id INTEGER NOT NULL,
                approver_id INTEGER NULL,
                status TEXT NOT NULL CHECK (status IN ('DRAFT', 'SUBMITTED', 'APPROVED', 'PARTIALLY_RECEIVED', 'CLOSED')),
                total_minor INTEGER NOT NULL CHECK (total_minor >= 0),
                version INTEGER NOT NULL DEFAULT 1,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY(supplier_id) REFERENCES suppliers(id),
                UNIQUE(tenant_id, po_number)
            );
            CREATE INDEX IF NOT EXISTS idx_po_tenant ON purchase_orders(tenant_id, id);

            CREATE TABLE IF NOT EXISTS purchase_order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                po_id INTEGER NOT NULL,
                tenant_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                ordered_qty INTEGER NOT NULL CHECK (ordered_qty > 0),
                received_qty INTEGER NOT NULL DEFAULT 0 CHECK (received_qty >= 0 AND received_qty <= ordered_qty),
                unit_price_minor INTEGER NOT NULL CHECK (unit_price_minor > 0),
                line_total_minor INTEGER NOT NULL CHECK (line_total_minor > 0),
                FOREIGN KEY(po_id) REFERENCES purchase_orders(id)
            );
            CREATE INDEX IF NOT EXISTS idx_poi_po ON purchase_order_items(po_id);

            CREATE TABLE IF NOT EXISTS inventory_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                quantity_on_hand INTEGER NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
                valuation_minor INTEGER NOT NULL DEFAULT 0 CHECK (valuation_minor >= 0),
                UNIQUE(tenant_id, sku)
            );
        SQL);
    }

    public function migrateV1ToV2(): int
    {
        $this->initSchemaV1();
        $this->pdo->beginTransaction();
        try {
            $this->pdo->exec(<<<'SQL'
                CREATE TABLE IF NOT EXISTS stock_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL,
                    po_id INTEGER NOT NULL,
                    sku TEXT NOT NULL,
                    qty_delta INTEGER NOT NULL,
                    value_delta_minor INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    actor_id INTEGER NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    UNIQUE(tenant_id, idempotency_key)
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    actor_id INTEGER NOT NULL,
                    actor_role TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS outbox_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL,
                    job_key TEXT NOT NULL UNIQUE,
                    job_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('PENDING', 'COMPLETED', 'FAILED')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS processed_jobs (
                    job_key TEXT PRIMARY KEY,
                    tenant_id INTEGER NOT NULL,
                    effect_count INTEGER NOT NULL,
                    processed_at_utc TEXT NOT NULL
                );

                UPDATE schema_meta SET version = 2 WHERE id = 1;
            SQL);
            $this->pdo->commit();
            return $this->getSchemaVersion();
        } catch (\Throwable $e) {
            if ($this->pdo->inTransaction()) {
                $this->pdo->rollBack();
            }
            throw $e;
        }
    }

    public function getSchemaVersion(): int
    {
        $row = $this->pdo->query('SELECT version FROM schema_meta WHERE id = 1')->fetch();
        return $row ? (int)$row['version'] : 0;
    }

    private function assertRole(array $actor, array $allowedRoles): void
    {
        $role = (string)($actor['role'] ?? '');
        if (!in_array($role, $allowedRoles, true)) {
            throw new DomainHttpException("Role '{$role}' is denied for this operation.", 403);
        }
    }

    private function assertTenantMatch(array $actor, int $resourceTenantId): void
    {
        $actorTenant = (int)($actor['tenant_id'] ?? 0);
        if ($actorTenant <= 0 || $actorTenant !== $resourceTenantId) {
            throw new DomainHttpException('Cross-tenant access denied (IDOR protection).', 403);
        }
    }

    public function createSupplier(array $actor, string $code, string $name): array
    {
        $this->assertRole($actor, ['requester', 'approver']);
        $tenantId = (int)$actor['tenant_id'];
        $stmt = $this->pdo->prepare('INSERT INTO suppliers (tenant_id, code, name) VALUES (:t, :c, :n)');
        $stmt->execute([':t' => $tenantId, ':c' => trim($code), ':n' => trim($name)]);
        return ['id' => (int)$this->pdo->lastInsertId(), 'tenant_id' => $tenantId, 'code' => $code, 'name' => $name];
    }

    /**
     * Explicit mass-assignment defense: only reads whitelisted fields (supplier_id, po_number, items).
     * Never honors client-supplied status, tenant_id, or approver_id.
     */
    public function createAndSubmitPurchaseOrder(array $actor, array $payload): array
    {
        $this->assertRole($actor, ['requester']);
        $tenantId = (int)$actor['tenant_id'];
        $actorId = (int)$actor['user_id'];
        $supplierId = (int)($payload['supplier_id'] ?? 0);
        $poNumber = trim((string)($payload['po_number'] ?? ''));
        $items = $payload['items'] ?? [];

        if ($poNumber === '' || !is_array($items) || count($items) === 0) {
            throw new DomainHttpException('Invalid purchase order payload.', 422);
        }

        $supStmt = $this->pdo->prepare('SELECT * FROM suppliers WHERE id = :id');
        $supStmt->execute([':id' => $supplierId]);
        $supplier = $supStmt->fetch();
        if (!$supplier) {
            throw new DomainHttpException('Supplier not found.', 404);
        }
        $this->assertTenantMatch($actor, (int)$supplier['tenant_id']);

        $now = gmdate('Y-m-d\TH:i:s\Z');
        $this->pdo->beginTransaction();
        try {
            $totalMinor = 0;
            $normalizedItems = [];
            foreach ($items as $item) {
                $sku = trim((string)($item['sku'] ?? ''));
                $qty = (int)($item['ordered_qty'] ?? 0);
                $priceMinor = (int)($item['unit_price_minor'] ?? 0);
                if ($sku === '' || $qty <= 0 || $priceMinor <= 0) {
                    throw new DomainHttpException('Invalid item SKU, quantity, or minor-unit price.', 422);
                }
                $lineTotal = $qty * $priceMinor;
                $totalMinor += $lineTotal;
                $normalizedItems[] = [
                    'sku' => $sku,
                    'ordered_qty' => $qty,
                    'unit_price_minor' => $priceMinor,
                    'line_total_minor' => $lineTotal,
                ];
            }

            $poStmt = $this->pdo->prepare(
                'INSERT INTO purchase_orders (tenant_id, po_number, supplier_id, requester_id, status, total_minor, version, created_at_utc)
                 VALUES (:t, :num, :sup, :req, :st, :tot, 1, :now)'
            );
            $poStmt->execute([
                ':t' => $tenantId,
                ':num' => $poNumber,
                ':sup' => $supplierId,
                ':req' => $actorId,
                ':st' => 'SUBMITTED',
                ':tot' => $totalMinor,
                ':now' => $now,
            ]);
            $poId = (int)$this->pdo->lastInsertId();

            $itemStmt = $this->pdo->prepare(
                'INSERT INTO purchase_order_items (po_id, tenant_id, sku, ordered_qty, received_qty, unit_price_minor, line_total_minor)
                 VALUES (:po, :t, :sku, :qty, 0, :price, :tot)'
            );
            foreach ($normalizedItems as $ni) {
                $itemStmt->execute([
                    ':po' => $poId,
                    ':t' => $tenantId,
                    ':sku' => $ni['sku'],
                    ':qty' => $ni['ordered_qty'],
                    ':price' => $ni['unit_price_minor'],
                    ':tot' => $ni['line_total_minor'],
                ]);
            }

            $this->recordAudit($tenantId, 'PURCHASE_ORDER', $poId, 'SUBMITTED', $actorId, (string)$actor['role'], ['po_number' => $poNumber, 'total_minor' => $totalMinor], $now);
            $this->pdo->commit();
            return $this->getPurchaseOrder($actor, $poId);
        } catch (\Throwable $e) {
            if ($this->pdo->inTransaction()) {
                $this->pdo->rollBack();
            }
            throw $e;
        }
    }

    public function approvePurchaseOrder(array $actor, int $poId, bool $injectFault = false): array
    {
        $this->assertRole($actor, ['approver']);
        $actorId = (int)$actor['user_id'];
        $now = gmdate('Y-m-d\TH:i:s\Z');

        $this->pdo->exec('BEGIN IMMEDIATE;');
        try {
            $po = $this->fetchPoRaw($poId);
            $this->assertTenantMatch($actor, (int)$po['tenant_id']);

            if ((int)$po['requester_id'] === $actorId) {
                throw new DomainHttpException('Segregation of duties violation: requester cannot self-approve.', 403);
            }
            if ($po['status'] !== 'SUBMITTED') {
                throw new DomainHttpException("Purchase order cannot be approved from state '{$po['status']}'.", 409);
            }

            $upd = $this->pdo->prepare(
                "UPDATE purchase_orders
                 SET status = 'APPROVED', approver_id = :app, version = version + 1
                 WHERE id = :id AND version = :ver AND status = 'SUBMITTED'"
            );
            $upd->execute([':app' => $actorId, ':id' => $poId, ':ver' => (int)$po['version']]);
            if ($upd->rowcount() !== 1) {
                throw new DomainHttpException('Concurrent approval conflict detected.', 409);
            }

            // Transactional outbox job staged inside commit boundary (dispatched after commit)
            $jobKey = "po-approved-{$po['tenant_id']}-{$poId}";
            $jobStmt = $this->pdo->prepare(
                "INSERT INTO outbox_jobs (tenant_id, job_key, job_type, payload_json, status, attempts, created_at_utc)
                 VALUES (:t, :jk, 'PO_APPROVED_NOTIFICATION', :pl, 'PENDING', 0, :now)"
            );
            $jobStmt->execute([
                ':t' => (int)$po['tenant_id'],
                ':jk' => $jobKey,
                ':pl' => json_encode(['po_id' => $poId, 'po_number' => $po['po_number'], 'total_minor' => (int)$po['total_minor']]),
                ':now' => $now,
            ]);

            $this->recordAudit((int)$po['tenant_id'], 'PURCHASE_ORDER', $poId, 'APPROVED', $actorId, 'approver', ['job_key' => $jobKey], $now);

            if ($injectFault) {
                throw new DomainHttpException('Injected fault after approval write to verify atomic rollback.', 500);
            }

            $this->pdo->exec('COMMIT;');
            return $this->getPurchaseOrder($actor, $poId);
        } catch (\Throwable $e) {
            $this->pdo->exec('ROLLBACK;');
            throw $e;
        }
    }

    public function receiveGoods(array $actor, int $poId, string $idempotencyKey, array $receiptLines, bool $injectFault = false): array
    {
        $this->assertRole($actor, ['stock_clerk']);
        $actorId = (int)$actor['user_id'];
        $idempotencyKey = trim($idempotencyKey);
        if ($idempotencyKey === '' || count($receiptLines) === 0) {
            throw new DomainHttpException('Idempotency key and receipt lines are required.', 422);
        }
        $now = gmdate('Y-m-d\TH:i:s\Z');

        $this->pdo->exec('BEGIN IMMEDIATE;');
        try {
            $po = $this->fetchPoRaw($poId);
            $tenantId = (int)$po['tenant_id'];
            $this->assertTenantMatch($actor, $tenantId);

            // Check exact idempotency key prefix inside transaction (immune to SQL LIKE '%'/'_' wildcards)
            // Scope by po_id: same PO returns idempotent replay; different PO in same tenant raises 409 Conflict
            $prefix = $idempotencyKey . ':';
            $dupStmt = $this->pdo->prepare(
                'SELECT DISTINCT po_id FROM stock_movements WHERE tenant_id = :t AND SUBSTR(idempotency_key, 1, :plen) = :pref'
            );
            $dupStmt->bindValue(':t', $tenantId, PDO::PARAM_INT);
            $dupStmt->bindValue(':plen', strlen($prefix), PDO::PARAM_INT);
            $dupStmt->bindValue(':pref', $prefix, PDO::PARAM_STR);
            $dupStmt->execute();
            $existingPoIds = array_map(static fn(array $r): int => (int)$r['po_id'], $dupStmt->fetchAll());
            if (count($existingPoIds) > 0) {
                if (in_array($poId, $existingPoIds, true)) {
                    $this->pdo->exec('COMMIT;');
                    return $this->getPurchaseOrder($actor, $poId);
                }
                throw new DomainHttpException(
                    "Idempotency key '{$idempotencyKey}' was already used for a different purchase order in tenant {$tenantId}.",
                    409
                );
            }

            if (!in_array($po['status'], ['APPROVED', 'PARTIALLY_RECEIVED'], true)) {
                throw new DomainHttpException("Cannot receive goods for PO in state '{$po['status']}'.", 409);
            }

            foreach ($receiptLines as $idx => $line) {
                $sku = trim((string)($line['sku'] ?? ''));
                $qty = (int)($line['qty'] ?? 0);
                if ($sku === '' || $qty <= 0) {
                    throw new DomainHttpException('Receipt line requires positive qty and SKU.', 422);
                }

                $itemStmt = $this->pdo->prepare('SELECT * FROM purchase_order_items WHERE po_id = :po AND sku = :sku');
                $itemStmt->execute([':po' => $poId, ':sku' => $sku]);
                $item = $itemStmt->fetch();
                if (!$item) {
                    throw new DomainHttpException("SKU '{$sku}' not found on purchase order.", 404);
                }

                $newReceived = (int)$item['received_qty'] + $qty;
                if ($newReceived > (int)$item['ordered_qty']) {
                    throw new DomainHttpException(
                        "Excess receipt rejected for SKU '{$sku}': {$newReceived} exceeds ordered {$item['ordered_qty']}.",
                        422
                    );
                }

                $updItem = $this->pdo->prepare('UPDATE purchase_order_items SET received_qty = :rq WHERE id = :id');
                $updItem->execute([':rq' => $newReceived, ':id' => (int)$item['id']]);

                $valueDeltaMinor = $qty * (int)$item['unit_price_minor'];
                $invStmt = $this->pdo->prepare(
                    'INSERT INTO inventory_items (tenant_id, sku, quantity_on_hand, valuation_minor)
                     VALUES (:t, :sku, :qty, :val)
                     ON CONFLICT(tenant_id, sku) DO UPDATE SET
                        quantity_on_hand = quantity_on_hand + :qty,
                        valuation_minor = valuation_minor + :val'
                );
                $invStmt->execute([':t' => $tenantId, ':sku' => $sku, ':qty' => $qty, ':val' => $valueDeltaMinor]);

                $movStmt = $this->pdo->prepare(
                    'INSERT INTO stock_movements (tenant_id, po_id, sku, qty_delta, value_delta_minor, idempotency_key, actor_id, created_at_utc)
                     VALUES (:t, :po, :sku, :qty, :val, :ik, :act, :now)'
                );
                $movStmt->execute([
                    ':t' => $tenantId,
                    ':po' => $poId,
                    ':sku' => $sku,
                    ':qty' => $qty,
                    ':val' => $valueDeltaMinor,
                    ':ik' => "{$idempotencyKey}:{$idx}:{$sku}",
                    ':act' => $actorId,
                    ':now' => $now,
                ]);
            }

            // Recompute PO status from persisted line items
            $allItemsStmt = $this->pdo->prepare('SELECT ordered_qty, received_qty FROM purchase_order_items WHERE po_id = :po');
            $allItemsStmt->execute([':po' => $poId]);
            $allRows = $allItemsStmt->fetchAll();
            $allComplete = true;
            foreach ($allRows as $r) {
                if ((int)$r['received_qty'] < (int)$r['ordered_qty']) {
                    $allComplete = false;
                    break;
                }
            }
            $nextStatus = $allComplete ? 'CLOSED' : 'PARTIALLY_RECEIVED';
            $this->pdo->prepare('UPDATE purchase_orders SET status = :st, version = version + 1 WHERE id = :id')
                ->execute([':st' => $nextStatus, ':id' => $poId]);

            $this->recordAudit($tenantId, 'PURCHASE_ORDER', $poId, 'GOODS_RECEIVED', $actorId, 'stock_clerk', ['status' => $nextStatus, 'idempotency_key' => $idempotencyKey], $now);

            if ($injectFault) {
                throw new DomainHttpException('Injected fault during goods receipt to verify atomic rollback.', 500);
            }

            $this->pdo->exec('COMMIT;');
            return $this->getPurchaseOrder($actor, $poId);
        } catch (\Throwable $e) {
            $this->pdo->exec('ROLLBACK;');
            throw $e;
        }
    }

    public function processOutboxQueue(int $tenantId): array
    {
        $now = gmdate('Y-m-d\TH:i:s\Z');
        $stmt = $this->pdo->prepare('SELECT * FROM outbox_jobs WHERE tenant_id = :t ORDER BY id ASC');
        $stmt->execute([':t' => $tenantId]);
        $jobs = $stmt->fetchAll();
        $processed = 0;
        $skippedDuplicate = 0;

        foreach ($jobs as $job) {
            $jobKey = (string)$job['job_key'];
            $this->pdo->exec('BEGIN IMMEDIATE;');
            try {
                $chk = $this->pdo->prepare('SELECT * FROM processed_jobs WHERE job_key = :jk');
                $chk->execute([':jk' => $jobKey]);
                if ($chk->fetch()) {
                    $this->pdo->prepare("UPDATE outbox_jobs SET status = 'COMPLETED', attempts = attempts + 1 WHERE id = :id")
                        ->execute([':id' => (int)$job['id']]);
                    $this->pdo->exec('COMMIT;');
                    $skippedDuplicate++;
                    continue;
                }

                $this->pdo->prepare(
                    'INSERT INTO processed_jobs (job_key, tenant_id, effect_count, processed_at_utc) VALUES (:jk, :t, 1, :now)'
                )->execute([':jk' => $jobKey, ':t' => $tenantId, ':now' => $now]);

                $this->pdo->prepare("UPDATE outbox_jobs SET status = 'COMPLETED', attempts = attempts + 1 WHERE id = :id")
                    ->execute([':id' => (int)$job['id']]);
                $this->pdo->exec('COMMIT;');
                $processed++;
            } catch (\Throwable $e) {
                $this->pdo->exec('ROLLBACK;');
                throw $e;
            }
        }

        $totalEffectsStmt = $this->pdo->prepare('SELECT COALESCE(SUM(effect_count), 0) AS total_effects FROM processed_jobs WHERE tenant_id = :t');
        $totalEffectsStmt->execute([':t' => $tenantId]);
        $totalEffects = (int)$totalEffectsStmt->fetch()['total_effects'];

        return [
            'tenant_id' => $tenantId,
            'processed_new' => $processed,
            'idempotent_replays_skipped' => $skippedDuplicate,
            'total_persisted_effects' => $totalEffects,
        ];
    }

    public function getPurchaseOrder(array $actor, int $poId): array
    {
        $this->assertRole($actor, ['requester', 'approver', 'stock_clerk', 'auditor']);
        // Eager load PO + items in 2 bounded queries (zero N+1)
        $po = $this->fetchPoRaw($poId);
        $this->assertTenantMatch($actor, (int)$po['tenant_id']);

        $itemsStmt = $this->pdo->prepare('SELECT id, sku, ordered_qty, received_qty, unit_price_minor, line_total_minor FROM purchase_order_items WHERE po_id = :po ORDER BY id ASC');
        $itemsStmt->execute([':po' => $poId]);
        $po['items'] = $itemsStmt->fetchAll();
        return $po;
    }

    public function generatePurchaseOrderPdf(array $actor, int $poId): string
    {
        $po = $this->getPurchaseOrder($actor, $poId);
        $lines = [
            "KIRION FORGE PROCUREMENT RECEIPT",
            "PO_NUMBER: {$po['po_number']}",
            "TENANT_ID: {$po['tenant_id']}",
            "STATUS: {$po['status']}",
            "TOTAL_MINOR: {$po['total_minor']}",
        ];
        foreach ($po['items'] as $item) {
            $lines[] = "ITEM {$item['sku']} ORDERED={$item['ordered_qty']} RECEIVED={$item['received_qty']} LINE_MINOR={$item['line_total_minor']}";
        }
        $textPayload = implode(' | ', $lines);
        $escaped = str_replace(['\\', '(', ')'], ['\\\\', '\\(', '\\)'], $textPayload);
        $stream = "BT /F1 10 Tf 36 750 Td ({$escaped}) Tj ET";
        $streamLen = strlen($stream);

        return "%PDF-1.4\n"
            . "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            . "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            . "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj\n"
            . "4 0 obj << /Length {$streamLen} >>\nstream\n{$stream}\nendstream\nendobj\n"
            . "trailer << /Root 1 0 R >>\n%%EOF\n";
    }

    public function reconcileTenant(array $actor): array
    {
        $this->assertRole($actor, ['auditor', 'approver']);
        $tenantId = (int)$actor['tenant_id'];

        $poHeaderStmt = $this->pdo->prepare('SELECT COALESCE(SUM(total_minor), 0) AS s FROM purchase_orders WHERE tenant_id = :t');
        $poHeaderStmt->execute([':t' => $tenantId]);
        $poHeaderSum = (int)$poHeaderStmt->fetch()['s'];

        $poLineStmt = $this->pdo->prepare('SELECT COALESCE(SUM(line_total_minor), 0) AS s, COALESCE(SUM(received_qty), 0) AS rq FROM purchase_order_items WHERE tenant_id = :t');
        $poLineStmt->execute([':t' => $tenantId]);
        $lineRow = $poLineStmt->fetch();
        $poLineSum = (int)$lineRow['s'];
        $poReceivedQty = (int)$lineRow['rq'];

        $invStmt = $this->pdo->prepare('SELECT COALESCE(SUM(quantity_on_hand), 0) AS q, COALESCE(SUM(valuation_minor), 0) AS v FROM inventory_items WHERE tenant_id = :t');
        $invStmt->execute([':t' => $tenantId]);
        $invRow = $invStmt->fetch();
        $invQty = (int)$invRow['q'];
        $invVal = (int)$invRow['v'];

        $movStmt = $this->pdo->prepare('SELECT COALESCE(SUM(qty_delta), 0) AS q, COALESCE(SUM(value_delta_minor), 0) AS v FROM stock_movements WHERE tenant_id = :t');
        $movStmt->execute([':t' => $tenantId]);
        $movRow = $movStmt->fetch();
        $movQty = (int)$movRow['q'];
        $movVal = (int)$movRow['v'];

        $reconciled = ($poHeaderSum === $poLineSum) && ($poReceivedQty === $invQty) && ($invQty === $movQty) && ($invVal === $movVal);

        return [
            'tenant_id' => $tenantId,
            'po_header_total_minor' => $poHeaderSum,
            'po_lines_total_minor' => $poLineSum,
            'po_received_qty' => $poReceivedQty,
            'inventory_qty_on_hand' => $invQty,
            'inventory_valuation_minor' => $invVal,
            'stock_movements_qty' => $movQty,
            'stock_movements_valuation_minor' => $movVal,
            'reconciled' => $reconciled,
        ];
    }

    private function fetchPoRaw(int $poId): array
    {
        $stmt = $this->pdo->prepare('SELECT * FROM purchase_orders WHERE id = :id');
        $stmt->execute([':id' => $poId]);
        $po = $stmt->fetch();
        if (!$po) {
            throw new DomainHttpException("Purchase order {$poId} not found.", 404);
        }
        return $po;
    }

    private function recordAudit(int $tenantId, string $entityType, int $entityId, string $action, int $actorId, string $actorRole, array $details, string $now): void
    {
        $stmt = $this->pdo->prepare(
            'INSERT INTO audit_logs (tenant_id, entity_type, entity_id, action, actor_id, actor_role, details_json, created_at_utc)
             VALUES (:t, :et, :eid, :act, :uid, :role, :det, :now)'
        );
        $stmt->execute([
            ':t' => $tenantId,
            ':et' => $entityType,
            ':eid' => $entityId,
            ':act' => $action,
            ':uid' => $actorId,
            ':role' => $actorRole,
            ':det' => json_encode($details),
            ':now' => $now,
        ]);
    }
}
