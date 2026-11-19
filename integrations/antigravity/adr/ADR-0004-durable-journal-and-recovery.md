# ADR-0004: SQLite WAL Durable Event Journal and Crash Recovery

- **Status:** ACCEPTED FOR R1 FACTORY CANDIDATE
- **Mission:** `F00` (`FORGE-ANTIGRAVITY-F00-FOUNDATION-R1`)
- **Date:** `2026-11-19`

## Context
Autonomous multi-stage software factory runs must survive process termination before/after local commits, before/after remote broker receipts, stale leases, quota exhaustion, and hook failures without losing evidence or duplicating remote mutations. F00 verified Python 3.13.5 stdlib `sqlite3` (`3.49.1`) supports `PRAGMA journal_mode=WAL` with ACID transactions.

## Decision
1. **Append-Only Event Stream (`integrations/antigravity/factory/scheduler.py` & `recovery.py`):**
   - Stored in a local SQLite WAL database (`journal.db`) with tables:
     - `missions` (`mission_id`, `run_id`, `state`, `state_version`, `base_sha`, `candidate_sha`, `packet_json`, `updated_at_utc`)
     - `journal_events` (`seq INTEGER PRIMARY KEY AUTOINCREMENT`, `event_id TEXT UNIQUE`, `mission_id`, `run_id`, `stage`, `event_type`, `state_version`, `payload_json`, `payload_sha256`, `prev_event_sha256`, `created_at_utc`)
     - `leases` (`lease_key PRIMARY KEY`, `mission_id`, `worker_id`, `version`, `expires_at_utc`, `released`)
     - `delivery_receipts` (`delivery_key PRIMARY KEY`, `mission_id`, `candidate_sha`, `branch`, `status`, `remote_ref`, `updated_at_utc`)
2. **Hash-Chained Tamper Evidence & Compare-and-Set (CAS):**
   - Every state transition updates `state_version = state_version + 1` via `WHERE mission_id = ? AND state_version = ?`. Concurrent or stale transitions fail closed.
   - Each `journal_events` row chains `prev_event_sha256` to form an auditable tamper-evident log.
3. **Content-Addressed Artifact Store & Secret Redaction:**
   - Gate logs, diffs, and receipts are redacted for token patterns (`ghp_`, `gho_`, `github_pat_`, `Bearer `, `ANTIGRAVITY_CSRF_TOKEN`) before persistence and stored by SHA-256 digest (`artifacts/<sha256[:2]>/<sha256>.blob`).
4. **Crash Recovery & Sandbox Capsules (`factory/recovery.py`):**
   - On startup or recovery, the recovery engine inspects the SQLite WAL journal, verifies current Git HEAD and dirty status, checks `delivery_receipts` against remote state read-only before retrying any delivery, reclaims expired leases only after explicit reconciliation, and emits a canonical Forge Sandbox Capsule (`schemas/sandbox-capsule.schema.json` compatible) for successor handoff.

## Consequences
- Orchestrator kills at any boundary (pre-commit, post-commit, pre-broker, post-broker) are deterministically recoverable across 3+ repeated trials (Benchmark D) with zero duplicate remote writes.
