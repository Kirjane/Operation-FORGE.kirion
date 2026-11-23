"""Synthetic-only Forge evidence-to-claim evaluator.

All inputs here, including the simulated resolver snapshot, are *test data*.
There are no live trust roots, production gate authorities, or promotion actions.
Security and applicability checks are explicit, including in optimized Python.
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
    "Kirjane/Salryn": ("retail.json", "96b4340c96f69f8a130018d69caf62052a3d5f1ecb95b504d9cf0a140d7a994b"),
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
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "contracts/claim-request.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(request), key=lambda e: (str(e.json_path), e.message))
    if errors:
        raise InvalidClaim("Invalid untrusted claim: " + "; ".join(e.message for e in errors[:4]))
    offered = request["offered_evidence_ids"]
    if len(offered) != len(set(offered)):
        raise InvalidClaim("Duplicate offered evidence ID")


def _load_policy(repository: str, context: Mapping[str, Any]) -> dict[str, Any] | None:
    # Hash pins are for test consistency only, never real policy approval.
    if repository not in POLICY_DIGESTS:
        return None
    name, expected = POLICY_DIGESTS[repository]
    raw = (ROOT / "policies" / name).read_bytes()
    if sha256(raw).hexdigest() != expected:
        return None
    declared = context.get("pinned_policy", {})
    if not isinstance(declared, Mapping) or (
        declared.get("path") != "policies/" + name
        or declared.get("sha256") != expected
        or declared.get("policy_mode") != "SYNTHETIC_TEST_ONLY_NOT_PROJECT_AUTHORITY"
    ):
        return None
    policy = json.loads(raw)
    if (policy.get("repository") != repository
            or policy.get("policy_id") != declared.get("policy_id")
            or policy.get("classification") != "SYNTHETIC_TEST_ONLY_NOT_PROJECT_AUTHORITY"):
        return None
    return policy


def _trusted(evidence: Mapping[str, Any]) -> bool:
    issuer = evidence.get("issuer_resolution", {})
    if not isinstance(issuer, Mapping):
        return False
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
        if "entrypoint" in request_target:
            keys.append("entrypoint")
        if "validation_scope" in request_target:
            keys.append("validation_scope")
    if claim_type == "RUNTIME_ACCEPTANCE":
        keys.append("artifact_digest_sha256")
    if claim_type == "SOURCE_INTEGRITY_VERIFIED":
        keys.append("content_scope")
    return all(request_target.get(key) == observed.get(key) for key in keys)


def _binding_failure(request: Mapping[str, Any], evidence: Mapping[str, Any]) -> str | None:
    target = request["claim"]["target"]
    claim_type = request["claim"]["type"]
    observed = evidence.get("observed_target", {})
    if not isinstance(observed, Mapping):
        return None
    if evidence.get("candidate_sha") != request["mission"]["candidate_sha"]:
        return "EVIDENCE_SHA_MISMATCH"
    if claim_type in {"RUNTIME_ACCEPTANCE", "RELEASE_READY"} and observed.get("artifact_digest_sha256") not in {
            None, target.get("artifact_digest_sha256")}:
        return "EVIDENCE_ARTIFACT_MISMATCH"
    if not _target_matches(target, observed, claim_type):
        if (claim_type == "RUNTIME_ACCEPTANCE" and observed.get("kind") == "ci-validation"
                and observed.get("entrypoint") and observed.get("entrypoint") != target.get("entrypoint")):
            return "WRONG_EXECUTABLE_TARGET"
    return None


def _reviewer_binding(context: Mapping[str, Any], security_context: Mapping[str, Any], evidence: Mapping[str, Any]) -> bool:
    """Synthetic resolved reviewer identity must equal actual receipt issuer, not a declared label."""
    resolution = context.get("reviewer_resolution", {})
    if (not isinstance(resolution, Mapping)
            or resolution.get("resolved_by") != "SIMULATED_REVIEWER_API"):
        return False
    reviewer, author = resolution.get("reviewer_identity"), resolution.get("author_identity")
    if not reviewer or not author or reviewer == author:
        return False
    if evidence.get("issuer_resolution", {}).get("issuer_id") != reviewer:
        return False
    if evidence.get("issuer_resolution", {}).get("channel") != "SIMULATED_REVIEWER_API":
        return False
    # Independently supplied security context must not contradict the resolved identity.
    if security_context:
        if "author_identity" in security_context and security_context["author_identity"] != author:
            return False
        if "reviewer_identity" in security_context and security_context["reviewer_identity"] != reviewer:
            return False
    return True


def _gate_evidence_problem(request: Mapping[str, Any], gate: Mapping[str, Any],
                           evidence: Mapping[str, Any], context: Mapping[str, Any],
                           security_context: Mapping[str, Any]) -> str | None:
    """Apply to BOTH PASS and FAIL, before interpreting either as claim evidence.

    A mismatched source SHA/artifact is a proof-binding contradiction only when
    an offered PASS is evaluated; an unrelated FAIL must never condemn a target.
    """
    if not _trusted(evidence):
        return "UNTRUSTED_ATTESTATION"
    if (evidence.get("evidence_level") != gate.get("minimum_level")
            or evidence.get("evidence_type") not in gate.get("allowed_types", [])):
        return "MISSING_TARGET_EVIDENCE"
    issuer = evidence.get("issuer_resolution", {})
    required_channel = gate.get("required_issuer_channel")
    if required_channel is not None and issuer.get("channel") != required_channel:
        return "UNTRUSTED_ATTESTATION"
    expected_issuer_id = gate.get("required_issuer_id")
    if expected_issuer_id is not None and issuer.get("issuer_id") != expected_issuer_id:
        return "UNTRUSTED_ATTESTATION"
    if gate.get("target_binding") == "EXACT_SOURCE_SHA_AND_REVIEWER":
        if not _reviewer_binding(context, security_context, evidence):
            return "REVIEWER_CONFLICT"
    observed = evidence.get("observed_target", {})
    if not isinstance(observed, Mapping):
        return "MISSING_TARGET_EVIDENCE"
    if evidence.get("candidate_sha") != request["mission"]["candidate_sha"]:
        return "EVIDENCE_SHA_MISMATCH"
    binding = gate.get("target_binding")
    required_target = gate.get("required_observed_target")
    if required_target is not None:
        if not isinstance(required_target, Mapping) or any(observed.get(k) != v for k, v in required_target.items()):
            return "MISSING_TARGET_EVIDENCE"
    if binding == "EXACT_SOURCE_SHA_AND_REVIEWER":
        if request["claim"]["type"] == "SOURCE_REVIEWED" and not _target_matches(
                request["claim"]["target"], observed, "SOURCE_REVIEWED"):
            return "MISSING_TARGET_EVIDENCE"
    elif binding in {"EXACT_INSTALLER_AND_DEVICE", "SIGNING_POLICY_AND_ARTIFACT_SHA256"}:
        expected_digest = request["claim"]["target"].get("artifact_digest_sha256")
        if observed.get("artifact_digest_sha256") != expected_digest:
            if observed.get("artifact_digest_sha256"):
                return "EVIDENCE_ARTIFACT_MISMATCH"
            return "MISSING_TARGET_EVIDENCE"
    else:
        defect = _binding_failure(request, evidence)
        if defect:
            return defect
        if not _target_matches(request["claim"]["target"], observed, request["claim"]["type"]):
            return "MISSING_TARGET_EVIDENCE"
    return None


def _content_comparison(request: Mapping[str, Any], context: Mapping[str, Any], linked: list[Mapping[str, Any]]) -> str:
    """Every in-scope path requires one provider-linked comparison to the exact Git object.

    Values are from a simulated resolver only. No actual Git fetch occurs.
    """
    raw = context.get("git_object_comparisons")
    if raw is None:
        raw = [context["git_object_comparison"]] if "git_object_comparison" in context else []
    if not isinstance(raw, list) or not raw or "git_object_comparisons" in context and "git_object_comparison" in context:
        return "MISSING_TARGET_EVIDENCE"
    scope = request["claim"]["target"].get("content_scope", [])
    paths = [r.get("path") for r in raw if isinstance(r, Mapping)]
    if len(paths) != len(raw) or len(paths) != len(set(paths)) or set(paths) != set(scope):
        return "MISSING_TARGET_EVIDENCE"
    ids = {e.get("evidence_id"): e for e in linked}
    for item in raw:
        e = ids.get(item.get("linked_evidence_id"))
        if (e is None or item.get("origin") != "SIMULATED_GIT_OBJECT_FETCH_NOT_CLAIMANT"
                or item.get("repository") != request["mission"]["repository"]
                or item.get("candidate_sha") != request["mission"]["candidate_sha"]
                or item.get("path") not in scope
                or not item.get("approved_blob_sha") or not item.get("observed_blob_sha")
                or e.get("issuer_resolution", {}).get("channel") != "SIMULATED_GIT_OBJECT_FETCH"
                or item["path"] not in e.get("observed_target", {}).get("content_scope", [])):
            return "MISSING_TARGET_EVIDENCE"
    return "SOURCE_CONTENT_MISMATCH" if any(
        item["approved_blob_sha"] != item["observed_blob_sha"] for item in raw) else "MATCH"


def evaluate_fixture(case: Mapping[str, Any], *, security_context: Mapping[str, Any] | None = None,
                     mode: str = "synthetic") -> Result:
    """Evaluate one fixture. Simulated evidence can NEVER authorize a live claim."""
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
    if (policy is None or not isinstance(auth, Mapping)
            or auth.get("resolver_source") != "SYNTHETIC_TEST_HARNESS_NOT_AUTHORIZED_FOR_LIVE"
            or auth.get("repository") != repo
            or auth.get("candidate_sha") != request["mission"]["candidate_sha"]
            or not auth.get("authority_ref")):
        return _result(UNVERIFIED, "UNRESOLVED_AUTHORITY")
    claim_type = request["claim"]["type"]
    required = [g for g in policy["gates"] if claim_type in g["applies_to"]]
    if not required or len({g["id"] for g in required}) != len(required):
        return _result(UNVERIFIED, "UNRESOLVED_AUTHORITY")

    sec = security_context or {}
    if not isinstance(sec, Mapping):
        return _result(UNVERIFIED, "UNRESOLVED_AUTHORITY")
    if sec.get("reviewer_identity") and sec.get("author_identity") and sec["reviewer_identity"] == sec["author_identity"]:
        return _result(UNVERIFIED, "REVIEWER_CONFLICT")
    for receipt_id, binding in sec.get("receipt_bindings", {}).items():
        if receipt_id not in request["offered_evidence_ids"]:
            continue
        expected = {
            "repository": repo, "candidate_sha": request["mission"]["candidate_sha"],
            "mission_id": request["mission"]["mission_id"],
            "claim_id": request["claim"]["claim_id"],
            "claimant_id": sec.get("claimant_id"), "nonce": sec.get("nonce"),
        }
        if not isinstance(binding, Mapping) or any(binding.get(k) != v or v is None for k, v in expected.items()):
            return _result(UNVERIFIED, "REPLAYED_RECEIPT")

    records = context.get("evidence_records", [])
    gates = context.get("gate_observations", [])
    if not isinstance(records, list) or any(not isinstance(e, Mapping) for e in records):
        return _result(UNVERIFIED, "UNTRUSTED_ATTESTATION")
    evidence = {e.get("evidence_id"): e for e in records}
    if len(evidence) != len(records):
        return _result(UNVERIFIED, "INCONSISTENT_EVIDENCE")
    if not isinstance(gates, list) or any(not isinstance(g, Mapping) for g in gates):
        return _result(UNVERIFIED, "REQUIRED_GATE_MISSING")
    observed = {g.get("gate_id"): g for g in gates}
    if len(observed) != len(gates):
        return _result(UNVERIFIED, "INCONSISTENT_EVIDENCE")
    if any(g["id"] not in observed for g in required):
        return _result(UNVERIFIED, "REQUIRED_GATE_MISSING")

    failures: list[str] = []
    unknowns: list[str] = []
    inconsistent = False
    for gate in required:
        obs = observed[gate["id"]]
        if obs.get("resolved_by") != "SIMULATED_POLICY_EVIDENCE_RESOLVER":
            unknowns.append("UNTRUSTED_ATTESTATION")
            continue
        status = obs.get("observed_status")
        if status == "NOT_RUN":
            unknowns.append("REQUIRED_GATE_NOT_RUN")
            continue
        if status == "BLOCKED":
            unknowns.append("REQUIRED_GATE_BLOCKED")
            continue
        if status not in {"PASS", "FAIL"}:
            unknowns.append("REQUIRED_GATE_MISSING")
            continue
        linked_ids = obs.get("evidence_ids")
        if not isinstance(linked_ids, list) or not linked_ids or any(not isinstance(k, str) for k in linked_ids):
            unknowns.append("MISSING_TARGET_EVIDENCE")
            continue
        if any(k not in request["offered_evidence_ids"] or k not in evidence for k in linked_ids):
            unknowns.append("MISSING_TARGET_EVIDENCE")
            continue
        linked = [evidence[k] for k in linked_ids]
        if any(e.get("result") != status for e in linked):
            inconsistent = True
            continue
        problems = [_gate_evidence_problem(request, gate, e, context, sec) for e in linked]
        if any(problems):
            # Evidence applicability MUST precede status. An irrelevant FAIL is UNKNOWN,
            # whereas a wrong-source/artifact PASS can contradict the offered proof.
            for problem in problems:
                if not problem:
                    continue
                if status == "PASS" and problem in {"EVIDENCE_SHA_MISMATCH", "EVIDENCE_ARTIFACT_MISMATCH", "WRONG_EXECUTABLE_TARGET"}:
                    failures.append(problem)
                else:
                    unknowns.append(problem)
            continue
        if claim_type == "SOURCE_INTEGRITY_VERIFIED":
            content_state = _content_comparison(request, context, linked)
            if content_state == "MISSING_TARGET_EVIDENCE":
                unknowns.append(content_state)
            elif content_state == "SOURCE_CONTENT_MISMATCH" and status == "FAIL":
                failures.append(content_state)
            elif content_state == "MATCH" and status == "PASS":
                pass
            else:
                inconsistent = True
        elif status == "FAIL":
            failures.append("REQUIRED_GATE_FAILED")

    # A specifically offered PASS may prove the proof was aimed at the wrong Cafe
    # executable, even while the installed Cafe outcome itself remains unknown.
    if claim_type == "RUNTIME_ACCEPTANCE":
        for offered_id in request["offered_evidence_ids"]:
            item = evidence.get(offered_id)
            if (item is None or not _trusted(item) or item.get("result") != "PASS"
                    or item.get("evidence_type") not in {"BROWSER", "RUNTIME"}):
                continue
            if _binding_failure(request, item) == "WRONG_EXECUTABLE_TARGET":
                failures.append("WRONG_EXECUTABLE_TARGET")

    if inconsistent:
        return _result(UNVERIFIED, "INCONSISTENT_EVIDENCE")
    if failures:
        return _result(CONTRADICTED, *(failures + unknowns))
    if unknowns:
        return _result(UNVERIFIED, *unknowns)
    return _result(SUPPORTED, "SCOPED_EVIDENCE_MATCH")


def evaluate_live(*_args: Any, **_kwargs: Any) -> Result:
    """Fail closed: no authorized policy resolver or live evidence source exists."""
    return _result(UNVERIFIED, "UNRESOLVED_AUTHORITY")
