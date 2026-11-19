using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Data.Sqlite;

namespace Kirion.TransactionEngine;

public sealed class DomainException : Exception
{
    public int StatusCode { get; }
    public DomainException(string message, int statusCode = 400) : base(message)
    {
        StatusCode = statusCode;
    }
}

public sealed record CreateAccountRequest(string AccountId, string Currency, decimal InitialBalance);
public sealed record PostPaymentRequest(string AccountId, string PaymentId, string IdempotencyKey, decimal Amount, string Currency, string Direction, bool InjectFault = false);
public sealed record ReversePaymentRequest(string ReversalIdempotencyKey, string Reason, bool InjectFault = false);

public sealed class ScopedTransactionStore : IDisposable
{
    public Guid ScopeInstanceId { get; } = Guid.NewGuid();
    private readonly string _connectionString;
    private static readonly SemaphoreSlim WriteGate = new(1, 1);

    public ScopedTransactionStore(IConfiguration config)
    {
        var dbPath = config["DatabasePath"] ?? throw new InvalidOperationException("DatabasePath is required.");
        _connectionString = new SqliteConnectionStringBuilder
        {
            DataSource = dbPath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Pooling = false
        }.ToString();
    }

    private async Task<SqliteConnection> OpenConnectionAsync(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        var conn = new SqliteConnection(_connectionString);
        await conn.OpenAsync(ct);
        await using (var pragma = conn.CreateCommand())
        {
            pragma.CommandText = "PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;";
            await pragma.ExecuteNonQueryAsync(ct);
        }
        return conn;
    }

    public static long ToMinorUnits(decimal amount)
    {
        if (decimal.Round(amount, 2, MidpointRounding.ToEven) != amount)
        {
            throw new DomainException($"Amount {amount} exceeds permitted 2-decimal scale.", 422);
        }
        return (long)(amount * 100m);
    }

    public static decimal FromMinorUnits(long minor) => minor / 100m;

    public async Task InitSchemaV1Async(CancellationToken ct)
    {
        await using var conn = await OpenConnectionAsync(ct);
        await using var cmd = conn.CreateCommand();
        cmd.CommandText = """
            CREATE TABLE IF NOT EXISTS schema_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL
            );
            INSERT OR IGNORE INTO schema_meta (id, version) VALUES (1, 1);

            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                currency TEXT NOT NULL,
                balance_minor INTEGER NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                updated_at_utc TEXT NOT NULL
            );
            """;
        await cmd.ExecuteNonQueryAsync(ct);
    }

    public async Task<int> MigrateV1ToV2Async(CancellationToken ct)
    {
        await InitSchemaV1Async(ct);
        await using var conn = await OpenConnectionAsync(ct);
        await using var tx = await conn.BeginTransactionAsync(ct);
        try
        {
            await using var cmd = conn.CreateCommand();
            cmd.Transaction = (SqliteTransaction)tx;
            cmd.CommandText = """
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    direction TEXT NOT NULL CHECK (direction IN ('CREDIT', 'DEBIT')),
                    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
                    currency TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('SETTLED', 'REVERSED')),
                    reversal_idempotency_key TEXT NULL UNIQUE,
                    created_at_utc TEXT NOT NULL,
                    reversed_at_utc TEXT NULL,
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
                );

                CREATE TABLE IF NOT EXISTS ledger_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    payment_id TEXT NOT NULL,
                    entry_kind TEXT NOT NULL CHECK (entry_kind IN ('PAYMENT', 'REVERSAL')),
                    signed_amount_minor INTEGER NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
                );
                CREATE INDEX IF NOT EXISTS idx_ledger_acc ON ledger_entries(account_id, id);

                CREATE TABLE IF NOT EXISTS audit_trail (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor_role TEXT NOT NULL,
                    details TEXT NULL,
                    created_at_utc TEXT NOT NULL
                );

                UPDATE schema_meta SET version = 2 WHERE id = 1;
                """;
            await cmd.ExecuteNonQueryAsync(ct);
            await tx.CommitAsync(ct);
        }
        catch
        {
            await tx.RollbackAsync(ct);
            throw;
        }
        return await GetSchemaVersionAsync(ct);
    }

    public async Task<int> GetSchemaVersionAsync(CancellationToken ct)
    {
        await using var conn = await OpenConnectionAsync(ct);
        await using var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT version FROM schema_meta WHERE id = 1;";
        var res = await cmd.ExecuteScalarAsync(ct);
        return Convert.ToInt32(res, CultureInfo.InvariantCulture);
    }

