# FCI-M02 Wave 1 — Verified Feature Context (candidate)

**Scope:** read-only provenance and source-state inspection. This document and its implementation are a draft candidate, **not deployed memory governance or an authorization service**.

## Source of truth

The current approved contract establishes *intended behavior*. A pinned Git tree establishes what bytes were committed in the inspected **local repository**. An executed test or observed runtime artifact establishes only the behavior actually covered by that artifact. Previous chat, worker recollection, and inferred descriptions remain non-authoritative.

The FCI resolver reads a feature-context input with `feature_id`, an exact local repository path/HEAD/branch, contract revision, declared source SHA-256 pins, classified claims, and claims needed for the proposed action. See `second-brain/harness/schema/feature-context.schema.json` and `claim-provenance.schema.json`.

**Critical qualification:** `status=RESOLVED` means the pinned local repository sources were found and verified, *not* that their assertions are true or their owners authorized work. Output declares `authority_granted:false` even if evidence is ready. Forge's separate Engineer-authorized action rules remain the only path to mutation.

## Verification architecture

- `lib/fci/project.js`: inspects an allowlisted, clean, exact-head **local** Git repository; checks tracked file identity and SHA-256 of committed bytes. Denies missing, dirty, symlink, untracked, oversized, path-traversal or mismatched files. It does **not** query GitHub/remote HEAD or verify deployment.
- `lib/fci/freshness.js`: invalidates superseded claims and changed contract revisions/content hashes.
- `lib/fci/provenance.js`: classifies memory claims; rejects unsupported status promotion. `OPERATOR_APPROVED`, `CODE_VERIFIED`, `TEST_VERIFIED` and `RUNTIME_OBSERVED` require a matching out-of-band attestation from a **trusted host adapter**, bound to the correct feature ID, contract revision, source digest, repository commit, claim ID or approval/evidence reference. Callbacks are deliberately **not** supplied inside feature-context JSON. If the host does not supply a verifier, reported approval and PASS remain `UNVERIFIED`.
- `lib/fci/resolve.js`: validates declared identifiers, repository/contract pins, source completeness, checked claim evidence, and conflicts. Detects contradictory verified values for the same subject. Does not read/execute instructions contained in any source file.
- `lib/fci/guard.js`: declares `EVIDENCE_READY` only when every required claim is independently verified, current, and conflict-free. Even then `authority_granted:false`; no action is authorized by this module.

**Trusted-host boundary:** this first wave does not implement or establish the identity/trust of external approval/execution attestation providers. A same-process caller can construct a fake callback; a production system must obtain the callback from a separately authenticated and authorized control plane, never from a worker or memory payload. Thus the current library is an inspectable **candidate primitive**, not a complete verified-authority solution. Default use without a trusted verifier fails closed.

## Known limitations

1. Repository verification is local-only and requires a trusted host-supplied `allowed_roots` list. Local `main` is not remote `main`, and an unpushed commit is not a GitHub approval.
2. All declared source pins are required in this first wave; role-based optional-source loading and continuity compaction are later work. FCI-M01's separate graph-truncation policy remains unchanged.
3. Approval and execution verifiers are **interfaces**, not live connector integrations. No remote account identity, runtime, CI authenticity or deployment is independently verified by the library.
4. Conflicts among concurrently VERIFIED, non-superseded claims are blocked. Unverified and inferred contradictions remain non-actionable under the claim guard.
5. The new library is **not wired into** the existing CLI/MCP/lifecycle acceptance path. Integration and role projections require independent review and an explicit later work package.
6. Only source filenames/digests/status codes are returned from Git inspection; document bodies are not returned for agents to treat as instructions. Claim values are represented by SHA-256 digests (rather than copied into responses), and subjects use restricted identifiers to reduce prompt-injection exposure. This is not a universal defense when a later agent independently opens untrusted files.
7. After source compilation, the resolver checks the local HEAD and worktree again to detect obvious state changes during reconstruction. It cannot provide a transactional snapshot across external systems.

## Test command and acceptance

From the embedded `second-brain/` directory:

```sh
node tools/harness/test/fci-memory.js
```

Root integration: `python tools/entity_check.py`. The fixture suite constructs disposable Git repositories and tests missing authority, stale source, invalid contract, supersession, false test PASS, conflicts, and hostile source content. It cannot establish a measurable production hallucination reduction without a controlled downstream pilot.

**Do not merge this Wave 1 PR, adopt KirionForge R2, migrate live project memory or deploy on the strength of source-inspection tests alone.**
