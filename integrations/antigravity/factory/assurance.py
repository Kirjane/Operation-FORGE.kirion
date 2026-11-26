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
from .policy import normalize_rel_path, path_matches_prefix
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
            "applicability": "UNVERIFIED",
            "fixture_only": True, "promotion_authorized": False,
            "actual_product_outcome": "NOT_TESTED"}


def strict_json(raw):
    require(type(raw) in (str, bytes), "RAW_JSON_REQUIRED")
    try:
        if type(raw) is bytes:
            raw = raw.decode("utf-8", errors="strict")
        require(len(raw) <= 8 * 1024 * 1024, "ASSURANCE_JSON_TOO_LARGE")
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


def execution_projection(record):
    """Canonical execution identity, independent of issuer signature.

    A trusted fixture capture provider resolves this material by reservation,
    oracle and nonce, from its own observation rather than from receipt ingress.
    """
    env = record["envelope"]
    return {"schema_version": 1,
            "binding": {k: v for k, v in record.items()
                        if k not in {"signature", "execution_sha256", "envelope"}},
            "envelope_sha256": digest_json(env), "artifact_sha256": env["artifact_sha256"],
            "artifact_size_bytes": env["artifact_size_bytes"]}


class FixtureAssuranceResolver:
    """Explicit synthetic trust boundary; not constructible from mission ingress.

    Keys, plans and current observation provider belong to the test/operator
    composition. A receipt is data, never a trust registration. Do not expose
    this class, its keys or the observer to an untrusted worker process.
    """

    def __init__(self, *, plans, issuers, artifact_store_root: Path, observe, resolve_execution=None):
        self._plans = deepcopy(plans)
        self._issuers = deepcopy(issuers)
        self._root = artifact_store_root.resolve()
        self._observe = observe
        self._resolve_execution = resolve_execution
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
        # Per-oracle current readback, not target/runtime from ingress. A
        # source check, browser journey and device check need not share a host.
        oracle_observations = {}
        for oid, configured in plan["oracles"].items():
            target = configured["target"]
            require(target["profile"] in {"MOCK", "SYNTHETIC"} and
                    target["repo_id"] == packet["repo_id"] and target["repo_name"] == packet["repo_name"]
                    and target["branch"] == packet["permitted_branch"], "ORACLE_TARGET_TRUST_UNAVAILABLE")
            require(all(type(target[k]) is str and target[k].strip() for k in
                        ("kind", "environment", "data_authority", "cwd")), "TARGET_IDENTITY_INCOMPLETE")
            oracle_observations[oid] = {k: configured[k] for k in
                ("target", "runtime_sha256", "environment_versions", "source_sha256",
                 "oracle_blob_sha", "observed_source_comparisons")}
        expected_observation = {"candidate_sha": plan["candidate_sha"], "tree_sha": plan["tree_sha"],
                                "oracles": oracle_observations}
        try:
            actual = self._observe(deepcopy(plan))
        except Exception as exc:
            raise AssuranceError("CURRENT_OBSERVATION_UNAVAILABLE") from exc
        require(type(actual) is dict and same(actual, expected_observation),
                "CURRENT_SOURCE_TARGET_OR_RUNTIME_DRIFT")
        require(dt.datetime.now(dt.timezone.utc) < utc(plan["expires_at_utc"]), "ASSURANCE_PLAN_STALE")
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
        require(max(utc(plan["observed_at_utc"]), utc(issuer["valid_from_utc"])) <=
                utc(record["issued_at_utc"]) <= now < utc(record["expires_at_utc"]) <=
                min(utc(plan["expires_at_utc"]), utc(issuer["expires_at_utc"])), "RECEIPT_STALE")
        author = plan["author_actor_id"]
        if role == "WRITER":
            require(issuer["actor_id"] == author and issuer["context_id"] == plan["author_context_id"],
                    "WRITER_GRANT_IDENTITY_MISMATCH")
        else:
            require(issuer["actor_id"] != author and issuer["context_id"] != plan["author_context_id"],
                    "SELF_APPROVAL_DENIED")
        return issuer

    def verify_execution(self, record):
        """A correct issuer signature is insufficient to prove execution."""
        require(callable(self._resolve_execution), "TRUSTED_EXECUTION_OBSERVATION_UNAVAILABLE")
        try:
            actual = self._resolve_execution(record["reservation_id"], record["oracle_id"], record["nonce"])
        except Exception as exc:
            raise AssuranceError("TRUSTED_EXECUTION_OBSERVATION_UNAVAILABLE") from exc
        require(type(actual) is dict, "TRUSTED_EXECUTION_OBSERVATION_MISSING")
        expected = execution_projection(record)
        require(same(actual, expected) and digest_json(actual) == record["execution_sha256"],
                "EXECUTION_RECEIPT_BINDING_MISMATCH")
        return record["execution_sha256"]

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
                and configured.get("source_sha256") == digest_json(source)
                and configured.get("oracle_blob_sha") == oracle["blob_sha"], "ORACLE_TRUST_UNAVAILABLE")
        expected = {
            "contract_sha256": contract_digest(packet), "revision": packet["revision"],
            "repo_id": packet["repo_id"], "repo_name": packet["repo_name"], "base_sha": packet["base_sha"],
            "branch": packet["permitted_branch"], "objective_sha256": digest_json(packet["objective"]),
            "grant_sha256": binding["grant_sha256"], "reservation_id": attempt["reservation_id"],
            "attempt_ordinal": attempt["ordinal"], "worker_actor_id": attempt["actor_id"],
            "plan_sha256": digest_json(plan), "oracle_sha256": digest_json(oracle),
            "source_sha256": digest_json(source), "outcome_ids": oracle["outcome_ids"],
            "target": configured["target"], "runtime_sha256": configured["runtime_sha256"],
        }
        for key, value in expected.items():
            require(same(record[key], value), "RECEIPT_BINDING_MISMATCH:" + key)
        role = "REVIEWER" if oracle["gate_id"] == "G13" else "WRITER"
        require(record["issuer_role"] == role, "WRONG_ISSUER_ROLE")
        issuer = self.verify_issuer(record, plan, role, dt.datetime.now(dt.timezone.utc))
        require(oracle["oracle_id"] in issuer["oracles"], "ISSUER_ORACLE_SCOPE_MISMATCH")
        execution_sha256 = self.verify_execution(record)
        require(EVIDENCE_LEVEL_ORDER[env["evidence_level"]] <= EVIDENCE_LEVEL_ORDER[issuer["max_level"]]
                <= EVIDENCE_LEVEL_ORDER["E5"], "EVIDENCE_CEILING_EXCEEDED")
        target = configured["target"]
        require(oracle["target_profile"] == target["profile"] and
                oracle["environment"] == target["environment"], "ORACLE_TARGET_MISMATCH")
        require(configured["runtime_sha256"] != "0" * 64, "RUNTIME_IDENTITY_UNANCHORED")
        if target["kind"] == "device-fixture":
            require(bool(target["device_id"]) and target["executable_sha256"] not in {None, "0" * 64}
                    and target["signing_policy_sha256"] not in {None, "0" * 64}, "DEVICE_OR_SIGNING_IDENTITY_MISSING")
        if oracle["gate_id"] in {"G07", "G09", "G10", "G11"}:
            allowed_targets = {"G07": {"database-fixture"}, "G09": {"runtime-fixture", "database-fixture"},
                               "G10": {"runtime-fixture", "browser-fixture", "device-fixture"},
                               "G11": {"browser-fixture", "device-fixture"}}
            require(target["kind"] in allowed_targets[oracle["gate_id"]], "RUNTIME_GATE_TARGET_KIND_MISMATCH")
        for key, value in {"mission_id": packet["mission_id"], "run_id": packet["run_id"],
                           "candidate_sha": plan["candidate_sha"], "tree_sha": plan["tree_sha"],
                           "stage": configured["stage"], "cwd": configured["target"]["cwd"],
                           "environment_versions": configured["environment_versions"],
                           "fixture_sha256": oracle["fixture_sha256"] or "0" * 64}.items():
            require(same(env[key], value), "ENVELOPE_BINDING_MISMATCH:" + key)
        require(utc(plan["observed_at_utc"]) <= utc(env["started_at_utc"]) <=
                utc(env["completed_at_utc"]) <= utc(record["issued_at_utc"]), "EXECUTION_TIME_MISMATCH")
        require(same(env["command_argv"], oracle["command_argv"] or configured["observation_argv"]),
                "COMMAND_OR_OBSERVATION_MISMATCH")
        try:
            assert_assurance_applicable_envelope(env, oracle)
            artifact = strict_json(read_assurance_artifact(self._root, env))
        except AuthorityError as exc:
            # The existing quality and artifact helpers use fixed reason codes.
            reason = str(exc)
            if reason in {"EVIDENCE_TYPE_OR_GATE_MISMATCH", "EVIDENCE_FLOOR_OR_CEILING_MISMATCH",
                          "EVIDENCE_PROVENANCE_OR_SOURCE_MISMATCH", "EVIDENCE_NOT_EXECUTED",
                          "ARTIFACT_IDENTITY_INVALID", "ARTIFACT_PATH_MISMATCH", "ARTIFACT_PATH_UNSAFE",
                          "ARTIFACT_CONTENT_MISMATCH"}:
                raise AssuranceError(reason) from exc
            raise
        artifact_expected = {"schema_version": 1, "oracle_sha256": digest_json(oracle),
                             "source_sha256": digest_json(source), "target": configured["target"],
                             "candidate_sha": plan["candidate_sha"], "tree_sha": plan["tree_sha"],
                             "runtime_sha256": configured["runtime_sha256"], "nonce": record["nonce"],
                             "reservation_id": attempt["reservation_id"], "outcome_ids": oracle["outcome_ids"],
                             "negative_scenario": oracle["negative_control"]}
        require(set(artifact) == set(artifact_expected) | {"observed", "negative_observed", "review", "finding_proofs", "source_comparisons"},
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
        # A receipt cannot compare an unrelated blob or silently omit a
        # required path. Compare actual per-path readback to authorized identity.
        comparisons = configured["source_comparisons"]
        actual_comparisons = configured["observed_source_comparisons"]
        require(type(comparisons) is dict and type(actual_comparisons) is dict and
                set(comparisons) == set(actual_comparisons) and
                same(artifact["source_comparisons"], actual_comparisons), "SOURCE_COMPARISON_BINDING_MISMATCH")
        if env["evidence_type"] == "SOURCE":
            require(comparisons.get(oracle["path"]) == oracle["blob_sha"] and all(
                normalize_rel_path(p) == p and any(path_matches_prefix(p, scope) for scope in source["scope"])
                and is_valid_git_sha(comparisons[p]) and is_valid_git_sha(actual_comparisons[p])
                for p in comparisons), "SOURCE_COMPARISON_SCOPE_INCOMPLETE")
        else:
            require(not comparisons, "UNEXPECTED_SOURCE_COMPARISON")
        verdict = "PASS" if same(artifact["observed"], positive) and same(comparisons, actual_comparisons) else "FAIL"
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
            require(len(review["evidence_inspected"]) == len(set(review["evidence_inspected"])),
                    "DUPLICATE_REVIEW_EVIDENCE")
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
                        require(type(proofs.get(fid)) is str and proofs[fid] in review["evidence_inspected"]
                                and bool(configured["finding_fix_oracles"].get(fid)),
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
                "execution_sha256": execution_sha256,
                "review": review, "finding_proofs": proofs,
                "finding_fix_oracles": configured.get("finding_fix_oracles", {}), "fixture_only": True}

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
    writer = {r["receipt_sha256"]: r for r in receipts if r["record"]["issuer_role"] == "WRITER"}
    reviews = [r for r in receipts if r["record"]["issuer_role"] == "REVIEWER"]

    def review_has_relevant_proofs(receipt):
        review = receipt["review"]
        if not review or set(review["evidence_inspected"]) != set(writer):
            return False
        for finding in review["findings"]:
            if finding["severity"] not in {"P0", "P1", "P2"} or finding["disposition"] != "FIXED":
                continue
            proof = writer.get(receipt["finding_proofs"].get(finding["id"]))
            if (not proof or proof["verdict"] != "PASS" or proof["record"]["oracle_id"] not in
                    receipt["finding_fix_oracles"].get(finding["id"], [])):
                return False
        return True

    review_complete = bool(reviews) and all(review_has_relevant_proofs(r) for r in reviews)
    if not review_complete and "G13" in passed:
        passed.remove("G13")
        missing.append("G13")
    return {"overall_status": "PASS" if not (missing or failed or conflicted) else "BLOCKED",
            "passed_gates": passed, "missing_gates": sorted(set(missing)), "failed_gates": failed,
            "conflicted_gates": conflicted, "documented_non_applicable": packet.get("non_applicable_gates", {}),
            "fixture_only": True, "promotion_authorized": False, "actual_product_outcome": "NOT_TESTED"}