    public async Task<Dictionary<string, object>> CreateAccountAsync(CreateAccountRequest req, string actorRole, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if (actorRole is not ("operator" or "treasurer"))
            throw new DomainException($"Role '{actorRole}' cannot create accounts.", 403);
        if (string.IsNullOrWhiteSpace(req.AccountId) || string.IsNullOrWhiteSpace(req.Currency))
            throw new DomainException("AccountId and Currency are required.", 422);
        var initialMinor = ToMinorUnits(req.InitialBalance);
        if (initialMinor < 0)
            throw new DomainException("InitialBalance cannot be negative.", 422);

        await WriteGate.WaitAsync(ct);
        try
        {
            await using var conn = await OpenConnectionAsync(ct);
            await using var tx = await conn.BeginTransactionAsync(ct);
            try
            {
                var now = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);
                await using (var cmd = conn.CreateCommand())
                {
                    cmd.Transaction = (SqliteTransaction)tx;
                    cmd.CommandText = """
                        INSERT INTO accounts (account_id, currency, balance_minor, version, updated_at_utc)
                        VALUES ($id, $cur, $bal, 1, $now);
                        """;
                    cmd.Parameters.AddWithValue("$id", req.AccountId);
                    cmd.Parameters.AddWithValue("$cur", req.Currency.ToUpperInvariant());
                    cmd.Parameters.AddWithValue("$bal", initialMinor);
                    cmd.Parameters.AddWithValue("$now", now);
                    await cmd.ExecuteNonQueryAsync(ct);
                }

                // If schema v2 is active and initialMinor > 0, record genesis ledger row so ledger reconciles
                var ver = await GetSchemaVersionInTxAsync(conn, (SqliteTransaction)tx, ct);
                if (ver >= 2 && initialMinor > 0)
                {
                    await using var pCmd = conn.CreateCommand();
                    pCmd.Transaction = (SqliteTransaction)tx;
                    pCmd.CommandText = """
                        INSERT INTO payments (payment_id, account_id, idempotency_key, direction, amount_minor, currency, state, created_at_utc)
                        VALUES ($pid, $aid, $ik, 'CREDIT', $amt, $cur, 'SETTLED', $now);
                        INSERT INTO ledger_entries (account_id, payment_id, entry_kind, signed_amount_minor, created_at_utc)
                        VALUES ($aid, $pid, 'PAYMENT', $amt, $now);
                        """;
                    pCmd.Parameters.AddWithValue("$pid", $"INIT-{req.AccountId}");
                    pCmd.Parameters.AddWithValue("$aid", req.AccountId);
                    pCmd.Parameters.AddWithValue("$ik", $"INIT-IK-{req.AccountId}");
                    pCmd.Parameters.AddWithValue("$amt", initialMinor);
                    pCmd.Parameters.AddWithValue("$cur", req.Currency.ToUpperInvariant());
                    pCmd.Parameters.AddWithValue("$now", now);
                    await pCmd.ExecuteNonQueryAsync(ct);
                }

                await tx.CommitAsync(ct);
                return new Dictionary<string, object>
                {
                    ["account_id"] = req.AccountId,
                    ["currency"] = req.Currency.ToUpperInvariant(),
                    ["balance"] = FromMinorUnits(initialMinor),
                    ["balance_minor"] = initialMinor,
                    ["version"] = 1
                };
            }
            catch
            {
                await tx.RollbackAsync(ct);
                throw;
            }
        }
        finally
        {
            WriteGate.Release();
        }
    }

    public async Task<Dictionary<string, object>> PostPaymentAsync(PostPaymentRequest req, string actorRole, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if (actorRole is not ("operator" or "treasurer"))
            throw new DomainException($"Role '{actorRole}' is denied from posting payments.", 403);
        if (string.IsNullOrWhiteSpace(req.IdempotencyKey) || string.IsNullOrWhiteSpace(req.PaymentId))
            throw new DomainException("IdempotencyKey and PaymentId are required.", 422);

        var amountMinor = ToMinorUnits(req.Amount);
        if (amountMinor <= 0)
            throw new DomainException("Payment amount must be strictly positive.", 422);
        var dir = req.Direction?.ToUpperInvariant() ?? "";
        if (dir is not ("CREDIT" or "DEBIT"))
            throw new DomainException("Direction must be CREDIT or DEBIT.", 422);

        await WriteGate.WaitAsync(ct);
        try
        {
            await using var conn = await OpenConnectionAsync(ct);
            await using var tx = await conn.BeginTransactionAsync(ct);
            try
            {
                // 1. Check idempotency key inside transaction
                await using (var dupCmd = conn.CreateCommand())
                {
                    dupCmd.Transaction = (SqliteTransaction)tx;
                    dupCmd.CommandText = """
                        SELECT p.payment_id, p.account_id, p.amount_minor, p.direction, p.state, a.balance_minor
                        FROM payments p
                        JOIN accounts a ON a.account_id = p.account_id
                        WHERE p.idempotency_key = $ik;
                        """;
                    dupCmd.Parameters.AddWithValue("$ik", req.IdempotencyKey);
                    await using var reader = await dupCmd.ExecuteReaderAsync(ct);
                    if (await reader.ReadAsync(ct))
                    {
                        var existingPid = reader.GetString(0);
                        var existingAid = reader.GetString(1);
                        var existingAmt = reader.GetInt64(2);
                        var existingDir = reader.GetString(3);
                        var existingState = reader.GetString(4);
                        var currentBal = reader.GetInt64(5);
                        await reader.CloseAsync();
                        await tx.CommitAsync(ct);
                        return new Dictionary<string, object>
                        {
                            ["payment_id"] = existingPid,
                            ["account_id"] = existingAid,
                            ["amount"] = FromMinorUnits(existingAmt),
                            ["amount_minor"] = existingAmt,
                            ["direction"] = existingDir,
                            ["state"] = existingState,
                            ["balance"] = FromMinorUnits(currentBal),
                            ["balance_minor"] = currentBal,
                            ["idempotent_replay"] = true
                        };
                    }
                }

                // 2. Load account with optimistic version check
                long currentBalanceMinor;
                long currentVersion;
                string accountCurrency;
                await using (var accCmd = conn.CreateCommand())
                {
                    accCmd.Transaction = (SqliteTransaction)tx;
                    accCmd.CommandText = "SELECT currency, balance_minor, version FROM accounts WHERE account_id = $aid;";
                    accCmd.Parameters.AddWithValue("$aid", req.AccountId);
                    await using var r = await accCmd.ExecuteReaderAsync(ct);
                    if (!await r.ReadAsync(ct))
                        throw new DomainException($"Account '{req.AccountId}' not found.", 404);
                    accountCurrency = r.GetString(0);
                    currentBalanceMinor = r.GetInt64(1);
                    currentVersion = r.GetInt64(2);
                }

                if (!string.Equals(accountCurrency, req.Currency, StringComparison.OrdinalIgnoreCase))
                    throw new DomainException("Currency mismatch with account.", 422);

                var signedDelta = dir == "CREDIT" ? amountMinor : -amountMinor;
                var newBalanceMinor = currentBalanceMinor + signedDelta;
                if (newBalanceMinor < 0)
                    throw new DomainException("Insufficient funds for debit.", 409);

                var now = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);

                await using (var updCmd = conn.CreateCommand())
                {
                    updCmd.Transaction = (SqliteTransaction)tx;
                    updCmd.CommandText = """
                        UPDATE accounts
                        SET balance_minor = $nb, version = version + 1, updated_at_utc = $now
                        WHERE account_id = $aid AND version = $ver;
                        """;
                    updCmd.Parameters.AddWithValue("$nb", newBalanceMinor);
                    updCmd.Parameters.AddWithValue("$now", now);
                    updCmd.Parameters.AddWithValue("$aid", req.AccountId);
                    updCmd.Parameters.AddWithValue("$ver", currentVersion);
                    var rows = await updCmd.ExecuteNonQueryAsync(ct);
                    if (rows != 1)
                        throw new DomainException("Optimistic concurrency conflict on account update.", 409);
                }

                await using (var insCmd = conn.CreateCommand())
                {
                    insCmd.Transaction = (SqliteTransaction)tx;
                    insCmd.CommandText = """
                        INSERT INTO payments (payment_id, account_id, idempotency_key, direction, amount_minor, currency, state, created_at_utc)
                        VALUES ($pid, $aid, $ik, $dir, $amt, $cur, 'SETTLED', $now);

                        INSERT INTO ledger_entries (account_id, payment_id, entry_kind, signed_amount_minor, created_at_utc)
                        VALUES ($aid, $pid, 'PAYMENT', $signed, $now);

                        INSERT INTO audit_trail (entity_id, action, actor_role, created_at_utc)
                        VALUES ($pid, 'PAYMENT_SETTLED', $role, $now);
                        """;
                    insCmd.Parameters.AddWithValue("$pid", req.PaymentId);
                    insCmd.Parameters.AddWithValue("$aid", req.AccountId);
                    insCmd.Parameters.AddWithValue("$ik", req.IdempotencyKey);
                    insCmd.Parameters.AddWithValue("$dir", dir);
                    insCmd.Parameters.AddWithValue("$amt", amountMinor);
                    insCmd.Parameters.AddWithValue("$cur", accountCurrency);
                    insCmd.Parameters.AddWithValue("$signed", signedDelta);
                    insCmd.Parameters.AddWithValue("$role", actorRole);
                    insCmd.Parameters.AddWithValue("$now", now);
                    await insCmd.ExecuteNonQueryAsync(ct);
                }

                if (req.InjectFault)
                    throw new DomainException("Injected fault after payment write to verify full rollback.", 500);

                await tx.CommitAsync(ct);
                return new Dictionary<string, object>
                {
                    ["payment_id"] = req.PaymentId,
                    ["account_id"] = req.AccountId,
                    ["amount"] = FromMinorUnits(amountMinor),
                    ["amount_minor"] = amountMinor,
                    ["direction"] = dir,
                    ["state"] = "SETTLED",
                    ["balance"] = FromMinorUnits(newBalanceMinor),
                    ["balance_minor"] = newBalanceMinor,
                    ["idempotent_replay"] = false
                };
            }
            catch
            {
                await tx.RollbackAsync(ct);
                throw;
            }
        }
        finally
        {
            WriteGate.Release();
        }
    }

    public async Task<Dictionary<string, object>> ReversePaymentAsync(string paymentId, ReversePaymentRequest req, string actorRole, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if (actorRole is not "treasurer")
            throw new DomainException($"Role '{actorRole}' is denied from reversing payments (requires treasurer).", 403);
        if (string.IsNullOrWhiteSpace(req.ReversalIdempotencyKey))
            throw new DomainException("ReversalIdempotencyKey is required.", 422);

        await WriteGate.WaitAsync(ct);
        try
        {
            await using var conn = await OpenConnectionAsync(ct);
            await using var tx = await conn.BeginTransactionAsync(ct);
            try
            {
                string accountId;
                string direction;
                long amountMinor;
                string state;
                string? existingRevKey;

                await using (var pCmd = conn.CreateCommand())
                {
                    pCmd.Transaction = (SqliteTransaction)tx;
                    pCmd.CommandText = "SELECT account_id, direction, amount_minor, state, reversal_idempotency_key FROM payments WHERE payment_id = $pid;";
                    pCmd.Parameters.AddWithValue("$pid", paymentId);
                    await using var r = await pCmd.ExecuteReaderAsync(ct);
                    if (!await r.ReadAsync(ct))
                        throw new DomainException($"Payment '{paymentId}' not found.", 404);
                    accountId = r.GetString(0);
                    direction = r.GetString(1);
                    amountMinor = r.GetInt64(2);
                    state = r.GetString(3);
                    existingRevKey = r.IsDBNull(4) ? null : r.GetString(4);
                }

                var reversalSignedDelta = direction == "CREDIT" ? -amountMinor : amountMinor;

                if (state == "REVERSED")
                {
                    if (string.Equals(existingRevKey, req.ReversalIdempotencyKey, StringComparison.Ordinal))
                    {
                        long curBal;
                        await using (var bCmd = conn.CreateCommand())
                        {
                            bCmd.Transaction = (SqliteTransaction)tx;
                            bCmd.CommandText = "SELECT balance_minor FROM accounts WHERE account_id = $aid;";
                            bCmd.Parameters.AddWithValue("$aid", accountId);
                            curBal = Convert.ToInt64(await bCmd.ExecuteScalarAsync(ct), CultureInfo.InvariantCulture);
                        }
                        await tx.CommitAsync(ct);
                        return new Dictionary<string, object>
                        {
                            ["payment_id"] = paymentId,
                            ["account_id"] = accountId,
                            ["state"] = "REVERSED",
                            ["reversal_idempotency_key"] = req.ReversalIdempotencyKey,
                            ["reversal_delta_minor"] = reversalSignedDelta,
                            ["balance"] = FromMinorUnits(curBal),
                            ["balance_minor"] = curBal,
                            ["idempotent_replay"] = true
                        };
                    }
                    throw new DomainException($"Payment '{paymentId}' is already REVERSED with a different reversal key.", 409);
                }

                if (state != "SETTLED")
                    throw new DomainException($"Payment '{paymentId}' is in state '{state}' and cannot be reversed.", 409);

                var now = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);
                var reasonText = string.IsNullOrWhiteSpace(req.Reason) ? "Unspecified" : req.Reason.Trim();

                await using (var updCmd = conn.CreateCommand())
                {
                    updCmd.Transaction = (SqliteTransaction)tx;
                    updCmd.CommandText = """
                        UPDATE payments
                        SET state = 'REVERSED', reversal_idempotency_key = $rik, reversed_at_utc = $now
                        WHERE payment_id = $pid AND state = 'SETTLED';
                        UPDATE accounts SET balance_minor = balance_minor + $delta, version = version + 1, updated_at_utc = $now WHERE account_id = $aid;
                        INSERT INTO ledger_entries (account_id, payment_id, entry_kind, signed_amount_minor, created_at_utc)
                        VALUES ($aid, $pid, 'REVERSAL', $delta, $now);
                        INSERT INTO audit_trail (entity_id, action, actor_role, details, created_at_utc)
                        VALUES ($pid, 'PAYMENT_REVERSED', $role, $reason, $now);
                        """;
                    updCmd.Parameters.AddWithValue("$now", now);
                    updCmd.Parameters.AddWithValue("$rik", req.ReversalIdempotencyKey);
                    updCmd.Parameters.AddWithValue("$pid", paymentId);
                    updCmd.Parameters.AddWithValue("$delta", reversalSignedDelta);
                    updCmd.Parameters.AddWithValue("$aid", accountId);
                    updCmd.Parameters.AddWithValue("$role", actorRole);
                    updCmd.Parameters.AddWithValue("$reason", reasonText);
                    await updCmd.ExecuteNonQueryAsync(ct);
                }

                if (req.InjectFault)
                    throw new DomainException("Injected fault during reversal to verify atomic rollback.", 500);

                long finalBal;
                await using (var bCmd = conn.CreateCommand())
                {
                    bCmd.Transaction = (SqliteTransaction)tx;
                    bCmd.CommandText = "SELECT balance_minor FROM accounts WHERE account_id = $aid;";
                    bCmd.Parameters.AddWithValue("$aid", accountId);
                    finalBal = Convert.ToInt64(await bCmd.ExecuteScalarAsync(ct), CultureInfo.InvariantCulture);
                }

                await tx.CommitAsync(ct);
                return new Dictionary<string, object>
                {
                    ["payment_id"] = paymentId,
                    ["account_id"] = accountId,
                    ["state"] = "REVERSED",
                    ["reversal_idempotency_key"] = req.ReversalIdempotencyKey,
                    ["reversal_delta_minor"] = reversalSignedDelta,
                    ["balance"] = FromMinorUnits(finalBal),
                    ["balance_minor"] = finalBal,
                    ["idempotent_replay"] = false
                };
            }
            catch
            {
                await tx.RollbackAsync(ct);
                throw;
            }
        }
        finally
        {
            WriteGate.Release();
        }
    }

    public async Task<Dictionary<string, object>> ReconcileAccountAsync(string accountId, string actorRole, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if (actorRole is not ("operator" or "treasurer" or "auditor"))
            throw new DomainException($"Role '{actorRole}' is denied from reconciling accounts.", 403);
        await using var conn = await OpenConnectionAsync(ct);
        long balanceMinor;
        long version;
        await using (var accCmd = conn.CreateCommand())
        {
            accCmd.CommandText = "SELECT balance_minor, version FROM accounts WHERE account_id = $aid;";
            accCmd.Parameters.AddWithValue("$aid", accountId);
            await using var r = await accCmd.ExecuteReaderAsync(ct);
            if (!await r.ReadAsync(ct))
                throw new DomainException($"Account '{accountId}' not found.", 404);
            balanceMinor = r.GetInt64(0);
            version = r.GetInt64(1);
        }

        long ledgerSumMinor;
        long ledgerCount;
        await using (var lCmd = conn.CreateCommand())
        {
            lCmd.CommandText = "SELECT COALESCE(SUM(signed_amount_minor), 0), COUNT(*) FROM ledger_entries WHERE account_id = $aid;";
            lCmd.Parameters.AddWithValue("$aid", accountId);
            await using var r = await lCmd.ExecuteReaderAsync(ct);
            await r.ReadAsync(ct);
            ledgerSumMinor = r.GetInt64(0);
            ledgerCount = r.GetInt64(1);
        }

        return new Dictionary<string, object>
        {
            ["account_id"] = accountId,
            ["balance"] = FromMinorUnits(balanceMinor),
            ["balance_minor"] = balanceMinor,
            ["ledger_sum"] = FromMinorUnits(ledgerSumMinor),
            ["ledger_sum_minor"] = ledgerSumMinor,
            ["ledger_entry_count"] = ledgerCount,
            ["version"] = version,
            ["reconciled"] = balanceMinor == ledgerSumMinor
        };
    }

    private static async Task<int> GetSchemaVersionInTxAsync(SqliteConnection conn, SqliteTransaction tx, CancellationToken ct)
    {
        await using var cmd = conn.CreateCommand();
        cmd.Transaction = tx;
        cmd.CommandText = "SELECT version FROM schema_meta WHERE id = 1;";
        var res = await cmd.ExecuteScalarAsync(ct);
        return Convert.ToInt32(res, CultureInfo.InvariantCulture);
    }

    public void Dispose() { }
}

