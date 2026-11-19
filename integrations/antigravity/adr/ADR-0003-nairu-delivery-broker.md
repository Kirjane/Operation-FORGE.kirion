# ADR-0003: Nairu Delivery Broker and Verified Actor Gateway

- **Status:** ACCEPTED FOR R1 FACTORY CANDIDATE
- **Mission:** `F00` (`FORGE-ANTIGRAVITY-F00-FOUNDATION-R1`)
- **Date:** `2026-11-19`

## Context
In Operation Forge, logical personas (`Antigravity-Maintainer`, `Antigravity-Lucien`, `Antigravity-Jane`, `Antigravity-Nox`, `Antigravity-Argon`, `Antigravity-Iris`, `Antigravity-QA`, `Antigravity-Aegis`, `Antigravity-Integrator`, `Antigravity-Scribe`) are execution roles, not separate GitHub user accounts. All remote GitHub writes on this host use the authenticated `Kirch-Nairu` account (`id: 291564617`). Workers must never embed PATs, impersonate independent human acceptance, or perform merges, force pushes, ref deletions, or production releases.

## Decision
1. **Verified Actor Precheck (`factory/delivery.py`):**
   - Before any remote operation, the broker executes `gh api user` (or uses an injected test verifier in offline qualification) and verifies `login == "Kirch-Nairu"` and `id == 291564617`. Any mismatch or unauthenticated state fails closed (`BLOCKED`).
2. **Pre-Push Diff & Ancestor Audit:**
   - The broker verifies that the candidate commit descends from the mission's `base_sha` without history rewrite, that the target branch matches `permitted_branch` (never `main` or `master`), that every changed file (`git diff --name-status base_sha..candidate_sha`) falls within the mission's `owned_paths`, and that no protected governance files or symlinks were added or deleted outside scope.
3. **Allowed vs Prohibited Remote Operations:**
   - **Allowed:** Non-force branch push (`git push origin <candidate_branch>`) and draft PR creation/update (`gh pr create --draft` / `gh pr edit` / `gh pr comment`) with structured `START`/`CLOSE` receipts, logical persona disclosure, exact SHA, evidence manifest digest, and explicit limitations.
   - **Prohibited (Hard-Blocked):** `gh pr merge`, `git push --force`, `git push --delete`, branch protection/ruleset edits, release creation, workflow secret read/write, and self-approval (`gh pr review --approve`).
4. **Idempotent Delivery Key:**
   - Each delivery attempt computes `delivery_key = sha256(mission_id + ":" + permitted_branch + ":" + candidate_sha)` and records it in the SQLite WAL journal before and after remote receipt so interrupted deliveries reconcile read-only without duplicate PR creation.

## Consequences
- Remote submissions truthfully disclose `Kirch-Nairu` as the authenticated GitHub actor while attributing logical persona work and fresh-context `Antigravity-Nox` review in the structured evidence receipt.
- Independent acceptance and promotion remain strictly reserved for a separate non-author session/Engineer decision.
