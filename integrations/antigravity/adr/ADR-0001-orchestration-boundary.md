# ADR-0001: Native Antigravity vs Deterministic Python Orchestration

- **Status:** ACCEPTED FOR R1 FACTORY CANDIDATE
- **Mission:** `F00` (`FORGE-ANTIGRAVITY-F00-FOUNDATION-R1`)
- **Date:** `2026-11-19`

## Context
F00 host capability probes proved that:
1. Antigravity 2.0 provides native `run_workflow` (dynamic Python workflows with `agent(prompt, schema, role, type_name, workspace, model)`, `parallel`, `pipeline`, `phase`) and `invoke_subagent` (`self`, `research`, `browser`, custom defined agents), plus Language Server plugin discovery (`GetAllPlugins`).
2. Neither the standalone `agy` CLI nor the PyPI `google-antigravity` package is installed on the host Python (`3.13.5`).
3. Native LLM agents cannot be sole custodians of immutable SHA checks, DAG cycle detection, lease locks, budget counters, or remote GitHub push enforcement.

## Decision
1. **Deterministic Python Control Plane (`integrations/antigravity/factory/`):**
   - Owns mission verification (`authority.py`), deny-by-default policy (`policy.py`), DAG scheduling and budgets (`scheduler.py`), path/module lease locking and worktree management (`ownership.py`), append-only SQLite WAL journaling (`recovery.py`), trusted command execution and evidence envelopes (`evidence.py`, `quality.py`), knowledge crosswalk mapping (`knowledge.py`), and verified `Kirch-Nairu` delivery (`delivery.py`).
   - Uses only the Python 3.13 standard library (`sqlite3`, `hashlib`, `subprocess`, `json`, `urllib.request`, `pathlib`) for zero fragile external Python dependencies.
2. **Native Antigravity Execution Plane (`integrations/antigravity/plugins/kirion-forge/` & `workflows/`):**
   - Provides the native plugin bundle (`plugin.json`, `rules/AGENTS.md`, `hooks.json`, `agents/*.md`, `skills/*/SKILL.md`).
   - Invokes isolated agent contexts via `run_workflow` / `invoke_subagent` (specifically `type_name="research"` for read-only fresh-context `Antigravity-Nox` and `Antigravity-Aegis` reviews, and isolated worktree lanes for `Antigravity-Jane`, `Antigravity-Lucien`, `Antigravity-Argon`, `Antigravity-Iris`, `Antigravity-QA`, `Antigravity-Integrator`, `Antigravity-Scribe`).
   - Degrades gracefully to sequential deterministic handoffs when running in headless CI or when model quota is constrained.

## Consequences
- Every safety invariant (exact SHA, path ownership, lease expiry, budget ceiling, gate exit code, remote actor identity) is enforced deterministically in Python and verified by unit/integration tests.
- Native Antigravity subagents and `run_workflow` scripts consume and emit schema-validated JSON payloads verified by the deterministic control plane.
