---
name: kirion-efcore
description: Use this skill for Entity Framework Core and ADO.NET relational data access, DbContext thread confinement, explicit transactions, optimistic concurrency tokens, and schema migration verification.
---

# Kirion EF Core & Relational Data Specialization (`kirion-efcore`)

## 1. Versioned Official References
- EF Core DbContext Lifetime, Configuration, and Initialization: `https://learn.microsoft.com/en-us/ef/core/dbcontext-configuration/`
- EF Core Transactions & Optimistic Concurrency: `https://learn.microsoft.com/en-us/ef/core/saving/transactions`

## 2. Concrete Workflow
1. Scope each unit of work to a fresh `DbContext` or transactional database connection; never share a single `DbContext` instance across concurrent threads (`Task.WhenAll`).
2. Use explicit database transactions (`BeginTransactionAsync` / `CommitAsync` / `RollbackAsync`) for multi-step financial postings (account balance update + ledger entry + idempotency receipt + audit record).
3. Enforce optimistic concurrency version tokens (`Version` / `RowVersion`) or serialized SQLite WAL `BEGIN IMMEDIATE` locks to prevent lost updates under concurrent writes.
4. Test schema upgrade migrations against pre-seeded database files and verify zero balance or row corruption.

## 3. Canonical Example
```csharp
await using var tx = await connection.BeginTransactionAsync(ct);
try
{
    // Verify idempotency key inside transaction
    // Update account balance with version check
    // Insert immutable double-entry or audit ledger rows
    await tx.CommitAsync(ct);
}
catch
{
    await tx.RollbackAsync(ct);
    throw;
}
```

## 4. Validation Commands
```bash
dotnet test -c Release --filter "FullyQualifiedName~TransactionEngineTests"
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Shared DbContext Across Parallel Tasks):** Running `await Task.WhenAll(items.Select(i => dbContext.AddAsync(i)))` on one `DbContext`.
- **Negative Case 2 (In-Memory Provider Substitution):** Using an in-memory collection that ignores relational constraints, foreign keys, and transaction rollback semantics as proof of database correctness.

## 6. Tests & Qualification Evidence
- Verified in Benchmark B (atomic rollback on injected failure, restart persistence, schema upgrade preservation, and lifetime isolation) and Benchmark C.
