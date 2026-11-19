"""F10, F11, F12 — Gate catalog G00–G15, risk profiles, fresh-context Antigravity-Nox review, and bounded self-healing."""
from __future__ import annotations

import hashlib
import uuid
from typing import Any, Callable

from .authority import AuthorityError, is_valid_git_sha, validate_contract
from .evidence import FORGE_LEVEL_TO_CERTAINTY_CEILING

GATE_CATALOG: dict[str, dict[str, str]] = {
    "G00": {"name": "Authority & Full SHA Verification", "min_evidence": "E1"},
    "G01": {"name": "Requirements & Traceability", "min_evidence": "E1"},
    "G02": {"name": "Architecture & ADR Contract", "min_evidence": "E1"},
    "G03": {"name": "Clean Build Verification", "min_evidence": "E4"},
    "G04": {"name": "Static Analysis, Lockfile & Security Scan", "min_evidence": "E4"},
    "G05": {"name": "Unit Test Verification", "min_evidence": "E4"},
    "G06": {"name": "Integration Test Verification", "min_evidence": "E4"},
    "G07": {"name": "Real Database & Migration Preservation", "min_evidence": "E5"},
    "G08": {"name": "Security & Negative Access Control", "min_evidence": "E5"},
    "G09": {"name": "Concurrency & Idempotency Verification", "min_evidence": "E5"},
    "G10": {"name": "Actual Observable Runtime Verification", "min_evidence": "E5"},
    "G11": {"name": "Frontend Accessibility & Responsive Visual Gate", "min_evidence": "E5"},
    "G12": {"name": "Full Regression Gate", "min_evidence": "E4"},
    "G13": {"name": "Fresh-Context Antigravity-Nox Exact-SHA Review", "min_evidence": "E4"},
    "G14": {"name": "Clean Checkout Reproduction", "min_evidence": "E4"},
    "G15": {"name": "Draft Delivery & Evidence Receipt", "min_evidence": "E4"},
}

EVIDENCE_LEVEL_ORDER: dict[str, int] = {
    "E0": 0,
    "E1": 1,
    "E2": 2,
    "E3": 3,
    "E4": 4,
    "E5": 5,
    "E6": 6,
    "E7": 7,
}

MANDATORY_NON_EXEMPTIBLE_GATES = {"G00", "G13", "G15"}
E5_RUNTIME_GATES = {"G07", "G08", "G09", "G10", "G11"}
STRICT_RUNTIME_ONLY_GATES = {"G07", "G09", "G10", "G11"}

GATE_ALLOWED_PASS_EVIDENCE_TYPES: dict[str, set[str]] = {
    "G00": {"SOURCE", "BUILD", "UNIT", "INTEGRATION", "RUNTIME", "SECURITY"},
    "G01": {"SOURCE", "UNIT", "INTEGRATION", "RUNTIME"},
    "G02": {"SOURCE", "UNIT", "INTEGRATION", "RUNTIME"},
    "G03": {"BUILD", "INTEGRATION", "RUNTIME"},
    "G04": {"BUILD", "UNIT", "INTEGRATION", "RUNTIME", "SECURITY"},
    "G05": {"UNIT", "INTEGRATION", "RUNTIME"},
    "G06": {"INTEGRATION", "RUNTIME"},
    "G07": {"RUNTIME"},
    "G08": {"RUNTIME", "SECURITY"},
    "G09": {"RUNTIME"},
    "G10": {"RUNTIME"},
    "G11": {"RUNTIME"},
    "G12": {"UNIT", "INTEGRATION", "RUNTIME"},
    "G13": {"UNIT", "INTEGRATION", "RUNTIME", "SECURITY"},
    "G14": {"BUILD", "UNIT", "INTEGRATION", "RUNTIME"},
    "G15": {"INTEGRATION", "RUNTIME", "SECURITY"},
}

