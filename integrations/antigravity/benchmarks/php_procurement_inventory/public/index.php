<?php
declare(strict_types=1);

require_once __DIR__ . '/../src/ProcurementEngine.php';

use Kirion\BenchmarkA\DomainHttpException;
use Kirion\BenchmarkA\ProcurementEngine;

$dbPath = getenv('KIRION_BENCHMARK_A_DB') ?: (sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'kirion_benchmark_a_http.sqlite');
$engine = new ProcurementEngine($dbPath);
$engine->migrateV1ToV2();

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$uri = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$rawBody = file_get_contents('php://input') ?: '{}';
$body = json_decode($rawBody, true) ?: [];

try {
    if ($method === 'GET' && $uri === '/health') {
        header('Content-Type: application/json');
        echo json_encode(['status' => 'ok', 'schema_version' => $engine->getSchemaVersion()]);
        exit;
    }

    // Fail-closed authentication: require positive integer tenant/user IDs and non-empty role on all /api/v1/* routes
    $rawTenant = trim((string)($_SERVER['HTTP_X_TENANT_ID'] ?? ''));
    $rawUser = trim((string)($_SERVER['HTTP_X_USER_ID'] ?? ''));
    $rawRole = trim((string)($_SERVER['HTTP_X_ACTOR_ROLE'] ?? ''));
    if (
        $rawTenant === ''
        || $rawUser === ''
        || $rawRole === ''
        || !ctype_digit($rawTenant)
        || !ctype_digit($rawUser)
        || (int)$rawTenant <= 0
        || (int)$rawUser <= 0
    ) {
        throw new DomainHttpException('Missing or invalid authentication headers (positive integer X-Tenant-Id, X-User-Id, and non-empty X-Actor-Role required).', 401);
    }

    $actor = [
        'tenant_id' => (int)$rawTenant,
        'user_id' => (int)$rawUser,
        'role' => $rawRole,
    ];

    if ($method === 'POST' && $uri === '/api/v1/suppliers') {
        header('Content-Type: application/json');
        http_response_code(201);
        echo json_encode($engine->createSupplier($actor, (string)($body['code'] ?? ''), (string)($body['name'] ?? '')));
        exit;
    }

    if ($method === 'POST' && $uri === '/api/v1/purchase-orders') {
        header('Content-Type: application/json');
        http_response_code(201);
        echo json_encode($engine->createAndSubmitPurchaseOrder($actor, $body));
        exit;
    }

    if ($method === 'POST' && $uri === '/api/v1/purchase-orders/approve') {
        header('Content-Type: application/json');
        echo json_encode($engine->approvePurchaseOrder($actor, (int)($body['po_id'] ?? 0), (bool)($body['inject_fault'] ?? false)));
        exit;
    }

    if ($method === 'POST' && $uri === '/api/v1/purchase-orders/receive') {
        header('Content-Type: application/json');
        echo json_encode($engine->receiveGoods(
            $actor,
            (int)($body['po_id'] ?? 0),
            (string)($body['idempotency_key'] ?? ''),
            (array)($body['lines'] ?? []),
            (bool)($body['inject_fault'] ?? false)
        ));
        exit;
    }

    if ($method === 'POST' && $uri === '/api/v1/queue/work') {
        if (!in_array($actor['role'], ['approver', 'stock_clerk', 'worker'], true)) {
            throw new DomainHttpException("Role '{$actor['role']}' is denied from executing outbox queue worker.", 403);
        }
        header('Content-Type: application/json');
        echo json_encode($engine->processOutboxQueue((int)$actor['tenant_id']));
        exit;
    }

    if ($method === 'GET' && $uri === '/api/v1/purchase-orders/get') {
        header('Content-Type: application/json');
        echo json_encode($engine->getPurchaseOrder($actor, (int)($_GET['po_id'] ?? 0)));
        exit;
    }

    if ($method === 'GET' && $uri === '/api/v1/purchase-orders/pdf') {
        $pdf = $engine->generatePurchaseOrderPdf($actor, (int)($_GET['po_id'] ?? 0));
        header('Content-Type: application/pdf');
        echo $pdf;
        exit;
    }

    if ($method === 'GET' && $uri === '/api/v1/reconcile') {
        header('Content-Type: application/json');
        echo json_encode($engine->reconcileTenant($actor));
        exit;
    }

    http_response_code(404);
    header('Content-Type: application/problem+json');
    echo json_encode(['title' => 'Not Found', 'status' => 404, 'detail' => "Route {$uri} not found."]);
} catch (DomainHttpException $e) {
    http_response_code($e->httpStatus);
    header('Content-Type: application/problem+json');
    echo json_encode([
        'type' => 'https://kirion-forge.local/problems/domain-error',
        'title' => 'Domain Guard Violation',
        'status' => $e->httpStatus,
        'detail' => $e->getMessage(),
    ]);
} catch (\Throwable $e) {
    http_response_code(500);
    header('Content-Type: application/problem+json');
    echo json_encode([
        'type' => 'https://kirion-forge.local/problems/internal-error',
        'title' => 'Internal Server Error',
        'status' => 500,
        'detail' => 'An internal transaction error occurred.',
    ]);
}
