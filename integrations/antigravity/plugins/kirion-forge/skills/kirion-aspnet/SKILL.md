---
name: kirion-aspnet
description: Use this skill for ASP.NET Core 10.0 Web APIs, DI service lifetime hygiene, policy/role authorization, RFC 9457 Problem Details, idempotency middleware, and real HTTP integration testing.
---

# Kirion ASP.NET Core Specialization (`kirion-aspnet`)

## 1. Versioned Official References
- ASP.NET Core Fundamentals & Dependency Injection Lifetimes: `https://learn.microsoft.com/en-us/aspnet/core/fundamentals/dependency-injection`
- ASP.NET Core Policy & Resource-Based Authorization: `https://learn.microsoft.com/en-us/aspnet/core/security/authorization/policies`
- RFC 9457 Problem Details in ASP.NET Core: `https://learn.microsoft.com/en-us/aspnet/core/web-api/handle-errors`

## 2. Concrete Workflow
1. Enforce DI lifetime hierarchy: never capture a `Scoped` service (such as `DbContext` or a unit-of-work repository) inside a `Singleton` service.
2. Require explicit authentication and role/policy authorization on every protected endpoint; return structured Problem Details (`400`, `403`, `404`, `409`, `422`) without leaking stack traces.
3. Enforce idempotency keys (`Idempotency-Key` header or command key) backed by persistent storage so repeated or concurrent identical requests execute at most once.
4. Test endpoints over real HTTP using `WebApplicationFactory<TEntryPoint>` or a live Kestrel socket bound to an ephemeral loopback port.

## 3. Canonical Example
```csharp
app.MapPost("/api/v1/payments", async (
    PaymentRequest req,
    HttpContext http,
    TransactionEngineService engine,
    CancellationToken ct) =>
{
    var role = http.Request.Headers["X-Actor-Role"].ToString();
    if (role is not ("operator" or "treasurer"))
        return Results.Problem(title: "Forbidden", detail: "Role cannot post payments.", statusCode: 403);

    var outcome = await engine.PostPaymentAsync(req, ct);
    return Results.Ok(outcome);
});
```

## 4. Validation Commands
```bash
dotnet build -c Release
dotnet test -c Release
dotnet list package --vulnerable --include-transitive
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Captive Dependency / Scoped in Singleton):** Injecting a scoped `DbContext` into a singleton cache or background processor (`DOTNET-EF-LIFETIME`), causing concurrent thread corruption and stale state.
- **Negative Case 2 (Fire-and-Forget Request Work):** Launching `Task.Run(async () => await db.SaveChangesAsync())` without awaiting or scoping, causing `ObjectDisposedException`.

## 6. Tests & Qualification Evidence
- Verified on `Microsoft.AspNetCore.App 10.0.12` in Benchmark B (real HTTP payment, reversal, and ledger engine) and Benchmark C (`DOTNET-EF-LIFETIME`).