RISK_REQUIRED_GATES: dict[str, list[str]] = {
    "RISK-0": ["G00", "G01", "G04", "G13", "G15"],
    "RISK-1": ["G00", "G01", "G03", "G04", "G05", "G12", "G13", "G15"],
    "RISK-2": ["G00", "G01", "G02", "G03", "G04", "G05", "G06", "G10", "G12", "G13", "G14", "G15"],
    "RISK-3": ["G00", "G01", "G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09", "G10", "G12", "G13", "G14", "G15"],
    "RISK-4": ["G00", "G01", "G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09", "G10", "G12", "G13", "G14", "G15"],
}

CANONICAL_FAILURE_CLASSES = (
    "product",
    "test",
    "environment",
    "dependency",
    "flaky",
    "architecture",
    "security",
    "requirements",
    "drift",
    "resource",
)


class QualityGateError(AuthorityError):
    """Raised when a required quality gate fails, is fabricated, or lacks required evidence."""


def evaluate_gate_suite(
    risk_class: str,
    envelopes: list[dict[str, Any]],
    *,
    candidate_sha: str,
    non_applicable_gates: dict[str, str] | None = None,
    required_gates: list[str] | None = None,
) -> dict[str, Any]:
    """Verify all required gates for a risk class (plus optional extra required_gates) have clean, exact-SHA trusted evidence."""
    if risk_class not in RISK_REQUIRED_GATES:
        raise QualityGateError(f"Unknown risk_class: {risk_class!r}")
    if not is_valid_git_sha(candidate_sha):
        raise QualityGateError(f"Invalid or all-zero candidate_sha forbidden: {candidate_sha!r}")

    extra_req = list(required_gates or [])
    for gid in extra_req:
        if gid not in GATE_CATALOG:
            raise QualityGateError(f"Unknown gate_id in required_gates: {gid!r}")

    required = list(dict.fromkeys(list(RISK_REQUIRED_GATES[risk_class]) + extra_req))
    na_map = non_applicable_gates or {}

    for gid, reason in na_map.items():
        if gid not in GATE_CATALOG:
            raise QualityGateError(f"Unknown gate_id in non_applicable_gates: {gid!r}")
        if gid in MANDATORY_NON_EXEMPTIBLE_GATES:
            raise QualityGateError(f"Mandatory anchor gate {gid} cannot be exempted via non_applicable_gates.")
        if not isinstance(reason, str) or not reason.strip():
            raise QualityGateError(f"Non-applicable gate {gid} requires a non-empty documented justification.")

    by_gate: dict[str, dict[str, Any]] = {}
    for env in envelopes:
        validate_contract(env, "evidence-envelope.schema.json")
        gid = env["gate_id"]
        if gid in by_gate:
            raise QualityGateError(
                f"Duplicate evidence envelope submitted for gate {gid} at candidate_sha {candidate_sha}; "
                "prior gate results cannot be overwritten."
            )
        if env["candidate_sha"] != candidate_sha:
            raise QualityGateError(
                f"Stale evidence envelope for gate {gid}: envelope SHA {env['candidate_sha']} != candidate SHA {candidate_sha}"
            )
        if env["status"] == "PASS":
            if not is_valid_git_sha(env["candidate_sha"]):
                raise QualityGateError(f"Unanchored zero SHA cannot produce a trusted PASS envelope for gate {gid}.")
            if not is_valid_git_sha(env["tree_sha"]):
                raise QualityGateError(f"Unanchored zero tree_sha cannot produce a trusted PASS envelope for gate {gid}.")
            if env["dirty"] is True:
                raise QualityGateError(f"Dirty working tree cannot produce a trusted PASS envelope for gate {gid}.")
            if env["exit_code"] != 0:
                raise QualityGateError(f"Non-zero exit_code ({env['exit_code']}) cannot be recorded as PASS for gate {gid}.")
            min_level = GATE_CATALOG[gid]["min_evidence"]
            actual_level = env["evidence_level"]
            if EVIDENCE_LEVEL_ORDER[actual_level] < EVIDENCE_LEVEL_ORDER[min_level]:
                raise QualityGateError(
                    f"Insufficient evidence level for gate {gid}: got {actual_level}, requires >= {min_level}."
                )
            expected_ceiling = FORGE_LEVEL_TO_CERTAINTY_CEILING[actual_level]
            if env["certainty_ceiling"] != expected_ceiling:
                raise QualityGateError(
                    f"Certainty ceiling mismatch for gate {gid} ({actual_level}): "
                    f"got {env['certainty_ceiling']!r}, expected {expected_ceiling!r}."
                )
            ev_type = env["evidence_type"]
            if ev_type == "NONE":
                raise QualityGateError(
                    f"Gate {gid} cannot claim PASS with evidence_type='NONE' (E0 only per EVIDENCE_CROSSWALK.md)."
                )
            if EVIDENCE_LEVEL_ORDER[actual_level] >= EVIDENCE_LEVEL_ORDER["E4"] and ev_type in ("NONE", "SOURCE"):
                raise QualityGateError(
                    f"Gate {gid} with {actual_level} PASS cannot carry evidence_type={ev_type!r} (SOURCE is E1 only)."
                )
            allowed_types = GATE_ALLOWED_PASS_EVIDENCE_TYPES[gid]
            if ev_type not in allowed_types:
                raise QualityGateError(
                    f"Gate {gid} ({GATE_CATALOG[gid]['name']}) requires evidence_type in {sorted(allowed_types)}, got {ev_type!r}."
                )
            if env["provenance"] == "ASSUMED":
                raise QualityGateError(
                    f"Gate {gid} cannot claim PASS with provenance='ASSUMED' (E0 only per EVIDENCE_CROSSWALK.md)."
                )
            if actual_level == "E1" and env["provenance"] == "REPORTED":
                raise QualityGateError(
                    f"Gate {gid} (E1) cannot carry provenance='REPORTED'; requires DIRECTLY_OBSERVED, AUTOMATED, or REPRODUCED."
                )
            if gid in E5_RUNTIME_GATES and env["provenance"] not in ("DIRECTLY_OBSERVED", "REPRODUCED"):
                raise QualityGateError(
                    f"Gate {gid} (E5) requires provenance in ('DIRECTLY_OBSERVED', 'REPRODUCED'), got {env['provenance']!r}."
                )
            if EVIDENCE_LEVEL_ORDER[actual_level] >= EVIDENCE_LEVEL_ORDER["E4"] and env["provenance"] in ("ASSUMED", "REPORTED"):
                raise QualityGateError(
                    f"Gate {gid} with {actual_level} cannot carry {env['provenance']!r} provenance."
                )
        by_gate[gid] = env

    missing: list[str] = []
    failed: list[str] = []
    not_run: list[str] = []
    passed: list[str] = []

    for gid in required:
        if gid in na_map:
            if gid in by_gate:
                st = by_gate[gid]["status"]
                if st == "NOT_RUN":
                    not_run.append(gid)
                elif st != "PASS":
                    failed.append(gid)
            continue
        if gid not in by_gate:
            missing.append(gid)
            continue
        st = by_gate[gid]["status"]
        if st == "PASS":
            passed.append(gid)
        elif st == "NOT_RUN":
            not_run.append(gid)
        else:
            failed.append(gid)

    # Any non-required gate envelope submitted must also be accounted for (failed/blocked/not-run cannot be hidden)
    required_set = set(required)
    for gid, env in by_gate.items():
        if gid in required_set:
            continue
        st = env["status"]
        if st == "PASS":
            if gid not in na_map:
                passed.append(gid)
        elif st == "NOT_RUN":
            not_run.append(gid)
        else:
            failed.append(gid)

    overall = "PASS" if (not missing and not failed and not not_run) else "BLOCKED"
    return {
        "risk_class": risk_class,
        "candidate_sha": candidate_sha,
        "overall_status": overall,
        "passed_gates": passed,
        "failed_gates": failed,
        "not_run_gates": not_run,
        "missing_gates": missing,
        "documented_non_applicable": na_map,
    }