public static class Program
{
    public static WebApplication BuildApp(string dbPath, int port = 0)
    {
        var builder = WebApplication.CreateBuilder();
        builder.Logging.ClearProviders();
        builder.Configuration["DatabasePath"] = dbPath;
        builder.Services.AddScoped<ScopedTransactionStore>();
        builder.WebHost.UseUrls($"http://127.0.0.1:{port}");

        var app = builder.Build();

        app.Use(async (ctx, next) =>
        {
            try
            {
                await next();
            }
            catch (DomainException dex)
            {
                ctx.Response.StatusCode = dex.StatusCode;
                ctx.Response.ContentType = "application/problem+json";
                await ctx.Response.WriteAsJsonAsync(new
                {
                    type = "https://kirion-forge.local/problems/domain-violation",
                    title = "Transaction Engine Domain Violation",
                    status = dex.StatusCode,
                    detail = dex.Message
                });
            }
        });

        static string RequireActorRole(HttpContext http)
        {
            var role = http.Request.Headers["X-Actor-Role"].FirstOrDefault()?.Trim();
            if (string.IsNullOrEmpty(role))
                throw new DomainException("Missing X-Actor-Role authentication header.", 401);
            return role;
        }

        app.MapGet("/health", async (ScopedTransactionStore store, CancellationToken ct) =>
            Results.Ok(new { status = "ok", schema_version = await store.GetSchemaVersionAsync(ct) }));

        app.MapPost("/api/v1/accounts", async (CreateAccountRequest req, HttpContext http, ScopedTransactionStore store, CancellationToken ct) =>
        {
            var role = RequireActorRole(http);
            return Results.Created($"/api/v1/reconcile/{req.AccountId}", await store.CreateAccountAsync(req, role, ct));
        });

        app.MapPost("/api/v1/payments", async (PostPaymentRequest req, HttpContext http, ScopedTransactionStore store, CancellationToken ct) =>
        {
            var role = RequireActorRole(http);
            return Results.Ok(await store.PostPaymentAsync(req, role, ct));
        });

        app.MapPost("/api/v1/payments/{paymentId}/reverse", async (string paymentId, ReversePaymentRequest req, HttpContext http, ScopedTransactionStore store, CancellationToken ct) =>
        {
            var role = RequireActorRole(http);
            return Results.Ok(await store.ReversePaymentAsync(paymentId, req, role, ct));
        });

        app.MapGet("/api/v1/reconcile/{accountId}", async (string accountId, HttpContext http, ScopedTransactionStore store, CancellationToken ct) =>
        {
            var role = RequireActorRole(http);
            return Results.Ok(await store.ReconcileAccountAsync(accountId, role, ct));
        });

        return app;
    }

