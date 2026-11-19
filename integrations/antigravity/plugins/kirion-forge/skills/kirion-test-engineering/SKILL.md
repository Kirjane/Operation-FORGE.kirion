---
name: kirion-test-engineering
description: Use this skill for contract-derived test design, discriminating regression tests, real HTTP/DB integration suites, hidden-oracle qualification, and anti-assertion-weakening enforcement.
---

# Kirion Test Engineering Specialization (`kirion-test-engineering`)

## 1. Versioned Official References
- xUnit.net & ASP.NET Core Integration Testing: `https://learn.microsoft.com/en-us/aspnet/core/test/integration-tests`
- PHPUnit / Pest Testing Documentation: `https://docs.phpunit.de/`

## 2. Concrete Workflow
1. Derive test cases directly from the accepted contract: positive path, boundary values, unauthorized role/tenant denial (`403`), duplicate idempotency replay, concurrent race, transaction rollback on injected fault, and restart/migration persistence.
2. During defect repair (F12), write a **discriminating regression test** that fails on the pre-fix defect state and passes after the root-cause fix.
3. Enforce strong assertions on persisted database state, exact integer minor-unit totals, HTTP status codes, and document bytes—never `assertTrue(true)` or status-only checks that ignore corrupted data.

## 3. Canonical Example
```python
# Discriminating assertion verifying exact persisted balance and ledger sum
assert account_balance_minor == expected_balance_minor
assert ledger_sum_minor == account_balance_minor
assert http_status == 200
```

## 4. Validation Commands
```bash
python -m unittest discover -s integrations/antigravity/tests -v
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Weak Assertion):** Asserting `response.status_code < 500` or `result is not None` while ignoring that a duplicate payment doubled the ledger balance (`BOTH-WEAK-ASSERTION`).
- **Negative Case 2 (Assertion Weakening During Repair):** Changing an expected balance in a failing test to match the buggy output instead of fixing the calculation.

## 6. Tests & Qualification Evidence
- Verified across Benchmarks A, B, C (`BOTH-WEAK-ASSERTION`), D, and E.