def _has_blocking_findings(findings: list[dict[str, Any]]) -> tuple[bool, bool]:
    """Return (has_p0_quarantine, has_blocking_p1_or_p2) from raw finding entries."""
    has_p0 = any(f["severity"] == "P0" and f["disposition"] != "FIXED" for f in findings)
    has_p1 = any(f["severity"] == "P1" and f["disposition"] != "FIXED" for f in findings)
    has_undisposed_p2 = any(
        f["severity"] == "P2" and f["disposition"] not in ("FIXED", "AUTHORIZED_DISPOSITION") for f in findings
    )
    return has_p0, (has_p1 or has_undisposed_p2)


class NoxReviewEngine:
    """F11 — Fresh-context read-only adversarial review engine at a frozen candidate SHA."""

    def execute_review(
        self,
        *,
        mission_id: str,
        frozen_sha: str,
        author_context_id: str,
        inspected_scope: list[str],
        evidence_inspected: list[str],
        findings: list[dict[str, Any]],
        reviewer_persona: str = "Antigravity-Nox",
        reviewer_context_id: str | None = None,
    ) -> dict[str, Any]:
        if not is_valid_git_sha(frozen_sha):
            raise QualityGateError(f"Invalid or all-zero frozen_sha forbidden in Nox review: {frozen_sha!r}")
        if not isinstance(author_context_id, str) or not author_context_id.strip():
            raise QualityGateError("author_context_id must be a non-empty non-whitespace string.")
        author_ctx = author_context_id.strip()

        if reviewer_context_id is not None:
            if not isinstance(reviewer_context_id, str) or not reviewer_context_id.strip():
                raise QualityGateError("reviewer_context_id must be a non-empty non-whitespace string.")
            rev_ctx = reviewer_context_id.strip()
        else:
            rev_ctx = f"ctx-antigravity-nox-{uuid.uuid4().hex[:12]}"

        if rev_ctx == author_ctx:
            raise QualityGateError("Self-review prohibited: reviewer_context_id must be distinct from author_context_id.")
        if reviewer_persona not in ("Antigravity-Nox", "Antigravity-Aegis"):
            raise QualityGateError(f"Invalid adversarial reviewer persona: {reviewer_persona!r}")

        has_p0, has_p1_or_p2 = _has_blocking_findings(findings)
        if has_p0:
            verdict = "QUARANTINED"
        elif has_p1_or_p2:
            verdict = "REWORK"
        else:
            verdict = "PASS"

        result = {
            "schema_version": 1,
            "mission_id": mission_id,
            "frozen_sha": frozen_sha,
            "reviewer_context_id": rev_ctx,
            "reviewer_persona": reviewer_persona,
            "author_context_id": author_ctx,
            "inspected_scope": inspected_scope,
            "evidence_inspected": evidence_inspected,
            "findings": findings,
            "verdict": verdict,
        }
        validate_contract(result, "nox-result.schema.json")
        return result

    def assert_review_valid_for_sha(
        self,
        nox_result: dict[str, Any],
        current_candidate_sha: str,
        *,
        expected_mission_id: str | None = None,
    ) -> None:
        validate_contract(nox_result, "nox-result.schema.json")
        if not is_valid_git_sha(current_candidate_sha):
            raise QualityGateError(f"Invalid or all-zero current_candidate_sha: {current_candidate_sha!r}")
        if not is_valid_git_sha(nox_result["frozen_sha"]):
            raise QualityGateError(f"Invalid or all-zero frozen_sha in Nox review: {nox_result['frozen_sha']!r}")
        if expected_mission_id is not None and nox_result["mission_id"] != expected_mission_id:
            raise QualityGateError(
                f"Nox review mission mismatch: review mission_id={nox_result['mission_id']!r} "
                f"!= expected {expected_mission_id!r}"
            )
        if nox_result["frozen_sha"] != current_candidate_sha:
            raise QualityGateError(
                f"Stale Nox review invalidated by commit drift: review frozen_sha={nox_result['frozen_sha']} "
                f"!= current candidate_sha={current_candidate_sha}"
            )
        rev_ctx = nox_result["reviewer_context_id"].strip()
        auth_ctx = nox_result["author_context_id"].strip()
        if not rev_ctx or not auth_ctx:
            raise QualityGateError("Nox review invalid: reviewer_context_id and author_context_id cannot be blank/whitespace.")
        if rev_ctx == auth_ctx:
            raise QualityGateError("Nox review invalid: reviewer and author share context_id.")

        # Independently recompute blocking finding invariants regardless of claimed verdict string
        has_p0, has_p1_or_p2 = _has_blocking_findings(nox_result["findings"])
        if has_p0:
            raise QualityGateError("Nox review invalid: unresolved P0 finding requires QUARANTINED regardless of verdict.")
        if has_p1_or_p2:
            raise QualityGateError("Nox review invalid: unresolved P1 or undisposed P2 finding blocks PASS.")

        if nox_result["verdict"] != "PASS":
            raise QualityGateError(f"Nox review verdict is {nox_result['verdict']!r}, not PASS.")