    private static int _assertionsExecuted;

    private static void AssertTrue(bool condition, string label)
    {
        if (!condition)
            throw new InvalidOperationException($"ASSERTION FAILED: {label}");
        Interlocked.Increment(ref _assertionsExecuted);
    }

    public static async Task<int> Main(string[] args)
    {
        if (args.Length >= 3 && args[0] == "--serve")
        {
            var port = int.Parse(args[1], CultureInfo.InvariantCulture);
            var dbPath = args[2];
            await using var serveApp = BuildApp(dbPath, port);
            using (var scope = serveApp.Services.CreateScope())
            {
                var store = scope.ServiceProvider.GetRequiredService<ScopedTransactionStore>();
                await store.MigrateV1ToV2Async(CancellationToken.None);
            }
            await serveApp.RunAsync();
            return 0;
        }

        // Default or --self-test: run complete Benchmark B real HTTP + SQLite WAL qualification suite
        var tempDb = Path.Combine(Path.GetTempPath(), $"kirion_bench_b_{Guid.NewGuid():N}.sqlite");
        try
        {
            await using (var app = BuildApp(tempDb, 0))
            {
                // 1. Verify Scoped lifetime isolation and CancellationToken propagation
                using (var scope1 = app.Services.CreateScope())
                using (var scope2 = app.Services.CreateScope())
                {
                    var s1 = scope1.ServiceProvider.GetRequiredService<ScopedTransactionStore>();
                    var s2 = scope2.ServiceProvider.GetRequiredService<ScopedTransactionStore>();
                    AssertTrue(s1.ScopeInstanceId != s2.ScopeInstanceId, "Scoped lifetime isolates store instances across scopes");

                    using var cts = new CancellationTokenSource();
                    cts.Cancel();
                    var cancelledThrown = false;
                    try
                    {
                        await s1.GetSchemaVersionAsync(cts.Token);
                    }
                    catch (OperationCanceledException)
                    {
                        cancelledThrown = true;
                    }
                    AssertTrue(cancelledThrown, "Cancelled CancellationToken throws OperationCanceledException");

                    // 2. Seed on Schema V1, then upgrade V1 -> V2 and verify fixture preservation
                    await s1.InitSchemaV1Async(CancellationToken.None);
                    AssertTrue(await s1.GetSchemaVersionAsync(CancellationToken.None) == 1, "Schema V1 initialized");
                    await s1.CreateAccountAsync(new CreateAccountRequest("ACC-100", "PHP", 1000.00m), "treasurer", CancellationToken.None);
                    var migratedVer = await s1.MigrateV1ToV2Async(CancellationToken.None);
                    AssertTrue(migratedVer == 2, "Schema migrated V1 -> V2");

                    // Insert matching genesis ledger entry for V1 pre-seeded account
                    await using var conn = new SqliteConnection($"Data Source={tempDb};Pooling=False");
                    await conn.OpenAsync();
                    await using var seedLedger = conn.CreateCommand();
                    seedLedger.CommandText = """
                        INSERT INTO payments (payment_id, account_id, idempotency_key, direction, amount_minor, currency, state, created_at_utc)
                        VALUES ('INIT-ACC-100', 'ACC-100', 'IK-INIT-100', 'CREDIT', 100000, 'PHP', 'SETTLED', '2026-11-19T00:00:00Z');
                        INSERT INTO ledger_entries (account_id, payment_id, entry_kind, signed_amount_minor, created_at_utc)
                        VALUES ('ACC-100', 'INIT-ACC-100', 'PAYMENT', 100000, '2026-11-19T00:00:00Z');
                        """;
                    await seedLedger.ExecuteNonQueryAsync();
                }

                await app.StartAsync();
                var address = app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.First();
                using var client = new HttpClient { BaseAddress = new Uri(address) };

                // 3. Unauthenticated (missing header -> 401) and role denial (403) checks over real HTTP
                using (var unauthMsg = new HttpRequestMessage(HttpMethod.Post, "/api/v1/payments"))
                {
                    unauthMsg.Content = JsonContent.Create(new PostPaymentRequest("ACC-100", "PAY-UNAUTH", "IK-UNAUTH", 10.00m, "PHP", "CREDIT"));
                    var unauthResp = await client.SendAsync(unauthMsg);
                    AssertTrue(unauthResp.StatusCode == HttpStatusCode.Unauthorized, "Missing X-Actor-Role fails closed with 401 Unauthorized");
                }

                using (var deniedRec = new HttpRequestMessage(HttpMethod.Get, "/api/v1/reconcile/ACC-100"))
                {
                    deniedRec.Headers.Add("X-Actor-Role", "guest");
                    var deniedRecResp = await client.SendAsync(deniedRec);
                    AssertTrue(deniedRecResp.StatusCode == HttpStatusCode.Forbidden, "Guest role denied from reconcile endpoint (403)");
                }

                using (var deniedMsg = new HttpRequestMessage(HttpMethod.Post, "/api/v1/payments"))
                {
                    deniedMsg.Headers.Add("X-Actor-Role", "auditor");
                    deniedMsg.Content = JsonContent.Create(new PostPaymentRequest("ACC-100", "PAY-DENIED", "IK-DENIED", 10.00m, "PHP", "CREDIT"));
                    var deniedResp = await client.SendAsync(deniedMsg);
                    AssertTrue(deniedResp.StatusCode == HttpStatusCode.Forbidden, "Auditor denied from posting payment (403)");
                }

                // 4. Scale validation (>2 decimals rejected with 422)
                using (var scaleMsg = new HttpRequestMessage(HttpMethod.Post, "/api/v1/payments"))
                {
                    scaleMsg.Headers.Add("X-Actor-Role", "operator");
                    scaleMsg.Content = JsonContent.Create(new PostPaymentRequest("ACC-100", "PAY-SCALE", "IK-SCALE", 10.129m, "PHP", "CREDIT"));
                    var scaleResp = await client.SendAsync(scaleMsg);
                    AssertTrue((int)scaleResp.StatusCode == 422, "Invalid 3-decimal amount scale rejected with 422");
                }

                // 5. Ten repeated same-key requests over real HTTP -> exactly-once effect
                var sameKeyTasks = Enumerable.Range(0, 10).Select(async _ =>
                {
                    using var msg = new HttpRequestMessage(HttpMethod.Post, "/api/v1/payments");
                    msg.Headers.Add("X-Actor-Role", "operator");
                    msg.Content = JsonContent.Create(new PostPaymentRequest("ACC-100", "PAY-SAME-01", "IK-SAME-01", 150.25m, "PHP", "CREDIT"));
                    var resp = await client.SendAsync(msg);
                    AssertTrue(resp.StatusCode == HttpStatusCode.OK, "Same-key request returned 200 OK");
                    return await resp.Content.ReadFromJsonAsync<JsonElement>();
                });
                var sameKeyResults = await Task.WhenAll(sameKeyTasks);
                AssertTrue(sameKeyResults.Length == 10, "10 same-key responses received");

                // 6. Five concurrent distinct payment requests over real HTTP
                var distinctAmounts = new[] { 10.00m, 20.00m, 30.00m, 40.00m, 50.00m };
                var distinctTasks = distinctAmounts.Select(async (amt, idx) =>
                {
                    using var msg = new HttpRequestMessage(HttpMethod.Post, "/api/v1/payments");
                    msg.Headers.Add("X-Actor-Role", "operator");
                    msg.Content = JsonContent.Create(new PostPaymentRequest("ACC-100", $"PAY-CONC-{idx}", $"IK-CONC-{idx}", amt, "PHP", "CREDIT"));
                    var resp = await client.SendAsync(msg);
                    AssertTrue(resp.StatusCode == HttpStatusCode.OK, $"Concurrent payment {idx} succeeded");
                });
                await Task.WhenAll(distinctTasks);

                // 7. Injected fault leaves zero partial changes
                using (var faultMsg = new HttpRequestMessage(HttpMethod.Post, "/api/v1/payments"))
                {
                    faultMsg.Headers.Add("X-Actor-Role", "operator");
                    faultMsg.Content = JsonContent.Create(new PostPaymentRequest("ACC-100", "PAY-FAULT", "IK-FAULT", 999.00m, "PHP", "CREDIT", InjectFault: true));
                    var faultResp = await client.SendAsync(faultMsg);
                    AssertTrue(faultResp.StatusCode == HttpStatusCode.InternalServerError, "Injected fault returns 500");
                }

                // 8. Reversal semantics: operator denied (403), treasurer succeeds once (200), repeat reversal denied (409)
                using (var revDenied = new HttpRequestMessage(HttpMethod.Post, "/api/v1/payments/PAY-CONC-4/reverse"))
                {
                    revDenied.Headers.Add("X-Actor-Role", "operator");
                    revDenied.Content = JsonContent.Create(new ReversePaymentRequest("REV-IK-1", "Duplicate charge"));
                    var r = await client.SendAsync(revDenied);
                    AssertTrue(r.StatusCode == HttpStatusCode.Forbidden, "Operator cannot reverse payment (403)");
                }

                using (var revOk = new HttpRequestMessage(HttpMethod.Post, "/api/v1/payments/PAY-CONC-4/reverse"))
                {
                    revOk.Headers.Add("X-Actor-Role", "treasurer");
                    revOk.Content = JsonContent.Create(new ReversePaymentRequest("REV-IK-1", "Authorized reversal of 50.00"));
                    var r = await client.SendAsync(revOk);
                    AssertTrue(r.StatusCode == HttpStatusCode.OK, "Treasurer reversed 50.00 payment (200)");
                }

                // Same reversal idempotency key -> idempotent 200 OK replay without double debit
                using (var revReplay = new HttpRequestMessage(HttpMethod.Post, "/api/v1/payments/PAY-CONC-4/reverse"))
                {
                    revReplay.Headers.Add("X-Actor-Role", "treasurer");
                    revReplay.Content = JsonContent.Create(new ReversePaymentRequest("REV-IK-1", "Authorized reversal of 50.00"));
                    var r = await client.SendAsync(revReplay);
                    AssertTrue(r.StatusCode == HttpStatusCode.OK, "Same-key reversal retry returns idempotent 200 OK");
                    var body = await r.Content.ReadFromJsonAsync<JsonElement>();
                    AssertTrue(body.GetProperty("idempotent_replay").GetBoolean(), "Same-key reversal sets idempotent_replay=true");
                }

                // Distinct reversal key on already-reversed payment -> 409 Conflict
                using (var revDup = new HttpRequestMessage(HttpMethod.Post, "/api/v1/payments/PAY-CONC-4/reverse"))
                {
                    revDup.Headers.Add("X-Actor-Role", "treasurer");
                    revDup.Content = JsonContent.Create(new ReversePaymentRequest("REV-IK-2", "Second reversal attempt"));
                    var r = await client.SendAsync(revDup);
                    AssertTrue(r.StatusCode == HttpStatusCode.Conflict, "Distinct reversal key rejected with 409 Conflict");
                }

                await app.StopAsync();
            }

            // 9. Durable restart verification: start a new WebApplication instance on the same SQLite WAL database
            await using (var restartedApp = BuildApp(tempDb, 0))
            {
                await restartedApp.StartAsync();
                var addr2 = restartedApp.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.First();
                using var client2 = new HttpClient { BaseAddress = new Uri(addr2) };
                using var recReq = new HttpRequestMessage(HttpMethod.Get, "/api/v1/reconcile/ACC-100");
                recReq.Headers.Add("X-Actor-Role", "auditor");
                var recResp = await client2.SendAsync(recReq);
                AssertTrue(recResp.StatusCode == HttpStatusCode.OK, "Auditor can reconcile persisted account after restart");
                var rec = await recResp.Content.ReadFromJsonAsync<JsonElement>();
                var balanceMinor = rec.GetProperty("balance_minor").GetInt64();
                var ledgerSumMinor = rec.GetProperty("ledger_sum_minor").GetInt64();
                var reconciled = rec.GetProperty("reconciled").GetBoolean();
                var entryCount = rec.GetProperty("ledger_entry_count").GetInt64();

                // Expected: 100000 (init) + 15025 (10x same-key) + 15000 (10+20+30+40+50) - 5000 (reversal of 50) = 125025 minor units (1250.25 PHP)
                AssertTrue(reconciled, "Persisted account balance reconciles with ledger entries after restart");
                AssertTrue(balanceMinor == 125025, $"Expected balance_minor 125025, got {balanceMinor}");
                AssertTrue(ledgerSumMinor == 125025, $"Expected ledger_sum_minor 125025, got {ledgerSumMinor}");
                AssertTrue(entryCount == 8, $"Expected 8 ledger entries (1 init + 1 same-key + 5 concurrent + 1 reversal), got {entryCount}");

                await restartedApp.StopAsync();
            }

            Console.WriteLine(JsonSerializer.Serialize(new
            {
                benchmark = "B_ASPNET_CSHARP_TRANSACTION_ENGINE",
                status = "PASS",
                assertions_verified = _assertionsExecuted,
                final_balance_minor = 125025,
                final_balance_decimal = 1250.25m,
                ledger_entries_verified = 8,
                reconciled = true
            }, new JsonSerializerOptions { WriteIndented = true }));
            return 0;
        }
        finally
        {
            SqliteConnection.ClearAllPools();
            try { if (File.Exists(tempDb)) File.Delete(tempDb); } catch { }
            try { if (File.Exists(tempDb + "-wal")) File.Delete(tempDb + "-wal"); } catch { }
            try { if (File.Exists(tempDb + "-shm")) File.Delete(tempDb + "-shm"); } catch { }
        }
    }
}
