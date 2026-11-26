"""W5 progressive context loading and fixture consumption receipts.

Registry metadata, selected IDs, retrieved bytes and actual reads are distinct.
Only the supported in-process fixture context issues consumption receipts.
A real host must implement an independently observed consumption boundary;
manual/advisory availability is never reclassified as native loading.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
import weakref
from copy import deepcopy

from .mission_contract import contract_digest
from .authority import validate_contract
from .skill_registry import SkillRegistry, SkillError, require, canonical, digest, MAX_REFERENCE_FILES
from .policy import FRONTEND_PERSONAS


def skill_denial(exc):
    return {"status": "BLOCKED", "reason": str(exc) if isinstance(exc, SkillError) else "SKILL_CONTEXT_INVALID",
            "native_loading_verified": False, "promotion_authorized": False, "replay_permitted": False}


def _brain_bytes(packet, config):
    """Read the existing W3B stage context shape; the source is trusted fixture
    composition, not a new verifier of the native lifecycle HMAC.
    """
    cognition = packet["cognition"]
    context = config.get("brain_stage_context")
    other = config.get("other_context_bytes", 0)
    require(type(other) is int and other >= 0, "CONTEXT_BUDGET_INVALID")
    if cognition["mode"] != "INHERITED":
        require(not packet["authority"]["brain_required"] and context is None,
                "REQUIRED_BRAIN_CONTEXT_UNAVAILABLE")
        return other, config["max_context_bytes"], None, 24
    require(type(context) is dict and config.get("brain_run_id") == cognition["brain_run_id"],
            "BRAIN_STAGE_CONTEXT_UNAVAILABLE")
    checkpoint = context["checkpoint"]
    manifest = checkpoint["context_manifest"]
    require(checkpoint["stage"] == config["stage"] and checkpoint["effective_stage"] == config["stage"]
            and checkpoint["context_sha256"] == cognition["context_sha256"]
            and digest(manifest) == cognition["context_sha256"]
            and digest({k: v for k, v in checkpoint.items() if k != "checkpoint_sha256"})
                == checkpoint["checkpoint_sha256"]
            and manifest["status"] == "RESOLVED" and not manifest["missing_required"]
            and not manifest["required_not_loaded"], "BRAIN_STAGE_OR_MANIFEST_MISMATCH")
    docs = context["documents"]
    require(type(docs) is list and len(docs) == manifest["document_count"] and
            len({d["path"] for d in docs}) == len(docs), "BRAIN_DOCUMENT_COVERAGE_MISMATCH")
    total = 0
    projected = []
    for doc in docs:
        raw = doc["content"].encode("utf-8")
        require(len(raw) == doc["bytes"] and hashlib.sha256(raw).hexdigest() == doc["sha256"],
                "BRAIN_DOCUMENT_CONTENT_MISMATCH")
        total += len(raw)
        projected.append({k: v for k, v in doc.items() if k != "content"})
    require(projected == manifest["documents"] and total == manifest["total_bytes"] and
            total <= manifest["byte_budget"] and len(docs) <= manifest["document_budget"],
            "BRAIN_CONTEXT_ACCOUNTING_MISMATCH")
    return (total + other, min(config["max_context_bytes"], manifest["byte_budget"]),
            checkpoint["checkpoint_sha256"], manifest["document_budget"] - len(docs))


class PreparedSkillContext:
    def __init__(self, plan, contents, binding):
        self._plan = deepcopy(plan)
        self._contents = dict(contents)
        self._binding = deepcopy(binding)
        self.plan_sha256 = digest({"plan": self._plan, "binding": self._binding})

    def summary(self):
        return {**deepcopy(self._plan), "binding": deepcopy(self._binding),
                "plan_sha256": self.plan_sha256, "native_loading_verified": False}


class FixtureSkillInput:
    """Read-only skill input actually made available to a fixture consumer.

    read() marks bytes delivered, not semantic model comprehension. Optional
    retrieved inputs that the callback never accesses remain not loaded.
    """
    def __init__(self, prepared):
        self._contents = dict(prepared._contents)
        self._sources = {x["id"]: x["source"] for x in prepared._plan["selected"]}
        self._dependencies = {x["id"]: x["dependencies"] for x in prepared._plan["selected"]}
        self._reads = []
        self._closed = False

    def available_ids(self):
        return tuple(self._contents)

    def read(self, skill_id):
        require(not self._closed and skill_id in self._contents, "SKILL_INPUT_UNAVAILABLE")
        require(set(self._dependencies[skill_id]) <= set(self._reads), "SKILL_DEPENDENCY_NOT_CONSUMED")
        raw = self._contents[skill_id]
        require(hashlib.sha256(raw).hexdigest() == self._sources[skill_id]["sha256"]
                and len(raw) == self._sources[skill_id]["bytes"], "SKILL_INPUT_CHANGED")
        if skill_id not in self._reads:
            self._reads.append(skill_id)
        return raw.decode("utf-8")

    def close(self):
        self._closed = True
        return tuple(self._reads)


class FixtureSkillRuntime:
    """Trusted fixture composition, no native worker credentials or rights.

    configs keyed by exact contract digest, never provided by mission ingress.
    signing_key belongs to the fixture runtime, not to its consumer. This
    proves local fixture delivery, not a real host/model skill load.
    """
    def __init__(self, registry, *, configs, signing_key):
        require(type(registry) is SkillRegistry and type(signing_key) is bytes and len(signing_key) >= 32,
                "TRUSTED_SKILL_CONFIGURATION_REQUIRED")
        self._registry = registry
        self._configs = deepcopy(configs)
        self._key = signing_key
        self._issued = set()
        self._prepared = weakref.WeakKeyDictionary()

    def prepare(self, packet, *, grant=None, require_consumable=False):
        from .dispatcher import STACK_SKILL_BUNDLES
        contract = contract_digest(packet)
        cfg = self._configs.get(contract)
        require(type(cfg) is dict and cfg.get("run_id") == packet["run_id"]
                and cfg.get("revision") == packet["revision"], "SKILL_MISSION_CONFIGURATION_UNAVAILABLE")
        require(cfg["profile"] in STACK_SKILL_BUNDLES and cfg["host"] in {"fixture", "chatgpt", "codex", "antigravity"},
                "SKILL_PROFILE_OR_HOST_UNAVAILABLE")
        require(packet["selected_skills"]["skill_source_sha"] == self._registry.identity["commit_sha"],
                "SKILL_REGISTRY_PIN_MISMATCH")
        require(all(type(cfg.get(k)) is str and bool(cfg[k]) for k in ("actor_id", "host_id", "context_id"))
                and type(cfg.get("attempt_ordinal")) is int and cfg["attempt_ordinal"] >= 1,
                "SKILL_CONSUMER_IDENTITY_UNAVAILABLE")
        if require_consumable:
            require(cfg["host"] == "fixture" and type(grant) is dict,
                    "NATIVE_SKILL_CONSUMPTION_UNAVAILABLE")
        if grant is not None:
            require(all(grant.get(k) == cfg[k] for k in ("actor_id", "host_id", "attempt_ordinal"))
                    and grant.get("contract_sha256") == contract and grant.get("revision") == packet["revision"],
                    "SKILL_GRANT_BINDING_MISMATCH")
        used, limit, checkpoint, document_remaining = _brain_bytes(packet, cfg)
        require(document_remaining > 0, "SKILL_CONTEXT_DOCUMENT_BUDGET_EXCEEDED")
        required = ["kirion-core", "kirion-dispatch", *STACK_SKILL_BUNDLES[cfg["profile"]]]
        frontend = None
        references, optional_references = [], []
        if packet["assigned_persona"] in FRONTEND_PERSONAS or cfg["profile"] == "frontend_web":
            from .frontend_activation import frontend_selection
            require(cfg["profile"] == "frontend_web", "FRONTEND_PROFILE_REQUIRED")
            references, optional_references, frontend = frontend_selection(self._registry, packet, cfg, required)
            used += frontend["metadata_bytes"]
            document_remaining -= 2
            require(document_remaining > 0, "FRONTEND_DECLARATION_BUDGET_EXCEEDED")
        required += [*cfg.get("required_extra", []), *references]
        optional = [*cfg.get("optional_extra", []), *optional_references]
        plan, contents = self._registry.plan(required, optional, host=cfg["host"],
                stage=cfg["stage"], task=cfg.get("task", "general"), max_bytes=limit,
                context_used_bytes=used, max_files=min(cfg.get("max_files", 8), document_remaining),
                max_reference_files=cfg.get("max_reference_files", MAX_REFERENCE_FILES),
                max_documents=min(document_remaining, 24),
                source_authorities=packet["source_authorities"],
                include_routes=cfg.get("include_routes", True))
        plan["frontend_activation"] = frontend
        require([s["source"]["path"] for s in plan["selected"] if s["kind"] == "skill"] ==
                packet["selected_skills"]["files"],
                "AUTHORIZED_SKILL_SELECTION_MISMATCH")
        if require_consumable:
            require(all(s["host_mode"] == "FIXTURE" for s in plan["selected"] if s["required"]),
                    "REQUIRED_SKILL_CONSUMPTION_UNAVAILABLE")
        binding = {"contract_sha256": contract, "mission_id": packet["mission_id"],
                   "revision": packet["revision"], "run_id": packet["run_id"], "repo_id": packet["repo_id"],
                   "repo_name": packet["repo_name"], "base_sha": packet["base_sha"],
                   "branch": packet["permitted_branch"], "persona": packet["assigned_persona"],
                   "formal_role": packet["formal_role"], "actor_id": cfg["actor_id"], "host_id": cfg["host_id"],
                   "context_id": cfg["context_id"], "attempt_ordinal": cfg["attempt_ordinal"],
                   "grant_sha256": digest(grant) if grant is not None else None,
                   "cognition_sha256": cognition_hash(packet), "brain_checkpoint_sha256": checkpoint}
        prepared = PreparedSkillContext(plan, contents, binding)
        self._prepared[prepared] = prepared.plan_sha256
        return prepared

    def manual_context(self, packet, *, grant):
        """Export verified retrieved text; neither host activation nor receipt."""
        prepared = self.prepare(packet, grant=grant)
        require(prepared._plan["host"] == "chatgpt", "MANUAL_CHATGPT_CONTEXT_REQUIRED")
        return {"plan": prepared.summary(), "documents": [
                    {"id": e["id"], "source": e["source"], "content": prepared._contents[e["id"]].decode("utf-8")}
                    for e in prepared._plan["selected"]],
                "status": "RETRIEVED_NOT_LOADED", "invoked": False,
                "native_loading_verified": False, "promotion_authorized": False}

    def consume(self, prepared, consumer, packet):
        require(type(prepared) is PreparedSkillContext and callable(consumer)
                and self._prepared.get(prepared) == prepared.plan_sha256
                and digest({"plan": prepared._plan, "binding": prepared._binding}) == prepared.plan_sha256
                and prepared._plan["host"] == "fixture"
                and prepared._binding["contract_sha256"] == contract_digest(packet)
                and prepared._binding["grant_sha256"] is not None, "SKILL_CONSUMPTION_CONTEXT_INVALID")
        # This instance issues at most one receipt per exact attempt/plan.
        require(prepared.plan_sha256 not in self._issued, "SKILL_CONSUMPTION_REPLAY")
        self._issued.add(prepared.plan_sha256)
        context = FixtureSkillInput(prepared)
        try:
            result = consumer(deepcopy(packet), context)
        finally:
            reads = context.close()
        require(type(result) is dict, "SKILL_CONSUMER_RESULT_INVALID")
        require(set(prepared._plan["required"]) <= set(reads), "REQUIRED_SKILL_NOT_CONSUMED")
        by_id = {e["id"]: e for e in prepared._plan["selected"]}
        receipt = {"schema_version": 1, "receipt_id": uuid.uuid4().hex,
                   "plan_sha256": prepared.plan_sha256, "binding": deepcopy(prepared._binding),
                   "status": "FIXTURE_CONSUMED", "fixture_only": True, "native_loading_verified": False,
                   "promotion_authorized": False, "loaded": [
                       {"id": name, "source": deepcopy(by_id[name]["source"]), "status": "CONSUMED_FIXTURE"}
                       for name in reads],
                   "retrieved_not_loaded": [e["id"] for e in prepared._plan["selected"] if e["id"] not in reads],
                   "consumed_bytes": sum(by_id[name]["source"]["bytes"] for name in reads),
                   "result_sha256": digest(result)}
        receipt["signature"] = hmac.new(self._key, canonical(receipt).encode("utf-8"), hashlib.sha256).hexdigest()
        validate_contract(receipt, "skill-consumption.schema.json")
        return result, receipt

    def verify_receipt(self, prepared, receipt):
        validate_contract(receipt, "skill-consumption.schema.json")
        require(type(receipt) is dict and type(receipt.get("signature")) is str, "SKILL_RECEIPT_INVALID")
        unsigned = {k: v for k, v in receipt.items() if k != "signature"}
        expected = hmac.new(self._key, canonical(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
        require(hmac.compare_digest(expected, receipt["signature"]), "SKILL_RECEIPT_SIGNATURE_INVALID")
        require(receipt["schema_version"] == 1 and receipt["status"] == "FIXTURE_CONSUMED"
                and receipt["fixture_only"] is True and receipt["native_loading_verified"] is False
                and receipt["promotion_authorized"] is False and receipt["binding"] == prepared._binding
                and receipt["plan_sha256"] == prepared.plan_sha256, "SKILL_RECEIPT_BINDING_MISMATCH")
        by_id = {e["id"]: e for e in prepared._plan["selected"]}
        reads = [e["id"] for e in receipt["loaded"]]
        require(len(reads) == len(set(reads)) and set(reads) <= set(by_id)
                and set(prepared._plan["required"]) <= set(reads), "SKILL_RECEIPT_COVERAGE_INVALID")
        for i, name in enumerate(reads):
            require(set(by_id[name]["dependencies"]) <= set(reads[:i]), "SKILL_RECEIPT_DEPENDENCY_ORDER_INVALID")
        require(receipt["loaded"] == [{"id": n, "source": by_id[n]["source"], "status": "CONSUMED_FIXTURE"}
                                      for n in reads] and receipt["retrieved_not_loaded"] ==
                [n for n in by_id if n not in reads] and receipt["consumed_bytes"] ==
                sum(by_id[n]["source"]["bytes"] for n in reads), "SKILL_RECEIPT_CONTENT_MISMATCH")
        return True


def cognition_hash(packet):
    return packet["cognition"]["context_sha256"]
