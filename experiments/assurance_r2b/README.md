# Forge R2-B — Synthetic assurance-verifier experiment (isolated)

**Status: WRITER CANDIDATE / NO INDEPENDENT REVIEW / NOT INTEGRATED / NOT A LIVE SECURITY OR RELEASE GATE.**

This is the bounded response to [Forge Issue #19](https://github.com/Kirjane/Operation-FORGE.kirion/issues/19) and [Nox's R2-A exact-artifact design review](https://github.com/Kirjane/Operation-FORGE.kirion/issues/19#issuecomment-7115974127). It implements a *purely synthetic*, deterministic evaluator for one narrowly defined engineering claim at a time. It does **not** run other AI workers, execute source builds, verify actual GitHub Actions runs, fetch real reviewer identities, access Salryn/ONE TALIBON databases, operate installers, or grant any Forge approval/promotion.

## Run (from repository root)

```bash
python -m pip install 'jsonschema>=4.18,<5'
python -m unittest discover -s experiments/assurance_r2b/tests -v
python -O -m unittest discover -s experiments/assurance_r2b/tests -v
python -m experiments.assurance_r2b.cli
python -m experiments.assurance_r2b.cli --mode live
```

`--mode live` deliberately returns `CLAIM_UNVERIFIED/UNRESOLVED_AUTHORITY` for every scenario. It is not a partially working live resolver.

The six original R2-A-R2 synthetic fixtures and three example policies were copied **without edits** from the SHA-256-pinned R2-A R2 design archive (`66e1c1637b6831a39743b34a06c7e7498235c283f57ce30eed7790fee53ee19b`). Here they are scoped test cases, not historical product evidence. The source claim schema was also copied unchanged.

## Boundaries

- **Untrusted source:** `untrusted_request` (worker-claimable). Strict Draft-2020-12 JSON Schema rejects source hash authority, new policy, fabricated mandatory gates, and authored expected verdicts.
- **Synthetic evidence source:** `simulated_resolver_context` is a test fixture **only**. `evaluate_fixture` accepts that container in `synthetic` mode to test claim reasoning. A real worker must never be allowed to supply an arbitrary resolver container and obtain acceptance from it.
- **Policy pin:** Synthetic policy content must match a hardcoded repository→file→digest mapping in code (not any digest or path supplied by the worker or mutated fixture). These are intentionally **not** approved live project policies.
- **Trust checks:** Evidence must have a compatible simulated channel and provenance, nonempty issuer and `fixture://` reference. Author-only/self-reported receipts cannot satisfy `E4`/`E5` claims. In real mode these synthetic receipts are NEVER accepted.
- **Evidence scope:** Enforce repo/candidate SHA, required gate membership, E-level/type, target/route, data authority, validation scope, source blob identity, and artifact hash. Release-ready aggregates different gate targets; source review does not need an installer artifact hash, but signing and device proof do.
- **Reviewer/replay:** Optional **provider-owned synthetic security_context** tests independent identity collisions and a receipt's repo/SHA/claim/mission/claimant/nonce binding; in live work these values require independent provider resolution, which is currently absent.
- **Result:** `CLAIM_SUPPORTED`, `CLAIM_CONTRADICTED`, or `CLAIM_UNVERIFIED` plus reasons, `actual_product_outcome=NOT_TESTED`, `synthetic=true`, `promotion_authorized=false` **for every result**. Supporting synthetic evidence is a property of the test scenario, not a real acceptance decision.

## Decisions and exceptional cases

For one claim, a pin/mission authority mismatch blocks with `UNRESOLVED_AUTHORITY`. Evidence that demonstrably belongs to a different source SHA, artifact, or the *explicitly offered* wrong runtime entrypoint can contradict the **proof binding**, even though the requested actual runtime is not known to have failed. Trusted negative test results produce `REQUIRED_GATE_FAILED`; missing, blocked, not run, or unsupported authority produce `CLAIM_UNVERIFIED`. Inconsistent PASS/FAIL evidence holds instead of choosing PASS. A release gate can remain incomplete even when an E1 review at that SHA is valid.

The six R2-A sidecar expected oracles are independent test expectations and are **never read by the evaluator**. The Cafe red case additionally reports `REQUIRED_GATE_MISSING` because its actual installed gate is UNKNOWN; it still correctly produces the required `WRONG_EXECUTABLE_TARGET` contradiction. The test suite therefore checks expected reason subsets while asserting exact verdicts. All further tests inspect specific reason codes, not just pass counts.

## Test coverage

- Six original historical-inspired fixtures: three RED and three narrow GREEN.
- R2-A H01–H21 hostile/benign scenarios (Python unittest methods).
- NXR2A-009: invalid authored gate rejected in ordinary Python and optimized `python -O` (no `assert`-dependent enforcement in verifier).
- NXR2A-010: same-SHA replay across claimant/nonce and reviewer-author conflict, explicitly unverified.
- NXR2A-011: cannot resolve actual project authority; `live` path always fails closed.
- Policy hash corruption, empty required-gate receipt, unbacked PASS, forged author-only evidence, target/artifact/SHA mismatches, and exact-scope positives.

These are **author-executed offline tests**, not CI acceptance or nonauthor QA. No network or installation credentials are used.

## Deliberate limitations / must remain blocked

The current `evaluate_fixture` verifies a *simulated resolver container,* not its real-world custody. No production issuer whitelist, approved project gate source, immutable live policy anchor, normalized GitHub API reviewer/run access, context-isolated operator proof, durable anti-replay database, or host capability parity is implemented. In particular, `security_context` is a test hook, not authenticated identity. Do not copy this code into production acceptance until those trust roots have their own explicit Engineer authorization, separate architecture review, and tests against real external APIs.

Writer candidate changes stay under `experiments/assurance_r2b/` and are not imported into Forge's main execution/acceptance path. Review exact PR head SHA before any promotion decision. **Draft PR is NOT merge authorization.**
