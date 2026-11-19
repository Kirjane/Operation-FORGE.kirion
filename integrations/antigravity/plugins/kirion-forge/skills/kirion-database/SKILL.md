---
name: kirion-database
description: Use this skill for relational schema design, constraints, indexes, forward/upgrade migrations, data preservation verification, and ledger reconciliation.
---

# Kirion Database Engineering Specialization (`kirion-database`)

## 1. Versioned Official References
- SQLite Foreign Keys, Check Constraints, and WAL: `https://www.sqlite.org/foreignkeys.html`
- PostgreSQL Constraints & Transactional DDL: `https://www.postgresql.org/docs/current/ddl-constraints.html`

## 2. Concrete Workflow
1. Enforce data integrity in the schema itself: `NOT NULL`, `FOREIGN KEY`, `UNIQUE` constraints on natural/idempotency keys, and `CHECK` constraints on monetary and quantity columns (`amount_minor >= 0`, `received_qty <= ordered_qty`).
2. Index every foreign key, tenant discriminator (`(tenant_id, id)`), and frequent filter/sort predicate.
3. Verify migrations both from an empty database (fresh install) and from a pre-seeded prior schema version (retained upgrade), asserting exact row and balance preservation.
4. Recompute aggregate balances directly from immutable ledger/receipt line items to verify reconciliation invariants.

## 3. Canonical Example
```sql
CREATE TABLE IF NOT EXISTS ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    tx_id TEXT NOT NULL UNIQUE,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('CREDIT', 'DEBIT', 'REVERSAL')),
    signed_amount_minor INTEGER NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);
CREATE INDEX IF NOT EXISTS idx_ledger_account ON ledger_entries(account_id, id);
```

## 4. Validation Commands
```bash
python -m unittest discover -s integrations/antigravity/tests -v
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Destructive Upgrade Migration):** Dropping and recreating a table during a schema upgrade (`DROP TABLE accounts`), destroying retained customer data (`MIGRATION-DATA-LOSS`).
- **Negative Case 2 (Unreconciled Header Total):** Updating a cached balance column without writing the corresponding immutable ledger row.

## 6. Tests & Qualification Evidence
- Verified in Benchmark A and Benchmark B (schema v1 → v2 upgrade preserving seeded fixtures + independent oracle ledger recomputation).
