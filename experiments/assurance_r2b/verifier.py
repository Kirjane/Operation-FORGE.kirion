"""Synthetic-only Forge claim adjudicator.

This module makes *no* remote calls and cannot authorize production, CI,
releases, or Forge promotion. `evaluate_fixture` is intentionally named: its
simulated resolver context and policies are test data, not accepted authority.

All security checks use explicit exceptions/branches, never Python `assert`.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
POLICY_DIGESTS = {
    "Kirjane/Dev-Salryn-Cafe": ("cafe.json", "e6421d75125b9ca5e711e9ed7de128cffe3784dd536ba3d7b1fdebc0fc687ae3"),
    "Kirjane/Salryn": ("retail.json", "a5aef97c5c99b47de4cb496f75cfcdf15d5809719cd35b4c1d000a27e2393757"),
    "Project-Intra-Smithy/ONE-TALIBON-intra.office.system-STABLE-v1-10-18-2026": ("talibon.json", "c5a42875b2a20b22a155923b904aa95789f94c4d5b7c2df39dd43947646fab09"),
}
SUPPORTED, CONTRADICTED, UNVERIFIED = "CLAIM_SUPPORTED", "CLAIM_CONTRADICTED", "CLAIM_UNVERIFIED"


class InvalidClaim(ValueError):
    """Claim is not valid for this synthetic contract boundary."""


@dataclass(frozen=True)
class Result:
    verdict: str
    reason_codes: tuple[str, ...]
    actual_product_outcome: str = "NOT_TESTED"
    synthetic: bool = True
    promotion_authorized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason_codes": list(self.reason_codes),
            "actual_product_outcome": self.actual_product_outcome,
            "synthetic": self.synthetic,
            "promotion_authorized": self.promotion_authorized,
        }


def _result(verdict: str, *reasons: str) -> Result:
    if not reasons:
        raise ValueError("A verdict must contain its material reason")
    return Result(verdict, tuple(dict.fromkeys(reasons)))


def _shape(request: Mapping[str, Any]) -> None:
    # Do not use assert, which `python -O` removes.
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "contracts/claim-request.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(request), key=lambda e: (str(e.json_path), e.message))
    if errors:
        raise InvalidClaim("Invalid untrusted claim: " + "; ".join(e.message for e in errors[:4]))
    offered = request["offered_evidence_ids"]
    if len(offered) != len(set(offered)):
        raise InvalidClaim("Duplicate offered evidence ID")


def _load_policy(repository: str, context: Mapping[str, Any]) -> dict[str, Any] | None:
    # Trusted *test harness* pin, not candidate-controlled path/digest or live policy.
    if repository not in POLICY_DIGESTS:
        return None
    name, expected = POLICY_DIGESTS[repository]
    raw = (ROOT / "policies" / name).read_bytes()
    actual = sha256(raw).hexdigest()
    if actual != expected:
        return None
    declared = context.get("pinned_policy", {})
    if (declared.get("path") != "policies/" + name
            or declared.get("sha256") != expected
            or declared.get("policy_mode") != "SYNTHETIC_TEST_ONLY_NOT_PROJECT_AUTHORITY"):
        return None
    policy = json.loads(raw)
    if (policy.get("repository") != repository
            or policy.get("policy_id") != declared.get("policy_id")
            or policy.get("classification") != "SYNTHETIC_TEST_ONLY_NOT_PROJECT_AUTHORITY"):
        return None
    return policy


def _trusted(evidence: Mapping[str, Any]) -> bool:
    issuer = evidence.get("issuer_resolution", {})
    level = evidence.get("evidence_level")
    provenance = evidence.get("provenance")
    provenance_consistent = (
        (level == "E1" and provenance in {"DIRECTLY_OBSERVED", "REPRODUCED"})
        or (level == "E4" and provenance in {"AUTOMATED", "REPRODUCED"})
        or (level == "E5" and provenance in {"DIRECTLY_OBSERVED", "REPRODUCED"})
    )
    return (issuer.get("trust_class") == "SIMULATED_RESOLVED_FIXTURE_ONLY"
            and issuer.get("channel") in {
                "SIMULATED_GITHUB_ACTIONS", "SIMULATED_GIT_OBJECT_FETCH", "SIMULATED_REVIEWER_API"}
            and provenance_consistent
            and bool(issuer.get("issuer_id"))
            and str(evidence.get("artifact_reference", "")).startswith("fixture://"))


def _target_matches(request_target: Mapping[str, Any], observed: Mapping[str, Any], claim_type: str) -> bool:
    if observed.get("kind") != request_target.get("kind"):
        return False
    keys = ["environment", "data_authority"]
    if claim_type in {"AUTOMATED_VALIDATION", "RUNTIME_ACCEPTANCE"}:
        keys.append("entrypoint") if "entrypoint" in request_target else None
        keys.append("validation_scope") if "validation_scope" in request_target else None
    if claim_type == "RUNTIME_ACCEPTANCE":
        keys += ["artifact_digest_sha256"]
    if claim_type == "SOURCE_INTEGRITY_VERIFIED":
        keys += ["content_scope"]
    return all(request_target.get(key) == observed.get(key) for key in keys)


def _binding_failure(request: Mapping[str, Any], evidence: Mapping[str, Any]) -> str | None:
    target = request["claim"]["target"]
    claim_type = request["claim"]["type"]
    observed = evidence.get("observed_target", {})
    if evidence.get("candidate_sha") != request["mission"]["candidate_sha"]:
        return "EVIDENCE_SHA_MISMATCH"
    if claim_type == "RUNTIME_ACCEPTANCE" and observed.get("artifact_digest_sha256") not in {
            None, target.get("artifact_digest_sha256")}:
        return "EVIDENCE_ARTIFACT_MISMATCH"
    if claim_type == "RELEASE_READY" and observed.get("artifact_digest_sha256") not in {
            None, target.get("artifact_digest_sha256")}:
        return "EVIDENCE_ARTIFACT_MISMATCH"
    if not _target_matches(target, observed, claim_type):
        if (claim_type == "RUNTIME_ACCEPTANCE" and observed.get("kind") == "ci-validation"
                and observed.get("entrypoint") and observed.get("entrypoint") != target.get("entrypoint")):
            return "WRONG_EXECUTABLE_TARGET"
    return None


def evaluate_fixture(case: Mapping[str, Any], *, security_context: Mapping[str, Any] | None = None,
                     mode: str = "synthetic") -> Result:
    """Adjudicate one isolated synthetic fixture. Never returns live acceptance.

    `security_context` represents *simulated provider-owned data* for hostile tests
    (not an agent-supplied claim extension). Its absence never creates a live trust.
    """
    if mode != "synthetic":
        return _result(UNVERIFIED, "UNRESOLVED_AUTHORITY")
    if not isinstance(case, Mapping) or "untrusted_request" not in case:
        raise InvalidClaim("A synthetic fixture must contain untrusted_request")
    request = case["untrusted_request"]
    _shape(request)
    context = case.get("simulated_resolver_context")
    if not isinstance(context, Mapping) or context.get("synthetic_only") is not True:
        return _result(UNVERIFIED, "UNRESOLVED_AUTHORITY")

    repo = request["mission"]["repository"]
    policy = _load_policy(repo, context)
    auth = context.get("authorization_snapshot", {})
    if (policy is None or auth.get("resolver_source") != "SYNTHETIC_TEST_HARNESS_NOT_AUTHORIZED_FOR_LIVE"
            or auth.get("repository") != repo or auth.get("candidate_sha") != request["mission"]["candidate_sha"]
            or not auth.get("authority_ref")):
        return _result(UNVERIFIED, "UNRESOLVED_AUTHORITY")

    claim_type = request["claim"]["type"]
    required = [gate for gate in policy["gates"] if claim_type in gate["applies_to"]]
    if not required:
        return _result(UNVERIFIED, "UNRESOLVED_AUTHORITY")
    required_ids = {gate["id"] for gate in required}
    if len(required_ids) != len(required):
        return _result(UNVERIFIED, "UNRESOLVED_AUTHORITY")

    sec = security_context or {}
    if sec.get("reviewer_identity") and sec.get("author_identity") and sec["reviewer_identity"] == sec["author_identity"]:
        return _result(UNVERIFIED, "REVIEWER_CONFLICT")

    # Receipt custody is keyed to mission, claimant, nonce, SHA and claim ID;
    # replay at the SAME source SHA is still invalid across these boundaries.
    for receipt_id, binding in sec.get("receipt_bindings", {}).items():
        if receipt_id not in request["offered_evidence_ids"]:
            continue
        expected = {
            "repository": repo, "candidate_sha": request["mission"]["candidate_sha"],
            "mission_id": request["mission"]["mission_id"],
            "claim_id": request["claim"]["claim_id"],
            "claimant_id": sec.get("claimant_id"), "nonce": sec.get("nonce"),
        }
        if any(binding.get(key) != value or value is None for key, value in expected.items()):
            return _result(UNVERIFIED, "REPLAYED_RECEIPT")

    evidence_records = context.get("evidence_records", [])
    if not isinstance(evidence_records, list) or any(not isinstance(e, Mapping) for e in evidence_records):
        return _result(UNVERIFIED, "UNTRUSTED_ATTESTATION")
    evidence = {e.get("evidence_id"): e for e in evidence_records}
    if len(evidence) != len(evidence_records):
        return _result(UNVERIFIED, "INCONSISTENT_EVIDENCE")
    gates = context.get("gate_observations", [])
    if not isinstance(gates, list) or any(not isinstance(g, Mapping) for g in gates):
        return _result(UNVERIFIED, "REQUIRED_GATE_MISSING")
    observed = {g.get("gate_id"): g for g in gates}
    if len(observed) != len(gates):
        return _result(UNVERIFIED, "INCONSISTENT_EVIDENCE")
    if any(gid not in observed for gid in required_ids):
        return _result(UNVERIFIED, "REQUIRED_GATE_MISSING")

    failures: list[str] = []
    unknowns: list[str] = []
    inconsistencies = False
    for gate in required:
        obs = observed[gate["id"]]
        if obs.get("resolved_by") != "SIMULATED_POLICY_EVIDENCE_RESOLVER":
            unknowns.append("UNTRUSTED_ATTESTATION")
            continue
        status = obs.get("observed_status")
        linked_ids = obs.get("evidence_ids", [])
        linked = [evidence.get(eid) for eid in linked_ids]
        if status == "NOT_RUN":
            unknowns.append("REQUIRED_GATE_NOT_RUN")
            continue
        if status == "BLOCKED":
            unknowns.append("REQUIRED_GATE_BLOCKED")
            continue
        if status == "UNKNOWN":
            unknowns.append("REQUIRED_GATE_MISSING")
            continue
        if status not in {"PASS", "FAIL"}:
            unknowns.append("REQUIRED_GATE_MISSING")
            continue
        if not linked_ids or any(e is None for e in linked):
            unknowns.append("MISSING_TARGET_EVIDENCE")
            continue
        if any(not _trusted(e) for e in linked):
            unknowns.append("UNTRUSTED_ATTESTATION")
            continue
        if any(e.get("result") != status for e in linked):
            inconsistencies = True
            continue
        if any(e.get("candidate_sha") != request["mission"]["candidate_sha"] for e in linked):
            failures.append("EVIDENCE_SHA_MISMATCH")
            continue
        if status == "FAIL":
            if claim_type == "SOURCE_INTEGRITY_VERIFIED":
                comparison = context.get("git_object_comparison", {})
                good = (comparison.get("origin") == "SIMULATED_GIT_OBJECT_FETCH_NOT_CLAIMANT"
                        and comparison.get("linked_evidence_id") in linked_ids
                        and comparison.get("path") in request["claim"]["target"].get("content_scope", [])
                        and comparison.get("approved_blob_sha") != comparison.get("observed_blob_sha")
                        and any(e.get("issuer_resolution", {}).get("channel") == "SIMULATED_GIT_OBJECT_FETCH" for e in linked))
                if good:
                    failures.append("SOURCE_CONTENT_MISMATCH")
                else:
                    unknowns.append("MISSING_TARGET_EVIDENCE")
            else:
                failures.append("REQUIRED_GATE_FAILED")
            continue
        # status PASS
        if any(e.get("evidence_level") != gate["minimum_level"] or e.get("evidence_type") not in gate["allowed_types"] for e in linked):
            unknowns.append("MISSING_TARGET_EVIDENCE")
            continue
        if any(e.get("evidence_id") not in request["offered_evidence_ids"] for e in linked):
            unknowns.append("MISSING_TARGET_EVIDENCE")
            continue
        for e in linked:
            # Release readiness aggregates multiple *different* gate targets.
            # Source review evidence is about the source SHA, NOT installer route;
            # the device/signing gates separately bind the release artifact.
            if claim_type == "RELEASE_READY" and gate["target_binding"] == "EXACT_SOURCE_SHA_AND_REVIEWER":
                if e.get("observed_target", {}).get("kind") != "source-tree":
                    unknowns.append("MISSING_TARGET_EVIDENCE")
                continue
            if claim_type == "RELEASE_READY" and gate["target_binding"] in {
                    "EXACT_INSTALLER_AND_DEVICE", "SIGNING_POLICY_AND_ARTIFACT_SHA256"}:
                if e.get("observed_target", {}).get("artifact_digest_sha256") != request["claim"]["target"].get("artifact_digest_sha256"):
                    failures.append("EVIDENCE_ARTIFACT_MISMATCH")
                continue
            fail = _binding_failure(request, e)
            if fail is not None:
                failures.append(fail)
            elif not _target_matches(request["claim"]["target"], e.get("observed_target", {}), claim_type):
                unknowns.append("MISSING_TARGET_EVIDENCE")
        if claim_type == "SOURCE_INTEGRITY_VERIFIED":
            comparison = context.get("git_object_comparison", {})
            if comparison.get("origin") != "SIMULATED_GIT_OBJECT_FETCH_NOT_CLAIMANT" or comparison.get("approved_blob_sha") != comparison.get("observed_blob_sha"):
                unknowns.append("MISSING_TARGET_EVIDENCE")

    # An *offered* and independently resolved proof can positively establish that
    # the evidence is for the wrong target even if the requested real-host gate
    # was never run. This does NOT assert that the actual host failed.
    for offered_id in request["offered_evidence_ids"]:
        offered = evidence.get(offered_id)
        if offered is None or not _trusted(offered) or offered.get("result") != "PASS":
            continue
        defect = _binding_failure(request, offered)
        if defect is not None:
            failures.append(defect)

    if inconsistencies:
        return _result(UNVERIFIED, "INCONSISTENT_EVIDENCE")
    if failures:
        return _result(CONTRADICTED, *(failures + unknowns))
    if unknowns:
        return _result(UNVERIFIED, *unknowns)
    return _result(SUPPORTED, "SCOPED_EVIDENCE_MATCH")


def evaluate_live(*_args: Any, **_kwargs: Any) -> Result:
    """Fail closed until a separately approved live resolver exists."""
    return _result(UNVERIFIED, "UNRESOLVED_AUTHORITY")
