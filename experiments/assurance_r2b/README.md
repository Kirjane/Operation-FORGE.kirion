# Forge R2-B — Synthetic-only claim verifier (R2 corrective candidate)

**Status:** R1 independent review `FIX_REQUIRED`; R2 **writer-side corrected**, fresh nonauthor review required, draft PR only. **Not a live security, release or promotion gate.**

**Source:** [Forge Issue #19](https://github.com/Kirjane/Operation-FORGE.kirion/issues/19), [Nox requested changes (PR #20 review 6031088112)](https://github.com/Kirjane/Operation-FORGE.kirion/pull/20), and [Nox's review receipt](https://github.com/Kirjane/Operation-FORGE.kirion/issues/19#issuecomment-7116841568). The original, frozen R1 SHA is `6844a7c3c9fa7da12a4e754d3f625bb7d6444509`. R1 author-side 30/30 tests did **not** exercise four semantic false-result classes. This R2 candidate must receive its own exact-SHA review.

## Reproduce from the repository root

```bash
python -m pip install 'jsonschema>=4.18,<5'
python -m unittest discover -s experiments/assurance_r2b/tests -v
python -O -m unittest discover -s experiments/assurance_r2b/tests -v
python -m experiments.assurance_r2b.cli
python -m experiments.assurance_r2b.cli --mode live
```

Writer-side observed result after correction: **54/54 PASS** in normal Python and **54/54 PASS** under `-O`. Six original synthetic scenarios return their historical narrow verdicts; live mode returns six `CLAIM_UNVERIFIED / UNRESOLVED_AUTHORITY` results. These checks are **not** independently authenticated CI or project evidence.

## Four reproduced R1 defects and bounded R2 repairs

| Nox finding | Old problem | R2 corrective behavior and tests |
| --- | --- | --- |
| **NXR2B-001** | A release-ready claim could be supported by device/signing receipts for a mock source tree if artifact digest matched. | Enforce separately hash-pinned *synthetic* policy constraints for per-gate target kind, environment, data authority, artifact digest, VHDX A/B/C device matrix, signing-policy ID and expected issuer. Full legitimate synthetic release positive + wrong-target/issuer/matrix/signing negatives. |
| **NXR2B-002** | Positive source-content comparison ignored file path and linked evidence ID. | One complete repository/SHA/path/linked-offered-receipt Git comparator per claimed path (single-file or multi-path), with matching observed content scope. Wrong path, wrong ID/SHA, missing-path and missing-offer tests reject proof. |
| **NXR2B-003** | The E1 source-review receipt issuer could be the author while separately declared reviewer differed. | Require synthetic reviewer-resolution binding, issuer ID matching resolved reviewer ID, reviewer distinct from resolved author, plus reject contradictory supplemental security_context. Valid review positive and collision/missing-resolution negatives. |
| **NXR2B-004** | Irrelevant FAIL from CI smoke or low-level E1 could falsely contradict the Windows device requirement. | Apply issuer, type/level, offer, source and target scope checks **before any PASS or FAIL** counts. Unrelated FAIL → `CLAIM_UNVERIFIED`; correct-target E5 FAIL → `CLAIM_CONTRADICTED`. Former H12 oracle changed. |

## Exactly what changed versus R2-A / R1

- `verifier.py`: implemented the four corrected semantic gates. All acceptance logic uses explicit branches and exceptions; no Python `assert` used for safety.
- `policies/retail.json`: **changed** to add synthetic-only exact per-gate target and issuer constraints; its hardcoded SHA-256 pin in `verifier.py` was recalculated. **No real Retail policy authorization** is implied.
- `fixtures/r2a-{red,green}-retail.json`: synthetic policy digest repinned and synthetic reviewer/author resolution provided separately from the untrusted claim. These are no longer byte-identical to the archived R2-A files.
- `fixtures/r2a-red-talibon.json`: negative comparison explicitly declares repository and commit, and the comparison receipt is included among offered IDs so negative proof is actually linked. The historical-inspired expected verdict is unchanged.
- `tests/test_verifier.py`: preserves the original 30 test methods (H12 oracle corrected) and adds 24 hostile and legitimate controls, including a fully supported **synthetic** release fixture and a two-file positive identity comparison.
- The original R2-A untrusted-request schema and remaining fixtures/policies are unchanged.

## Strict authority boundary

This module is a **simulator**. `untrusted_request` is claimant-authored; simulated resolver evidence, reviewer context and policy fixtures are *also locally supplied test data*, not independently obtained trustworthy events. A correct simulated verdict is not a real GitHub CI attestation, sign-off, C# operator workflow, installed host test, or business outcome. Every result includes `synthetic=true`, `promotion_authorized=false`, and `actual_product_outcome=NOT_TESTED`. A requested `live` mode always fails closed.

Source reviews, policy pins and reviewer identities still require authenticated external trust roots under a **separately authorized** future stage. Existing Forge E0–E7 doctrine and Forge-vs-Brain authority remain unchanged. No merge, runtime installation, production signature, automatic PR acceptance or R2-C authority is granted by this writer-side test result.
