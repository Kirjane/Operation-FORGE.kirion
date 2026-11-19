"""F15 — Hidden Oracle verification runner for Benchmark A (PHP/Laravel) and Benchmark B (C#/ASP.NET Core)."""
from __future__ import annotations

import json
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..factory import BENCHMARKS_ROOT


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _php_cmd_prefix() -> list[str]:
    php_bin = shutil.which("php")
    if not php_bin:
        raise RuntimeError("PHP binary not found on PATH")
    ext_dir = Path(php_bin).resolve().parent / "ext"
    return [php_bin, "-d", f"extension_dir={ext_dir}", "-d", "extension=pdo_sqlite", "-d", "extension=sqlite3"]


def _http_request(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> tuple[int, bytes]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def _wait_for_health(
    base_url: str,
    *,
    retries: int = 40,
    delay_seconds: float = 0.1,
    requester: Any | None = None,
) -> int:
    """Poll /health retrying transient connection errors until HTTP 200 or fail closed on startup timeout."""
    req_fn = requester or _http_request
    last_status: int | None = None
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            st, _ = req_fn(f"{base_url}/health")
            last_status = st
            if st == 200:
                return 200
        except (urllib.error.URLError, OSError) as exc:
            last_err = exc
        time.sleep(delay_seconds)
    raise RuntimeError(
        f"HTTP server at {base_url}/health failed to report 200 after {retries} attempts "
        f"(last_status={last_status!r}, last_error={last_err!r})."
    )


def run_benchmark_a_with_hidden_oracle(trials: int = 2) -> dict[str, Any]:
    """Run Benchmark A CLI suite + live HTTP server + independent SQLite hidden-oracle verification across repeated trials."""
    bench_dir = BENCHMARKS_ROOT / "php_procurement_inventory"
    php_prefix = _php_cmd_prefix()
    trial_results: list[dict[str, Any]] = []

    for trial in range(1, trials + 1):
        started = time.perf_counter()
        # 1. Execute CLI + restart verification suite
        cli_proc = subprocess.run(
            [*php_prefix, str(bench_dir / "tests" / "run_tests.php")],
            cwd=bench_dir,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        cli_summary = json.loads(cli_proc.stdout.strip())

        # 2. Live HTTP server + hidden SQLite oracle test
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / f"oracle_bench_a_t{trial}.sqlite"
            port = _find_free_port()
            env = {**dict(__import__("os").environ), "KIRION_BENCHMARK_A_DB": str(db_path)}
            server = subprocess.Popen(
                [*php_prefix, "-S", f"127.0.0.1:{port}", str(bench_dir / "public" / "index.php")],
                cwd=bench_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            try:
                base_url = f"http://127.0.0.1:{port}"
                _wait_for_health(base_url, retries=30)

                # Negative HTTP auth checks: missing or zero headers must fail closed with 401
                st_unauth, _ = _http_request(
                    f"{base_url}/api/v1/suppliers",
                    method="POST",
                    body={"code": "NO-AUTH", "name": "Should Fail"},
                )
                assert st_unauth == 401, f"Expected 401 on missing auth headers, got {st_unauth}"
                st_zero_tenant, _ = _http_request(
                    f"{base_url}/api/v1/suppliers",
                    method="POST",
                    headers={"X-Tenant-Id": "0", "X-User-Id": "0", "X-Actor-Role": "requester"},
                    body={"code": "ZERO-TENANT", "name": "Should Fail"},
                )
                assert st_zero_tenant == 401, f"Expected 401 on zero X-Tenant-Id/X-User-Id, got {st_zero_tenant}"

                # Tenant A supplier & PO
                st, sup_raw = _http_request(
                    f"{base_url}/api/v1/suppliers",
                    method="POST",
                    headers={"X-Tenant-Id": "1", "X-User-Id": "101", "X-Actor-Role": "requester"},
                    body={"code": "ORA-SUP-A", "name": "Oracle Supplier A"},
                )
                assert st == 201, f"Expected 201, got {st}"
                sup_id = json.loads(sup_raw)["id"]

                st, po_raw = _http_request(
                    f"{base_url}/api/v1/purchase-orders",
                    method="POST",
                    headers={"X-Tenant-Id": "1", "X-User-Id": "101", "X-Actor-Role": "requester"},
                    body={
                        "supplier_id": sup_id,
                        "po_number": "PO-ORA-100",
                        "items": [
                            {"sku": "SENSOR-A", "ordered_qty": 5, "unit_price_minor": 40000},
                            {"sku": "CABLE-B", "ordered_qty": 10, "unit_price_minor": 5000},
                        ],
                    },
                )
                assert st == 201
                po_id = json.loads(po_raw)["id"]

                # Holdout cross-tenant negative check over HTTP
                st_idor, _ = _http_request(
                    f"{base_url}/api/v1/purchase-orders/get?po_id={po_id}",
                    headers={"X-Tenant-Id": "2", "X-User-Id": "201", "X-Actor-Role": "auditor"},
                )
                assert st_idor == 403, f"Expected 403 cross-tenant denial, got {st_idor}"

                # Approve as Tenant A approver
                st_app, _ = _http_request(
                    f"{base_url}/api/v1/purchase-orders/approve",
                    method="POST",
                    headers={"X-Tenant-Id": "1", "X-User-Id": "102", "X-Actor-Role": "approver"},
                    body={"po_id": po_id},
                )
                assert st_app == 200

                # Partial receive 3 SENSOR-A and 10 CABLE-B
                st_rec, _ = _http_request(
                    f"{base_url}/api/v1/purchase-orders/receive",
                    method="POST",
                    headers={"X-Tenant-Id": "1", "X-User-Id": "103", "X-Actor-Role": "stock_clerk"},
                    body={
                        "po_id": po_id,
                        "idempotency_key": "ORA-REC-1",
                        "lines": [{"sku": "SENSOR-A", "qty": 3}, {"sku": "CABLE-B", "qty": 10}],
                    },
                )
                assert st_rec == 200

                # Queue worker denies unauthorized role (requester -> 403), allows worker/approver (200) and stays idempotent
                st_q_denied, _ = _http_request(
                    f"{base_url}/api/v1/queue/work",
                    method="POST",
                    headers={"X-Tenant-Id": "1", "X-User-Id": "101", "X-Actor-Role": "requester"},
                )
                assert st_q_denied == 403, f"Expected 403 for requester on queue/work, got {st_q_denied}"
                _http_request(
                    f"{base_url}/api/v1/queue/work",
                    method="POST",
                    headers={"X-Tenant-Id": "1", "X-User-Id": "102", "X-Actor-Role": "worker"},
                )
                st_q, q_raw = _http_request(
                    f"{base_url}/api/v1/queue/work",
                    method="POST",
                    headers={"X-Tenant-Id": "1", "X-User-Id": "102", "X-Actor-Role": "worker"},
                )
                assert st_q == 200
                assert json.loads(q_raw)["total_persisted_effects"] == 1

                # Download PDF bytes over HTTP
                st_pdf, pdf_bytes = _http_request(
                    f"{base_url}/api/v1/purchase-orders/pdf?po_id={po_id}",
                    headers={"X-Tenant-Id": "1", "X-User-Id": "104", "X-Actor-Role": "auditor"},
                )
                assert st_pdf == 200
                assert pdf_bytes.startswith(b"%PDF-1.4\n") and pdf_bytes.endswith(b"%%EOF\n")

                # Hidden Oracle: directly inspect SQLite database independently of PHP application code
                conn = sqlite3.connect(db_path)
                try:
                    po_tot = conn.execute("SELECT total_minor, status FROM purchase_orders WHERE id = ?", (po_id,)).fetchone()
                    inv_tot = conn.execute(
                        "SELECT SUM(quantity_on_hand), SUM(valuation_minor) FROM inventory_items WHERE tenant_id = 1"
                    ).fetchone()
                    t2_rows = conn.execute("SELECT COUNT(*) FROM inventory_items WHERE tenant_id = 2").fetchone()[0]
                    assert po_tot == (250000, "PARTIALLY_RECEIVED")
                    # 3*40000 + 10*5000 = 170000 minor units, 13 items
                    assert inv_tot == (13, 170000)
                    assert t2_rows == 0
                finally:
                    conn.close()
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except Exception:
                    server.kill()

        duration = round(time.perf_counter() - started, 3)
        trial_results.append(
            {
                "trial": trial,
                "cli_assertions": cli_summary["assertions_verified"],
                "http_oracle_verified": True,
                "duration_seconds": duration,
            }
        )

    return {
        "benchmark": "A",
        "stack": "PHP 8.4.25 / Laravel Modular Monolith Architecture",
        "status": "PASS",
        "trials_executed": trials,
        "trials": trial_results,
    }


def run_benchmark_b_with_hidden_oracle(trials: int = 2) -> dict[str, Any]:
    """Build and execute Benchmark B (C# / ASP.NET Core 10.0 Transaction Engine) across repeated trials with hidden oracle."""
    bench_dir = BENCHMARKS_ROOT / "dotnet_transaction_engine"
    proj_file = bench_dir / "Kirion.TransactionEngine.csproj"
    trial_results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as build_tmp:
        out_dir = Path(build_tmp) / "out"
        obj_dir = Path(build_tmp) / "obj"
        build_proc = subprocess.run(
            [
                "dotnet",
                "build",
                str(proj_file),
                "-c",
                "Release",
                "-o",
                str(out_dir),
                f"-p:BaseIntermediateOutputPath={obj_dir}\\",
            ],
            cwd=bench_dir,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        # Ensure repo directory has no leftover bin/obj
        for leftover in ("bin", "obj"):
            p = bench_dir / leftover
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)

        exe_path = out_dir / ("Kirion.TransactionEngine.exe" if (out_dir / "Kirion.TransactionEngine.exe").exists() else "Kirion.TransactionEngine")

        for trial in range(1, trials + 1):
            started = time.perf_counter()
            # 1. Run built-in self-test suite (runtime-counted assertions over live Kestrel HTTP + SQLite WAL)
            run_proc = subprocess.run(
                [str(exe_path), "--self-test"],
                cwd=out_dir,
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            summary = json.loads(run_proc.stdout.strip())
            assert summary["status"] == "PASS" and summary["reconciled"] is True

            # 2. Holdout external Python hidden-oracle verification against live Kestrel `--serve` process
            db_path = Path(build_tmp) / f"oracle_bench_b_t{trial}.sqlite"
            port = _find_free_port()
            server = subprocess.Popen(
                [str(exe_path), "--serve", str(port), str(db_path)],
                cwd=out_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                base_url = f"http://127.0.0.1:{port}"
                _wait_for_health(base_url, retries=40)

                # Missing header fails closed with 401
                st_unauth_b, _ = _http_request(
                    f"{base_url}/api/v1/accounts",
                    method="POST",
                    body={"AccountId": "ORA-NOAUTH", "Currency": "PHP", "InitialBalance": 10.00},
                )
                assert st_unauth_b == 401, f"Expected 401 on missing X-Actor-Role, got {st_unauth_b}"

                st_acc, _ = _http_request(
                    f"{base_url}/api/v1/accounts",
                    method="POST",
                    headers={"X-Actor-Role": "treasurer"},
                    body={"AccountId": "ORA-ACC-1", "Currency": "PHP", "InitialBalance": 500.00},
                )
                assert st_acc == 201

                # 5 repeated same-key debit requests of 75.50
                for _ in range(5):
                    st_p, _ = _http_request(
                        f"{base_url}/api/v1/payments",
                        method="POST",
                        headers={"X-Actor-Role": "operator"},
                        body={
                            "AccountId": "ORA-ACC-1",
                            "PaymentId": "ORA-PAY-1",
                            "IdempotencyKey": "ORA-IK-1",
                            "Amount": 75.50,
                            "Currency": "PHP",
                            "Direction": "DEBIT",
                        },
                    )
                    assert st_p == 200

                # Hidden Oracle: directly query SQLite WAL database file from Python
                conn = sqlite3.connect(db_path)
                try:
                    bal_minor = conn.execute("SELECT balance_minor FROM accounts WHERE account_id = 'ORA-ACC-1'").fetchone()[0]
                    ledger_sum = conn.execute("SELECT SUM(signed_amount_minor) FROM ledger_entries WHERE account_id = 'ORA-ACC-1'").fetchone()[0]
                    assert bal_minor == 42450, f"Expected 42450 minor units (500.00 - 75.50), got {bal_minor}"
                    assert ledger_sum == 42450, f"Expected ledger sum 42450, got {ledger_sum}"
                finally:
                    conn.close()
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except Exception:
                    server.kill()

            duration = round(time.perf_counter() - started, 3)
            trial_results.append(
                {
                    "trial": trial,
                    "self_test_assertions": summary["assertions_verified"],
                    "external_hidden_oracle_verified": True,
                    "duration_seconds": duration,
                }
            )

    return {
        "benchmark": "B",
        "stack": "C# / ASP.NET Core 10.0 (SDK 10.0.401) + SQLite WAL",
        "status": "PASS",
        "build_output_clean": "0 Warning(s)" in build_proc.stdout and "0 Error(s)" in build_proc.stdout,
        "trials_executed": trials,
        "trials": trial_results,
    }