def classify_failure_output(output_text: str) -> str:
    """Classify a red gate output into one of the 10 canonical failure categories."""
    low = output_text.lower()
    if any(k in low for k in ("sql injection", "idor", "mass assignment", "symlink", "unauthorized", "csrf", "secret")):
        return "security"
    if any(k in low for k in ("sha drift", "base_sha", "non-fast-forward", "branch mismatch")):
        return "drift"
    if any(k in low for k in ("quota", "out of memory", "disk full", "timeout")):
        return "resource"
    if any(k in low for k in ("ambiguous requirement", "missing contract", "financial policy ambiguity")):
        return "requirements"
    if any(k in low for k in ("captive dependency", "scoped service in singleton", "cycle detected", "layer violation")):
        return "architecture"
    if any(k in low for k in ("package not found", "lockfile", "composer.lock", "vulnerable package")):
        return "dependency"
    if any(k in low for k in ("executable not found", "connection refused", "port already in use")):
        return "environment"
    if "flaky" in low:
        return "flaky"
    if "weak assertion" in low or "test syntax" in low:
        return "test"
    return "product"


class SelfHealingController:
    """F12 — Bounded self-healing controller enforcing root-cause repair, regression proof, and retry budgets."""

    def __init__(self, *, max_repair_cycles: int = 5, max_identical_retries: int = 2) -> None:
        self.max_repair_cycles = min(max_repair_cycles, 5)
        self.max_identical_retries = min(max_identical_retries, 2)

    def run_repair_loop(
        self,
        *,
        initial_sha: str,
        evaluate_fn: Callable[[str], dict[str, Any]],
        repair_fn: Callable[[int, str, dict[str, Any]], dict[str, Any]],
        nox_review_fn: Callable[[str, str], dict[str, Any]],
    ) -> dict[str, Any]:
        if not is_valid_git_sha(initial_sha):
            raise QualityGateError(f"Invalid or all-zero initial_sha in SelfHealingController: {initial_sha!r}")
        current_sha = initial_sha
        cycles_used = 0
        failure_counts: dict[str, int] = {}
        history: list[dict[str, Any]] = []
        nox_engine = NoxReviewEngine()

        while True:
            eval_state = evaluate_fn(current_sha)
            author_ctx = str(eval_state.get("author_context_id", "ctx-antigravity-jane-initial")).strip()
            if not author_ctx:
                return {
                    "status": "QUARANTINED",
                    "reason": "Blank author_context_id from evaluate_fn rejected (fail-closed).",
                    "final_sha": current_sha,
                    "cycles_used": cycles_used,
                    "history": history,
                }

            if eval_state["passed"]:
                nox_res = nox_review_fn(current_sha, author_ctx)
                validate_contract(nox_res, "nox-result.schema.json")
                if nox_res["frozen_sha"] != current_sha:
                    return {
                        "status": "QUARANTINED",
                        "reason": f"Stale/mismatched Nox frozen_sha ({nox_res['frozen_sha']} != {current_sha})",
                        "final_sha": current_sha,
                        "cycles_used": cycles_used,
                        "nox_result": nox_res,
                        "history": history,
                    }
                rev_ctx = nox_res["reviewer_context_id"].strip()
                res_author_ctx = nox_res["author_context_id"].strip()
                if not rev_ctx or not res_author_ctx or res_author_ctx != author_ctx or rev_ctx == author_ctx:
                    return {
                        "status": "QUARANTINED",
                        "reason": (
                            "Self-review, blank context, or mismatched author_context_id rejected: "
                            f"eval_author={author_ctx!r}, nox_author={res_author_ctx!r}, nox_reviewer={rev_ctx!r}."
                        ),
                        "final_sha": current_sha,
                        "cycles_used": cycles_used,
                        "nox_result": nox_res,
                        "history": history,
                    }

                has_p0, has_p1_or_p2 = _has_blocking_findings(nox_res["findings"])
                if has_p0 or nox_res["verdict"] == "QUARANTINED":
                    return {
                        "status": "QUARANTINED",
                        "reason": "Unresolved P0 finding or QUARANTINED verdict in Antigravity-Nox review",
                        "final_sha": current_sha,
                        "cycles_used": cycles_used,
                        "nox_result": nox_res,
                        "history": history,
                    }
                if not has_p1_or_p2 and nox_res["verdict"] == "PASS":
                    nox_engine.assert_review_valid_for_sha(nox_res, current_sha)
                    return {
                        "status": "READY",
                        "final_sha": current_sha,
                        "cycles_used": cycles_used,
                        "nox_result": nox_res,
                        "history": history,
                    }

                failure_output = "Nox findings: " + "; ".join(
                    f"{f['id']}:{f['severity']}:{f['contract_violated']}" for f in nox_res["findings"]
                )
            else:
                failure_output = eval_state.get("failure_output", "gate failed")

            failure_class = classify_failure_output(failure_output)
            sig = hashlib.sha256(f"{failure_class}:{failure_output}".encode("utf-8")).hexdigest()[:16]
            failure_counts[sig] = failure_counts.get(sig, 0) + 1

            if failure_class in ("requirements", "drift", "resource"):
                return {
                    "status": "BLOCKED",
                    "reason": f"Non-repairable stop condition ({failure_class}): {failure_output}",
                    "final_sha": current_sha,
                    "cycles_used": cycles_used,
                    "history": history,
                }

            if failure_counts[sig] > self.max_identical_retries:
                return {
                    "status": "BLOCKED",
                    "reason": f"Identical failure retry budget exhausted ({failure_counts[sig] - 1} retries) for signature {sig}",
                    "final_sha": current_sha,
                    "cycles_used": cycles_used,
                    "history": history,
                }

            if cycles_used >= self.max_repair_cycles:
                return {
                    "status": "BLOCKED",
                    "reason": f"Max candidate repair cycles exhausted ({self.max_repair_cycles})",
                    "final_sha": current_sha,
                    "cycles_used": cycles_used,
                    "history": history,
                }

            cycles_used += 1
            repair_outcome = repair_fn(cycles_used, failure_class, eval_state)
            if repair_outcome.get("assertion_weakened"):
                return {
                    "status": "QUARANTINED",
                    "reason": "Assertion weakening detected during repair cycle.",
                    "final_sha": current_sha,
                    "cycles_used": cycles_used,
                    "history": history,
                }
            # Fail-closed default: repair MUST explicitly prove discriminating pre-fix failure
            if repair_outcome.get("regression_failed_prefix", False) is not True:
                return {
                    "status": "BLOCKED",
                    "reason": "Repair did not include a discriminating regression check that fails pre-fix.",
                    "final_sha": current_sha,
                    "cycles_used": cycles_used,
                    "history": history,
                }

            next_sha = repair_outcome.get("new_sha")
            if not is_valid_git_sha(next_sha) or next_sha == current_sha:
                return {
                    "status": "BLOCKED",
                    "reason": f"Repair must produce a distinct valid non-zero 40-char SHA, got {next_sha!r}",
                    "final_sha": current_sha,
                    "cycles_used": cycles_used,
                    "history": history,
                }

            history.append(
                {
                    "cycle": cycles_used,
                    "from_sha": current_sha,
                    "to_sha": next_sha,
                    "failure_class": failure_class,
                    "signature": sig,
                }
            )
            current_sha = next_sha
