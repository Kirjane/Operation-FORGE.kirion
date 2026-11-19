"""F10, F11, F12 — Gate catalog G00–G15, risk profiles, fresh-context Antigravity-Nox review, and bounded self-healing."""
from __future__ import annotations

import hashlib
import uuid
from typing import Any, Callable

from .authority import AuthorityError, validate_contract

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
) -> dict[str, Any]:
    """Verify all required gates for a risk class have non-stale trusted evidence envelopes."""
    if risk_class not in RISK_REQUIRED_GATES:
        raise QualityGateError(f"Unknown risk_class: {risk_class!r}")

    required = list(RISK_REQUIRED_GATES[risk_class])
    na_map = non_applicable_gates or {}
    by_gate: dict[str, dict[str, Any]] = {}
    for env in envelopes:
        validate_contract(env, "evidence-envelope.schema.json")
        if env["candidate_sha"] != candidate_sha:
            raise QualityGateError(
                f"Stale evidence envelope for gate {env['gate_id']}: envelope SHA {env['candidate_sha']} != candidate SHA {candidate_sha}"
            )
        if env["gate_id"] == "G10" and env["evidence_type"] == "BUILD":
            raise QualityGateError("E4 BUILD evidence cannot satisfy G10 (Actual Observable Runtime Verification).")
        by_gate[env["gate_id"]] = env

    missing: list[str] = []
    failed: list[str] = []
    not_run: list[str] = []
    passed: list[str] = []

    for gid in required:
        if gid in na_map:
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
        rev_ctx = reviewer_context_id or f"ctx-antigravity-nox-{uuid.uuid4().hex[:12]}"
        if rev_ctx == author_context_id:
            raise QualityGateError("Self-review prohibited: reviewer_context_id must be distinct from author_context_id.")
        if reviewer_persona not in ("Antigravity-Nox", "Antigravity-Aegis"):
            raise QualityGateError(f"Invalid adversarial reviewer persona: {reviewer_persona!r}")

        has_p0 = any(f["severity"] == "P0" and f["disposition"] == "OPEN" for f in findings)
        has_p1 = any(f["severity"] == "P1" and f["disposition"] == "OPEN" for f in findings)
        has_undisposed_p2 = any(
            f["severity"] == "P2" and f["disposition"] not in ("FIXED", "AUTHORIZED_DISPOSITION") for f in findings
        )

        if has_p0:
            verdict = "QUARANTINED"
        elif has_p1 or has_undisposed_p2:
            verdict = "REWORK"
        else:
            verdict = "PASS"

        result = {
            "schema_version": 1,
            "mission_id": mission_id,
            "frozen_sha": frozen_sha,
            "reviewer_context_id": rev_ctx,
            "reviewer_persona": reviewer_persona,
            "author_context_id": author_context_id,
            "inspected_scope": inspected_scope,
            "evidence_inspected": evidence_inspected,
            "findings": findings,
            "verdict": verdict,
        }
        validate_contract(result, "nox-result.schema.json")
        return result

    def assert_review_valid_for_sha(self, nox_result: dict[str, Any], current_candidate_sha: str) -> None:
        validate_contract(nox_result, "nox-result.schema.json")
        if nox_result["frozen_sha"] != current_candidate_sha:
            raise QualityGateError(
                f"Stale Nox review invalidated by commit drift: review frozen_sha={nox_result['frozen_sha']} "
                f"!= current candidate_sha={current_candidate_sha}"
            )
        if nox_result["reviewer_context_id"] == nox_result["author_context_id"]:
            raise QualityGateError("Nox review invalid: reviewer and author share context_id.")
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
        """
        Execute bounded self-healing cycles:
        - evaluate_fn(sha) -> {'passed': bool, 'failure_output': str, 'author_context_id': str}
        - repair_fn(cycle, failure_class, eval_state) -> {'new_sha': str, 'regression_failed_prefix': bool, 'assertion_weakened': bool}
        - nox_review_fn(sha, author_context_id) -> NoxResult dict
        """
        current_sha = initial_sha
        cycles_used = 0
        failure_counts: dict[str, int] = {}
        history: list[dict[str, Any]] = []

        while True:
            eval_state = evaluate_fn(current_sha)
            author_ctx = eval_state.get("author_context_id", "ctx-antigravity-jane-initial")

            if eval_state["passed"]:
                nox_res = nox_review_fn(current_sha, author_ctx)
                if nox_res["verdict"] == "PASS":
                    return {
                        "status": "READY",
                        "final_sha": current_sha,
                        "cycles_used": cycles_used,
                        "nox_result": nox_res,
                        "history": history,
                    }
                if nox_res["verdict"] == "QUARANTINED":
                    return {
                        "status": "QUARANTINED",
                        "reason": "P0 finding in Antigravity-Nox review",
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

            # Halt immediately on non-auto-repairable authority/requirements/drift stops
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
            if not repair_outcome.get("regression_failed_prefix", True):
                return {
                    "status": "BLOCKED",
                    "reason": "Repair did not include a discriminating regression check that fails pre-fix.",
                    "final_sha": current_sha,
                    "cycles_used": cycles_used,
                    "history": history,
                }

            next_sha = repair_outcome["new_sha"]
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
