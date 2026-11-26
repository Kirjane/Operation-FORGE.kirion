"""W4 evidence applicability and independent fixture trust.

Only trusted in-process fixture composition can supply a plan, issuer keys and
an observation callback. No native or remote trust resolver is shipped. Even a
fully supported fixture cannot authorize production acceptance or delivery.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
from copy import deepcopy
from pathlib import Path

from .authority import AuthorityError, validate_contract, is_valid_git_sha
from .evidence import read_assurance_artifact
from .mission_contract import (_check_json, _unique_pairs, _invalid_constant,
                               canonical_json, contract_digest, digest_json)
from .quality import (assert_assurance_applicable_envelope, EVIDENCE_LEVEL_ORDER,
                      NoxReviewEngine, RISK_REQUIRED_GATES)


class AssuranceError(AuthorityError):
    """A structured assurance denial, not a product failure."""


def require(condition, reason):
    if not condition:
        raise AssuranceError(reason)


def assurance_denial(exc):
    # Stable reason for deliberate denials; don't echo arbitrary provider errors
    # or signed payload values (which can include sensitive material).
    reason = str(exc) if isinstance(exc, AssuranceError) else "INVALID_OR_UNAVAILABLE_ASSURANCE"
    return {"status": "BLOCKED", "overall_status": "BLOCKED", "reason": reason,
            "fixture_only": True, "promotion_authorized": False,
            "actual_product_outcome": "NOT_TESTED"}


def strict_json(raw):
    require(type(raw) in (str, bytes), "RAW_JSON_REQUIRED")
    try:
        obj = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
        _check_json(obj)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise AssuranceError("MALFORMED_ASSURANCE_JSON") from exc
    require(type(obj) is dict, "OBJECT_REQUIRED")
    return obj


def same(left, right):
    return canonical_json(left) == canonical_json(right)


def utc(value):
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.utcoffset() == dt.timedelta(0), "UTC_REQUIRED")
        return result
    except (AttributeError, ValueError, TypeError) as exc:
        raise AssuranceError("INVALID_TIMESTAMP") from exc


def signed_material(record):
    return canonical_json({k: v for k, v in record.items() if k != "signature"}).encode("utf-8")


class FixtureAssuranceResolver:
    """Explicit synthetic trust boundary; not constructible from mission ingress.

    Keys, plans and current observation provider belong to the test/operator
    composition. A receipt is data, never a trust registration. Do not expose
    this class, its keys or the observer to an untrusted worker process.
    """

    def __init__(self, *, plans, issuers, artifact_store_root: Path, observe):
        self._plans = deepcopy(plans)
        self._issuers = deepcopy(issuers)
        self._root = artifact_store_root.resolve()
        self._observe = observe
        actors = [v["actor_id"] for v in self._issuers.values()]
        keys = [v["key"] for v in self._issuers.values()]
        contexts = [v["context_id"] for v in self._issuers.values()]
        require(len(actors) == len(set(actors)) and len(keys) == len(set(keys)) and
                len(contexts) == len(set(contexts)) and
                all(type(key) is bytes and len(key) >= 32 for key in keys),
                "ISSUER_INDEPENDENCE_CONFIGURATION_INVALID")

    def plan(self, packet, attempt, binding):
        plan = deepcopy(self._plans.get(attempt["reservation_id"]))
        require(type(plan) is dict, "TRUSTED_ASSURANCE_PLAN_UNAVAILABLE")
        expected = {"contract_sha256": contract_digest(packet), "revision": packet["revision"],
                    "reservation_id": attempt["reservation_id"], "grant_sha256": binding["grant_sha256"],
                    "worker_actor_id": attempt["actor_id"], "run_id": packet["run_id"],
                    "attempt_result_sha256": digest_json(json.loads(attempt["result_json"])),
                    "adapter_binding": binding.get("adapter_binding", {"kind": "CALLBACK_FIXTURE"})}
        require(all(same(plan.get(k), v) for k, v in expected.items()), "ASSURANCE_PLAN_BINDING_MISMATCH")
        require(plan["target"]["profile"] in {"SYNTHETIC", "MOCK"}, "REAL_TARGET_TRUST_UNAVAILABLE")
        require(plan["target"]["repo_id"] == packet["repo_id"] and
                plan["target"]["repo_name"] == packet["repo_name"] and
                plan["target"]["branch"] == packet["permitted_branch"], "PLAN_TARGET_MISMATCH")
        require(is_valid_git_sha(plan["candidate_sha"]) and is_valid_git_sha(plan["tree_sha"]),
                "PLAN_SOURCE_UNANCHORED")
        require(plan["author_actor_id"] == attempt["actor_id"], "AUTHOR_GRANT_MISMATCH")
        require(type(plan["oracles"]) is dict, "ORACLE_PLAN_UNAVAILABLE")
        now = dt.datetime.now(dt.timezone.utc)
        require(utc(plan["observed_at_utc"]) <= now < utc(plan["expires_at_utc"]) <= utc(binding["valid_until_utc"]),
                "ASSURANCE_PLAN_STALE")
        # Independently supplied current readback, not target/runtime from ingress.
        actual = self._observe(deepcopy(plan))
        require(type(actual) is dict and same(actual, {k: plan[k] for k in
                ("candidate_sha", "tree_sha", "target", "runtime_sha256", "environment_versions")}),
                "CURRENT_SOURCE_TARGET_OR_RUNTIME_DRIFT")
        return plan

    def verify_issuer(self, record, plan, role, now):
        issuer = self._issuers.get(record["issuer_id"])
        require(type(issuer) is dict and issuer.get("role") == role, "UNTRUSTED_ISSUER")
        require(record["issuer_actor_id"] == issuer["actor_id"] and
                record["issuer_context_id"] == issuer["context_id"], "ISSUER_IDENTITY_MISMATCH")
        require(issuer.get("revoked") is False and utc(issuer["valid_from_utc"]) <= now <
                utc(issuer["expires_at_utc"]), "ISSUER_REVOKED_OR_STALE")
        require(contract_scope(plan) in issuer["contracts"], "ISSUER_CONTRACT_SCOPE_MISMATCH")
        expected = hmac.new(issuer["key"], signed_material(record), hashlib.sha256).hexdigest()
        require(hmac.compare_digest(expected, record["signature"]), "RECEIPT_SIGNATURE_INVALID")
        require(utc(plan["observed_at_utc"]) <= utc(record["issued_at_utc"]) <= now <
                utc(record["expires_at_utc"]) <= utc(plan["expires_at_utc"]), "RECEIPT_STALE")
        author = plan["author_actor_id"]
        if role == "WRITER":
            require(issuer["actor_id"] == author and issuer["context_id"] == plan["author_context_id"],
                    "WRITER_GRANT_IDENTITY_MISMATCH")
        else:
            require(issuer["actor_id"] != author and issuer["context_id"] != plan["author_context_id"],
                    "SELF_APPROVAL_DENIED")
        return issuer

    def verify_receipt(self, packet, attempt, binding, raw):
        record = strict_json(raw)
        validate_contract(record, "assurance-receipt.schema.json")
        validate_contract(record["envelope"], "evidence-envelope.schema.json")
        plan = self.plan(packet, attempt, binding)
        env = record["envelope"]
        oracle = next((o for o in packet["oracles"] if o["oracle_id"] == record["oracle_id"]), None)
        require(oracle is not None, "WRONG_ORACLE")
        source = next(s for s in packet["source_authorities"] if s["source_id"] == oracle["source_id"])
        configured = plan["oracles"].get(oracle["oracle_id"])
        require(type(configured) is dict and configured.get("oracle_sha256") == digest_json(oracle)
                and configured.get("source_sha256") == digest_json(source), "ORACLE_TRUST_UNAVAILABLE")
        expected = {
            "contract_sha256": contract_digest(packet), "revision": packet["revision"],
            "repo_id": packet["repo_id"], "repo_name": packet["repo_name"], "base_sha": packet["base_sha"],
            "branch": packet["permitted_branch"], "objective_sha256": digest_json(packet["objective"]),
            "grant_sha256": binding["grant_sha256"], "reservation_id": attempt["reservation_id"],
            "attempt_ordinal": attempt["ordinal"], "worker_actor_id": attempt["actor_id"],
            "plan_sha256": digest_json(plan), "oracle_sha256": digest_json(oracle),
            "source_sha256": digest_json(source), "outcome_ids": oracle["outcome_ids"],
            "target": plan["target"], "runtime_sha256": plan["runtime_sha256"],
        }
        for key, value in expected.items():
            require(same(record[key], value), "RECEIPT_BINDING_MISMATCH:" + key)
        role = "REVIEWER" if oracle["gate_id"] == "G13" else "WRITER"
        require(record["issuer_role"] == role, "WRONG_ISSUER_ROLE")
        issuer = self.verify_issuer(record, plan, role, dt.datetime.now(dt.timezone.utc))
        require(oracle["oracle_id"] in issuer["oracles"], "ISSUER_ORACLE_SCOPE_MISMATCH")
        require(EVIDENCE_LEVEL_ORDER[env["evidence_level"]] <= EVIDENCE_LEVEL_ORDER[issuer["max_level"]]
                <= EVIDENCE_LEVEL_ORDER["E5"], "EVIDENCE_CEILING_EXCEEDED")
        require(oracle["target_profile"] == plan["target"]["profile"] and
                oracle["environment"] == plan["target"]["environment"], "ORACLE_TARGET_MISMATCH")
        for key, value in {"mission_id": packet["mission_id"], "run_id": packet["run_id"],
                           "candidate_sha": plan["candidate_sha"], "tree_sha": plan["tree_sha"],
                           "stage": configured["stage"], "cwd": plan["target"]["cwd"],
                           "environment_versions": plan["environment_versions"],
                           "fixture_sha256": oracle["fixture_sha256"] or "0" * 64}.items():
            require(same(env[key], value), "ENVELOPE_BINDING_MISMATCH:" + key)
        require(utc(plan["observed_at_utc"]) <= utc(env["started_at_utc"]) <=
                utc(env["completed_at_utc"]) <= utc(record["issued_at_utc"]), "EXECUTION_TIME_MISMATCH")
        require(same(env["command_argv"], oracle["command_argv"] or configured["observation_argv"]),
                "COMMAND_OR_OBSERVATION_MISMATCH")
        assert_assurance_applicable_envelope(env, oracle)
        artifact = strict_json(read_assurance_artifact(self._root, env))
        artifact_expected = {"schema_version": 1, "oracle_sha256": digest_json(oracle),
                             "source_sha256": digest_json(source), "target": plan["target"],
                             "candidate_sha": plan["candidate_sha"], "tree_sha": plan["tree_sha"],
                             "runtime_sha256": plan["runtime_sha256"], "nonce": record["nonce"],
                             "reservation_id": attempt["reservation_id"], "outcome_ids": oracle["outcome_ids"],
                             "negative_scenario": oracle["negative_control"]}
        require(set(artifact) == set(artifact_expected) | {"observed", "negative_observed", "review", "finding_proofs"},
                "OBSERVATION_SHAPE_MISMATCH")
        require(all(same(artifact[k], v) for k, v in artifact_expected.items()), "OBSERVATION_BINDING_MISMATCH")
        # Fixed exact structured comparator; all required observation keys must
        # be present. A 403 with the wrong reason is not the authorized denial.
        positive, negative = configured["expected"], configured["negative_expected"]
        require(type(positive) is dict and bool(positive) and type(negative) is dict and
                set(positive) == set(negative) and not same(positive, negative), "NEGATIVE_CONTROL_UNQUALIFIED")
        require(type(artifact["observed"]) is dict and set(artifact["observed"]) == set(positive),
                "OBSERVATION_SCOPE_INCOMPLETE")
        require(same(artifact["negative_observed"], negative), "NEGATIVE_CONTROL_MISMATCH")
        verdict = "PASS" if same(artifact["observed"], positive) else "FAIL"
        require(env["status"] == verdict and env["exit_code"] is not None and
                (verdict != "PASS" or env["exit_code"] == 0), "ORACLE_RESULT_MISMATCH")
        review = artifact["review"]
        proofs = artifact["finding_proofs"]
        require(type(proofs) is dict, "FINDING_PROOFS_INVALID")
        if role == "REVIEWER":
            require(type(review) is dict, "REVIEW_RECEIPT_MISSING")
            validate_contract(review, "nox-result.schema.json")
            require(review["mission_id"] == packet["mission_id"] and review["frozen_sha"] == plan["candidate_sha"]
                    and review["reviewer_context_id"] == issuer["context_id"] and
                    review["author_context_id"] == plan["author_context_id"], "REVIEW_IDENTITY_OR_SOURCE_MISMATCH")
            require(set(configured["review_scope"]) <= set(review["inspected_scope"]), "REVIEW_SCOPE_INCOMPLETE")
            finding_ids = [f["id"] for f in review["findings"]]
            require(len(finding_ids) == len(set(finding_ids)), "DUPLICATE_FINDING")
            # Independently configured known finding inventory cannot be omitted.
            known = configured["known_findings"]
            require(type(known) is dict and set(known) <= set(finding_ids), "KNOWN_FINDING_OMITTED")
            required_proofs = set()
            for finding in review["findings"]:
                fid = finding["id"]
                if fid in known:
                    require(all(same(finding[k], v) for k, v in known[fid].items()),
                            "KNOWN_FINDING_IDENTITY_MISMATCH")
                if finding["severity"] in {"P0", "P1", "P2"}:
                    if finding["disposition"] == "FIXED":
                        required_proofs.add(fid)
                        require(type(proofs.get(fid)) is str and proofs[fid] in review["evidence_inspected"],
                                "FINDING_FIX_PROOF_MISSING")
                    elif finding["disposition"] == "AUTHORIZED_DISPOSITION":
                        required_proofs.add(fid)
                        require(finding["severity"] == "P2" and fid in configured["authorized_dispositions"] and
                                proofs.get(fid) == configured["authorized_dispositions"][fid],
                                "FINDING_DISPOSITION_AUTHORITY_MISSING")
            require(set(proofs) == required_proofs, "FINDING_PROOF_SCOPE_MISMATCH")
            if verdict == "PASS":
                NoxReviewEngine().assert_review_valid_for_sha(review, plan["candidate_sha"],
                                                              expected_mission_id=packet["mission_id"])
        else:
            require(review is None and not proofs, "WRITER_CANNOT_ISSUE_REVIEW")
        return {"record": record, "receipt_sha256": digest_json(record), "verdict": verdict,
                "review": review, "finding_proofs": proofs, "fixture_only": True}

    def verify_decision(self, packet, attempt, binding, raw, receipts):
        decision = strict_json(raw)
        validate_contract(decision, "assurance-decision.schema.json")
        plan = self.plan(packet, attempt, binding)
        expected = {"contract_sha256": contract_digest(packet), "revision": packet["revision"],
                    "reservation_id": attempt["reservation_id"], "plan_sha256": digest_json(plan),
                    "candidate_sha": plan["candidate_sha"], "tree_sha": plan["tree_sha"],
                    "receipt_sha256s": sorted(r["receipt_sha256"] for r in receipts)}
        require(all(same(decision[k], v) for k, v in expected.items()), "DECISION_BINDING_MISMATCH")
        self.verify_issuer(decision, plan, "ACCEPTANCE", dt.datetime.now(dt.timezone.utc))
        require(all(decision["issuer_actor_id"] != r["record"]["issuer_actor_id"] for r in receipts),
                "ACCEPTANCE_INDEPENDENCE_DENIED")
        return decision


def contract_scope(plan):
    return plan["contract_sha256"]


def evaluate_applicable_receipts(packet, receipts):
    """Only authenticated, applicable, read-back receipts enter this aggregation."""
    required = (set(RISK_REQUIRED_GATES[packet["risk_class"]]) | set(packet["required_gates"])) - set(
        packet.get("non_applicable_gates", {}))
    expected = {o["oracle_id"]: o for o in packet["oracles"]}
    by_oracle = {}
    for receipt in receipts:
        by_oracle.setdefault(receipt["record"]["oracle_id"], []).append(receipt)
    missing, failed, conflicted, passed = [], [], [], []
    for gid in sorted(required):
        oracles = [oid for oid, oracle in expected.items() if oracle["gate_id"] == gid]
        if not oracles or any(not by_oracle.get(oid) for oid in oracles):
            missing.append(gid)
        if any(len(by_oracle.get(oid, [])) > 1 for oid in oracles):
            conflicted.append(gid)
        if any(r["verdict"] == "FAIL" for oid in oracles for r in by_oracle.get(oid, [])):
            failed.append(gid)
        if gid not in missing + failed + conflicted:
            passed.append(gid)
    # The independent review must cite every applicable writer receipt.
    writer = {r["receipt_sha256"] for r in receipts if r["record"]["issuer_role"] == "WRITER"}
    reviews = [r for r in receipts if r["record"]["issuer_role"] == "REVIEWER"]
    review_complete = bool(reviews) and all(r["review"] and
        set(r["review"]["evidence_inspected"]) == writer for r in reviews)
    if not review_complete and "G13" in passed:
        passed.remove("G13")
        missing.append("G13")
    return {"overall_status": "PASS" if not (missing or failed or conflicted) else "BLOCKED",
            "passed_gates": passed, "missing_gates": sorted(set(missing)), "failed_gates": failed,
            "conflicted_gates": conflicted, "documented_non_applicable": packet.get("non_applicable_gates", {}),
            "fixture_only": True, "promotion_authorized": False, "actual_product_outcome": "NOT_TESTED"}
