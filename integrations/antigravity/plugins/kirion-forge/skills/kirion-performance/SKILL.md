---
name: kirion-performance
description: Use this skill for query plan inspection, N+1 query detection, memory allocation discipline, bounded batching, and Core Web Vitals performance budgets.
---

# Kirion Performance Engineering Specialization (`kirion-performance`)

## 1. Versioned Official References
- Web Vitals (LCP <= 2.5s, INP <= 200ms, CLS <= 0.1): `https://web.dev/articles/vitals`
- SQLite EXPLAIN QUERY PLAN: `https://www.sqlite.org/eqp.html`

## 2. Concrete Workflow
1. Record baseline latency, query count, and payload size before optimizing; always report the measured environment alongside metrics.
2. Eliminate N+1 queries by asserting bounded SQL query counts per request (`query_count <= 3` for list endpoints regardless of row count).
3. Stream or paginate large result sets and use `AsNoTracking()` (EF Core) or indexed cursor queries for read-only reporting endpoints.

## 3. Canonical Example
```sql
EXPLAIN QUERY PLAN
SELECT id, po_number, status, total_minor
FROM purchase_orders
WHERE tenant_id = 1
ORDER BY id DESC
LIMIT 25;
-- Expected: SEARCH purchase_orders USING INDEX idx_po_tenant_id (tenant_id=?)
```

## 4. Validation Commands
```bash
python -m unittest discover -s integrations/antigravity/tests -v
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (Per-Row Query inside Loop):** Executing `SELECT * FROM line_items WHERE po_id = ?` inside a `foreach ($orders as $order)` loop (`LARAVEL-N-PLUS-1`).
- **Negative Case 2 (Unmeasured Performance Claim):** Claiming "4x faster" or "sub-10ms" without a recorded baseline, target command, and environment envelope.

## 6. Tests & Qualification Evidence
- Verified in Benchmark A (query count assertions) and Benchmark C (`LARAVEL-N-PLUS-1` detection and repair).
