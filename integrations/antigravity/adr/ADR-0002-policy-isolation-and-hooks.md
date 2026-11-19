# ADR-0002: Deny-by-Default Policy Enforcement, Worktree Sandbox, and Fail-Closed Hooks

- **Status:** ACCEPTED FOR R1 FACTORY CANDIDATE
- **Mission:** `F00` (`FORGE-ANTIGRAVITY-F00-FOUNDATION-R1`)
- **Date:** `2026-11-19`

## Context
Workers executing in parallel or sequentially must not overwrite unowned files, traverse outside their workspace via symlinks or relative paths, inherit broker secrets, or bypass governance rules (`AGENTS.md`, `SYSTEM_BOUNDARY.md`, `EVIDENCE_CROSSWALK.md`, `.forge/`). Furthermore, on Windows hosts, `git config core.autocrlf=true` silently converts LF to CRLF on checkout, breaking `SHARED_DOCS.sha256` verification.

## Decision
1. **Deny-by-Default Policy (`factory/policy.py`):**
   - Every operation (`READ`, `WRITE_OWNED`, `RUN_GATE`, `REVIEW_READONLY`, `INTEGRATE_BRANCH`, `DELIVER_DRAFT_PR`) must be explicitly listed in `allowed_operations` on a verified `MissionPacket`.
   - High-risk operations (`FORCE_PUSH`, `MERGE_PR`, `DELETE_REF`, `ADMIN_MUTATION`, `PRODUCTION_DEPLOY`, `RESET_CLIENT_DATA`, `GLOBAL_PLUGIN_INSTALL`, `MODIFY_PROTECTED_GOVERNANCE`) are unconditionally denied by default.
   - Protected repository paths (`AGENTS.md`, `SYSTEM_BOUNDARY.md`, `EVIDENCE_CROSSWALK.md`, `SHARED_DOCS.sha256`, `ENTITY.md`, `ENTITY_MANIFEST.json`, `.forge/AUTHORITY.md`) are blocked from worker mutation unless a dedicated governance mission explicitly authorizes them.
2. **Worktree Isolation and Lease Manager (`factory/ownership.py`):**
   - Each writer lane runs in a dedicated `git worktree` initialized with `git config core.autocrlf false` at the frozen base SHA.
   - Leases are keyed by `(repo, canonical_target)` across path prefixes, module namespaces, and shared surfaces (schemas, lockfiles, migrations, CI, auth), with TTL expiry, heartbeat renewal, and compare-and-set version checks.
   - Canonical path validation resolves `Path.resolve()`, rejects any path escaping the worktree root, and rejects untracked symlink/hardlink escapes.
   - Worker and test subprocesses run with a sanitized minimal environment (stripping `GITHUB_TOKEN`, `GH_TOKEN`, `ANTIGRAVITY_CSRF_TOKEN`, and credential variables).
3. **Advisory Fail-Closed Native Hooks (`plugins/kirion-forge/hooks.json` & `hooks/forge_guard.py`):**
   - Placed at the plugin root (`plugins/kirion-forge/hooks.json`) per native Antigravity discovery requirements.
   - Intercepts `PreToolUse` (`run_command`, `write_file`, `edit_file`) and returns `{"decision": "deny", "reason": "..."}` on any destructive command (`git push --force`, `gh pr merge`, `git branch -D`, `rm -rf .git`, global config edits) or on malformed hook payload.
   - Because hooks are advisory defense-in-depth, the Python worktree inspection and Nairu delivery broker independently re-verify the post-execution git diff and tree state before accepting any writer result.

## Consequences
- Hook crashes or bypasses cannot result in an unauthorized remote write because the deterministic Python ownership inspector and Nairu delivery broker enforce identical path, symlink, and operation guards on the actual Git tree.
