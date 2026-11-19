---
name: kirion-csharp
description: Use this skill for C# 12/13/14 and .NET 10.0 engineering, nullable reference types, exact decimal/minor-unit financial arithmetic, immutable records, and deterministic resource management.
---

# Kirion C# Specialization (`kirion-csharp`)

## 1. Versioned Official References
- C# Language Specification & Nullable Reference Types: `https://learn.microsoft.com/en-us/dotnet/csharp/nullable-references`
- .NET 10.0 SDK & Runtime Fundamentals: `https://learn.microsoft.com/en-us/dotnet/core/whats-new/dotnet-10/overview`
- System.Decimal Exact Arithmetic: `https://learn.microsoft.com/en-us/dotnet/api/system.decimal`

## 2. Concrete Workflow
1. Enable `<Nullable>enable</Nullable>`, `<ImplicitUsings>enable</ImplicitUsings>`, and `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` (or explicit analyzer enforcement) in `.csproj`.
2. Use `decimal` with explicit scale (`Math.Round(amount, 2, MidpointRounding.ToEven)`) or `long` minor units for all financial amounts—never `double` or `float`.
3. Model domain commands, events, and money values as immutable `readonly record struct` or `sealed record` types.
4. Propagate `CancellationToken` through every async I/O method and avoid sync-over-async (`.Result`, `.Wait()`).

## 3. Canonical Example
```csharp
namespace Kirion.Transactions.Domain;

public readonly record struct Money(decimal Amount, string Currency)
{
    public Money Normalize()
    {
        if (string.IsNullOrWhiteSpace(Currency))
            throw new ArgumentException("Currency is required.", nameof(Currency));
        return new Money(decimal.Round(Amount, 2, MidpointRounding.ToEven), Currency.ToUpperInvariant());
    }
}
```

## 4. Validation Commands
```bash
dotnet --info
dotnet build -c Release
dotnet test -c Release --no-build
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Floating-Point Money):** Using `double` for payment or ledger balances causes binary floating-point drift (`0.1 + 0.2 != 0.3`).
- **Negative Case 2 (Sync-Over-Async Deadlock):** Calling `task.Result` or `task.GetAwaiter().GetResult()` inside an async request pipeline.
- **Negative Case 3 (Incorrect Rounding Scale):** Allowing >2 decimal places or unrounded division into ledger postings without explicit scale validation.

## 6. Tests & Qualification Evidence
- Verified on `.NET SDK 10.0.401` in Benchmark B (`benchmarks/dotnet_transaction_engine/`) and Benchmark C (`BOTH-INCORRECT-ROUNDING`, `BOTH-MISSING-TRANSACTION`).
