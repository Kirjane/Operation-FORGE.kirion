---
name: kirion-concurrency
description: Use this skill for concurrency control, idempotency keys, optimistic/pessimistic locking, deadlock avoidance, compare-and-set state versions, and race-condition testing across C# and PHP.
---

# Kirion Concurrency & Idempotency Specialization (`kirion-concurrency`)

## 1. Versioned Official References
- PostgreSQL Explicit Locking & Isolation Levels: `https://www.postgresql.org/docs/current/explicit-locking.html`
- SQLite WAL Mode & Immediate Transactions: `https://www.sqlite.org/wal.html`
- .NET Concurrency & Async Synchronization: `https://learn.microsoft.com/en-us/dotnet/standard/threading/`

## 2. Concrete Workflow
1. Require a caller-supplied or deterministic `idempotency_key` for every non-idempotent mutation (payment posting, reversal, PO approval, partial goods receipt, remote PR delivery).
2. Enforce uniqueness on `(tenant_id, idempotency_key)` in the database inside the same ACID transaction as the state transition.
3. Acquire locks in deterministic primary-key order (`ORDER BY id ASC`) or use `BEGIN IMMEDIATE` (SQLite WAL) / `SELECT ... FOR UPDATE` (PostgreSQL/MySQL) with compare-and-set version checks (`WHERE id = ? AND version = ?`).
4. Test with 10+ repeated same-key requests and controlled concurrent distinct operations to prove exactly-once effect and zero balance corruption.

## 3. Canonical Example
```python
# Compare-and-set state version transition in SQLite WAL
cur = conn.execute(
    "UPDATE missions SET state = ?, state_version = state_version + 1 "
    "WHERE mission_id = ? AND state_version = ?",
    (next_state, mission_id, expected_version),
)
if cur.rowcount != 1:
    raise ConcurrencyConflictError(f"CAS mismatch for {mission_id} at version {expected_version}")
```

## 4. Validation Commands
```bash
python -m unittest discover -s integrations/antigravity/tests -v
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Check-Then-Act Race Outside Transaction):** Checking `if (!exists(key))` before opening a transaction, allowing two concurrent requests to pass the check simultaneously (`BOTH-CONCURRENCY-RACE`).
- **Negative Case 2 (Unordered Multi-Row Lock):** Locking Account B then Account A in one request while another locks Account A then Account B, causing deadlocks.

## 6. Tests & Qualification Evidence
- Verified in Benchmark A (concurrent PO approvals), Benchmark B (10 repeated same-key requests + concurrent distinct operations), Benchmark C (`BOTH-CONCURRENCY-RACE`, `BOTH-DUPLICATE-POSTING`), and Benchmark D (lease CAS races).
