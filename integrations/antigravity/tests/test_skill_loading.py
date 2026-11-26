"""W5 focused tests: disposable Git objects and bounded callback consumers only."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from integrations.antigravity.factory.authority import AuthorityError
from integrations.antigravity.factory.dispatcher import FleetDispatcher, resolve_skill_plan, select_skills_for_mission
from integrations.antigravity.factory.dispatch_preflight import ContractJournal
from integrations.antigravity.factory.mission_contract import canonical_json, contract_digest, digest_json
from integrations.antigravity.factory.skill_loading import FixtureSkillRuntime, PreparedSkillContext
from integrations.antigravity.factory.skill_registry import PinnedGitSources, SkillRegistry, SkillError, digest
from integrations.antigravity.tests.test_dispatch_preflight import make_grant, make_observation
from integrations.antigravity.tests.test_mission_contract import make_contract


class SkillLoadingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "forge"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.repo_id = 100
        self.repo_name = "fixture/forge"
        self.sources = PinnedGitSources({self.repo_id: (self.repo_name, self.repo)})
        self.names = ["kirion-core", "kirion-dispatch", "kirion-evidence", "kirion-cognition",
                      "kirion-worker", "kirion-debug", "kirion-architecture", "kirion-runtime",
                      "kirion-frontend", "kirion-design-engineering", "kirion-test-engineering"]
        paths = {}
        for name in self.names:
            p = (f"integrations/antigravity/plugins/kirion-forge/skills/{name}/SKILL.md"
                 if name in {"kirion-design-engineering", "kirion-test-engineering"}
                 else f".agents/skills/{name}/SKILL.md")
            paths[name] = p
            self.write(p, f"---\nname: {name}\ndescription: test\n---\n# {name}\nActual UTF-8 instruction: café.\n")
        self.source_commit = self.commit("source")
        self.git("switch", "-c", "standard-source")
        self.reference = "standards/example/standard.md"
        self.write(self.reference, "# Canonical example standard\nDo not conflate mock and live data.\n")
        self.ref_commit = self.commit("reference-only source")
        self.git("switch", "main")
        self.assertFalse((self.repo / self.reference).exists())
        modes = {"chatgpt": "MANUAL", "codex": "MANUAL", "antigravity": "MANUAL", "fixture": "FIXTURE"}
        self.manifest = {
            "registry_version": 1, "status": "draft-not-adopted", "noAutomaticMerge": True,
            "noAutomaticProjectPolicyAdoption": True, "candidate_count": len(self.names) + 1,
            "registry": [], "stage_optional": {"PRE_DESIGN": ["kirion-architecture"],
                "PRE_IMPLEMENTATION": ["kirion-worker"], "PRE_DELIVERY": ["kirion-evidence"],
                "POST_DEPLOY": ["kirion-runtime"]}, "task_optional": {"general": [], "debug": ["kirion-debug"]}}
        for name, path in paths.items():
            raw = (self.repo / path).read_bytes()
            self.manifest["registry"].append(self.entry(name, "skill", self.source_commit, path, raw,
                modes, ["kirion-core"] if name == "kirion-dispatch" else
                ["kirion-frontend"] if name == "kirion-design-engineering" else []))
        raw = self.git_bytes("show", self.ref_commit + ":" + self.reference)
        self.manifest["registry"].append(self.entry("example-standard", "reference", self.ref_commit,
                                                   self.reference, raw, modes, []))
        self.registry = self.registry_from(self.manifest)
        self.authorities = [{"source_id": "example", "repository_id": self.repo_id,
                             "repository_name": self.repo_name, "commit_sha": self.ref_commit,
                             "scope": ["standards/example"], "authority_kind": "CONSTRAINT"}]

    def git_bytes(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    def git(self, *args):
        return self.git_bytes(*args).decode("utf-8").strip()

    def write(self, path, content):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content.encode("utf-8"))

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def entry(self, name, kind, commit, path, raw, modes, dependencies):
        return {"id": name, "kind": kind, "status": "CANDIDATE", "description": name,
                "source": {"repository_id": self.repo_id, "repository_name": self.repo_name,
                           "commit_sha": commit, "path": path, "blob_sha": self.git("rev-parse", commit + ":" + path),
                           "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
                "hosts": dict(modes), "dependencies": dependencies}

    def registry_from(self, manifest):
        self.write("arsenal/manifest.json", json.dumps(manifest))
        # allow an identical manifest to reuse the existing commit
        if self.git("status", "--porcelain"):
            commit = self.commit("registry")
        else:
            commit = self.git("rev-parse", "HEAD")
        return SkillRegistry(self.sources, repository_id=self.repo_id, repository_name=self.repo_name,
                             registry_commit=commit)

    def plan(self, registry=None, required=None, optional=None, **kwargs):
        options = {"host": "fixture", "stage": "PRE_IMPLEMENTATION", "task": "general",
                   "max_bytes": 8192, "include_routes": False}
        options.update(kwargs)
        return (registry or self.registry).plan(required or ["kirion-core", "kirion-dispatch"],
                                                optional or [], **options)

    def config(self, packet, grant, **kwargs):
        cfg = {"run_id": packet["run_id"], "revision": packet["revision"], "profile": "documentation",
               "host": "fixture", "stage": "PRE_IMPLEMENTATION", "task": "general",
               "max_context_bytes": 8192, "context_id": "fixture-context",
               "actor_id": grant["actor_id"], "host_id": grant["host_id"],
               "attempt_ordinal": grant["attempt_ordinal"], "include_routes": True}
        cfg.update(kwargs)
        return cfg

    def mission(self, **options):
        packet = make_contract()
        plan = resolve_skill_plan("documentation", skill_source_sha=self.registry.identity["commit_sha"],
                sources=self.sources, registry_repository_id=self.repo_id, registry_repository_name=self.repo_name,
                host=options.get("host", "fixture"), max_bytes=8192)
        packet["selected_skills"] = {"skill_source_sha": self.registry.identity["commit_sha"],
                                    "files": [e["source"]["path"] for e in plan["selected"]]}
        grant = make_grant(packet)
        return packet, grant, self.config(packet, grant, **options)

    def runtime(self, packet, config):
        return FixtureSkillRuntime(self.registry, configs={contract_digest(packet): config},
                                   signing_key=b"s" * 32)

    @staticmethod
    def consume_required(packet, inputs):
        # Each returned string is actually read by this fixture consumer.
        loaded = [inputs.read(n) for n in inputs.available_ids() if n != "kirion-worker"]
        return {"observed_markdown": len(loaded), "bytes": sum(len(s.encode("utf-8")) for s in loaded)}

    def test_inventory_selection_retrieval_are_distinct(self):
        self.assertTrue(all(i["status"] == "AVAILABLE_METADATA" and not i["adopted"]
                            for i in self.registry.inventory()))
        plan, contents = self.plan(required=["kirion-dispatch", "kirion-core", "kirion-dispatch"])
        self.assertEqual(list(contents), ["kirion-core", "kirion-dispatch"])
        self.assertEqual(plan["status"], "RETRIEVED_NOT_LOADED")
        self.assertTrue(all(x["selection_status"] == "SELECTED" and x["loading_status"] == "NOT_LOADED"
                            for x in plan["selected"]))

    def test_git_pin_not_dirty_worktree_or_fallback(self):
        p = ".agents/skills/kirion-core/SKILL.md"
        prior = self.git_bytes("show", self.source_commit + ":" + p)
        self.write(p, "dirty replacement")
        raw, identity = self.registry.retrieve("kirion-core")
        self.assertEqual(raw, prior)
        self.assertEqual(identity["sha256"], hashlib.sha256(prior).hexdigest())
        (self.repo / p).unlink()
        self.assertEqual(self.registry.retrieve("kirion-core")[0], prior)
        with self.assertRaises(AuthorityError):
            SkillRegistry(self.sources, repository_id=self.repo_id, repository_name=self.repo_name,
                          registry_commit="f" * 40)
        with self.assertRaises(AuthorityError):
            self.sources.read(self.repo_id, self.repo_name, self.source_commit, self.reference)
        with self.assertRaises(AuthorityError):
            self.sources.read(self.repo_id, "other/repo", self.source_commit, p)

    def test_source_store_cannot_fall_back_to_parent_repository(self):
        sub = self.repo / ".agents"
        with self.assertRaisesRegex(SkillError, "SOURCE_ROOT_MISMATCH"):
            PinnedGitSources({self.repo_id: (self.repo_name, sub)})

    def test_duplicate_content_pin_denied(self):
        m = copy.deepcopy(self.manifest)
        m["registry"][1]["source"]["sha256"] = m["registry"][0]["source"]["sha256"]
        with self.assertRaisesRegex(SkillError, "REGISTRY_DUPLICATE_CONTENT"):
            self.registry_from(m)

    def test_wrong_blob_digest_and_size(self):
        for key, value in (("blob_sha", "f" * 40), ("sha256", "f" * 64), ("bytes", 1)):
            m = copy.deepcopy(self.manifest)
            m["registry"][0]["source"][key] = value
            registry = self.registry_from(m)
            with self.assertRaises(AuthorityError):
                self.plan(registry)
        with self.assertRaises(AuthorityError):
            self.sources.read(self.repo_id, self.repo_name, self.source_commit, "../outside.md")

    def test_registry_rejects_collision_cycle_and_unknown_dependency(self):
        mutations = [
            lambda m: m["registry"][1].update(id=m["registry"][0]["id"]),
            lambda m: m["registry"][0].update(dependencies=["kirion-dispatch"]),
            lambda m: m["registry"][0].update(dependencies=["missing-skill"]),
            lambda m: m["registry"][0]["source"].update(path=".agents/skills/../core/SKILL.md"),
        ]
        for mutate in mutations:
            m = copy.deepcopy(self.manifest)
            mutate(m)
            with self.assertRaises(AuthorityError):
                self.registry_from(m)

    @unittest.skipIf(os.name == "nt", "Windows symlink fixture may require operator privilege")
    def test_committed_symlink_is_not_skill_bytes(self):
        path = ".agents/skills/kirion-core/SKILL.md"
        p = self.repo / path
        p.unlink()
        p.symlink_to("/etc/passwd")
        sha = self.commit("symlink")
        with self.assertRaises(AuthorityError):
            self.sources.read(self.repo_id, self.repo_name, sha, path)

    def test_required_budget_cannot_be_truncated(self):
        p, _ = self.plan()
        needed = p["skill_bytes"]
        with self.assertRaisesRegex(SkillError, "BUDGET"):
            self.plan(max_bytes=needed - 1)
        with self.assertRaisesRegex(SkillError, "BUDGET"):
            self.plan(max_files=1)
        p, contents = self.plan(optional=["kirion-debug"], max_bytes=needed + 17, context_used_bytes=17)
        self.assertEqual(p["total_context_bytes"], needed + 17)
        self.assertNotIn("kirion-debug", contents)
        self.assertEqual(p["omitted"][0]["reason"], "SKILL_CONTEXT_BUDGET_EXCEEDED")

    def test_stage_task_progressive_order_and_dedup(self):
        p, c = self.plan(include_routes=True, stage="PRE_DESIGN", task="debug")
        self.assertEqual(list(c), ["kirion-core", "kirion-dispatch", "kirion-architecture", "kirion-debug"])
        p2, c2 = self.plan(include_routes=True, stage="POST_DEPLOY", task="general")
        self.assertIn("kirion-runtime", c2)
        self.assertNotIn("kirion-architecture", c2)
        self.assertNotEqual(p, p2)

    def test_optional_advisory_and_unavailable_required(self):
        m = copy.deepcopy(self.manifest)
        next(x for x in m["registry"] if x["id"] == "kirion-debug")["hosts"]["fixture"] = "ADVISORY_ONLY"
        registry = self.registry_from(m)
        plan, contents = self.plan(registry, optional=["kirion-debug"])
        self.assertEqual(plan["omitted"][0]["reason"], "SKILL_HOST_ADVISORY_ONLY")
        self.assertNotIn("kirion-debug", contents)
        with self.assertRaisesRegex(SkillError, "ADVISORY"):
            self.plan(registry, required=["kirion-debug"])

    def test_cross_branch_reference_requires_exact_source_authority(self):
        with self.assertRaisesRegex(SkillError, "NOT_AUTHORIZED"):
            self.plan(required=["example-standard"])
        wrong = copy.deepcopy(self.authorities)
        wrong[0]["commit_sha"] = self.source_commit
        with self.assertRaisesRegex(SkillError, "NOT_AUTHORIZED"):
            self.plan(required=["example-standard"], source_authorities=wrong)
        plan, contents = self.plan(required=["example-standard"], source_authorities=self.authorities)
        self.assertIn(b"Canonical example standard", contents["example-standard"])
        self.assertFalse((self.repo / self.reference).exists())
        self.assertEqual(plan["selected"][0]["source"]["commit_sha"], self.ref_commit)
        # Trusted registry points at a missing commit: no working-tree fallback.
        m = copy.deepcopy(self.manifest)
        m["registry"][-1]["source"]["commit_sha"] = "f" * 40
        registry = self.registry_from(m)
        bad = copy.deepcopy(self.authorities)
        bad[0]["commit_sha"] = "f" * 40
        with self.assertRaises(AuthorityError):
            self.plan(registry, required=["example-standard"], source_authorities=bad)

    def test_legacy_projection_is_exact_pinned_selection_not_loading(self):
        kw = {"sources": self.sources, "registry_repository_id": self.repo_id,
              "registry_repository_name": self.repo_name}
        selected = select_skills_for_mission("documentation", skill_source_sha=self.registry.identity["commit_sha"], **kw)
        self.assertEqual(set(selected), {"skill_source_sha", "files"})
        self.assertEqual(len(selected["files"]), 4)
        with self.assertRaises(AuthorityError):
            select_skills_for_mission("documentation", skill_source_sha=self.source_commit, **kw)

    def test_actual_fixture_reads_and_receipt_integrity(self):
        packet, grant, cfg = self.mission()
        runtime = self.runtime(packet, cfg)
        prepared = runtime.prepare(packet, grant=grant, require_consumable=True)
        result, receipt = runtime.consume(prepared, self.consume_required, packet)
        self.assertTrue(runtime.verify_receipt(prepared, receipt))
        self.assertEqual(receipt["status"], "FIXTURE_CONSUMED")
        self.assertEqual(receipt["retrieved_not_loaded"], ["kirion-worker"])
        self.assertEqual(receipt["consumed_bytes"], result["bytes"])
        self.assertFalse(receipt["native_loading_verified"])
        self.assertFalse(receipt["promotion_authorized"])
        tampered = copy.deepcopy(receipt)
        tampered["consumed_bytes"] += 1
        with self.assertRaisesRegex(SkillError, "SIGNATURE"):
            runtime.verify_receipt(prepared, tampered)
        with self.assertRaisesRegex(SkillError, "REPLAY"):
            runtime.consume(prepared, self.consume_required, packet)

    def test_forged_context_and_missing_required_read_denied(self):
        packet, grant, cfg = self.mission()
        runtime = self.runtime(packet, cfg)
        prepared = runtime.prepare(packet, grant=grant, require_consumable=True)
        fake = PreparedSkillContext(prepared._plan, prepared._contents, prepared._binding)
        with self.assertRaisesRegex(SkillError, "CONTEXT_INVALID"):
            runtime.consume(fake, self.consume_required, packet)
        with self.assertRaisesRegex(SkillError, "NOT_CONSUMED"):
            runtime.consume(prepared, lambda p, c: {"loaded": True}, packet)
        other = self.runtime(packet, cfg)
        prepared = other.prepare(packet, grant=grant, require_consumable=True)
        with self.assertRaisesRegex(SkillError, "DEPENDENCY"):
            other.consume(prepared, lambda p, c: {"text": c.read("kirion-dispatch")}, packet)

    def test_native_manual_retrieval_is_not_actual_loading(self):
        packet, grant, cfg = self.mission(host="chatgpt")
        runtime = self.runtime(packet, cfg)
        self.assertEqual(runtime.prepare(packet).summary()["status"], "RETRIEVED_NOT_LOADED")
        with self.assertRaisesRegex(SkillError, "NATIVE_SKILL_CONSUMPTION_UNAVAILABLE"):
            runtime.prepare(packet, grant=grant, require_consumable=True)

    def test_wrong_mission_run_grant_and_selection(self):
        packet, grant, cfg = self.mission()
        runtime = self.runtime(packet, cfg)
        bad = copy.deepcopy(grant)
        bad["actor_id"] = "other"
        with self.assertRaisesRegex(SkillError, "GRANT_BINDING"):
            runtime.prepare(packet, grant=bad)
        for key, value in (("run_id", "other-run"), ("repo_name", "fixture/other")):
            bad_packet = copy.deepcopy(packet)
            bad_packet[key] = value
            with self.assertRaises(AuthorityError):
                runtime.prepare(bad_packet)
        bad_packet = copy.deepcopy(packet)
        bad_packet["selected_skills"]["files"].reverse()
        bad_grant = make_grant(bad_packet)
        with self.assertRaisesRegex(SkillError, "SELECTION_MISMATCH"):
            self.runtime(bad_packet, cfg).prepare(bad_packet, grant=bad_grant)

    def test_brain_context_consumes_actual_bytes_and_rejects_tamper(self):
        packet, _, cfg = self.mission()
        text = "Cognition café"
        doc = {"path": "brain/context.md", "sha256": hashlib.sha256(text.encode()).hexdigest(),
               "bytes": len(text.encode()), "depth": 0, "source": "REQUIRED_SEED"}
        manifest = {"status": "RESOLVED", "missing_required": [], "required_not_loaded": [],
                    "documents": [doc], "document_count": 1, "total_bytes": doc["bytes"],
                    "document_budget": 8, "byte_budget": 8192}
        checkpoint = {"stage": "PRE_IMPLEMENTATION", "effective_stage": "PRE_IMPLEMENTATION",
                      "context_sha256": digest(manifest), "context_manifest": manifest}
        checkpoint["checkpoint_sha256"] = digest(checkpoint)
        packet["cognition"] = {"mode": "INHERITED", "brain_run_id": "brain-fixture",
                "context_sha256": digest(manifest), "manifest_ref": "fixture-context",
                "target_binding": digest_json({k: packet[k] for k in ("repo_id","repo_name","base_sha","permitted_branch")}),
                "reason": None}
        packet["cognition_hash"] = digest(manifest)
        grant = make_grant(packet)
        cfg.update(brain_run_id="brain-fixture", brain_stage_context={"checkpoint": checkpoint,
                                                                    "documents": [{**doc, "content": text}]})
        runtime = self.runtime(packet, cfg)
        summary = runtime.prepare(packet, grant=grant).summary()
        self.assertEqual(summary["prior_context_bytes"], doc["bytes"])
        self.assertEqual(summary["max_files"], 7)
        cfg["brain_stage_context"]["documents"][0]["content"] = "tampered"
        with self.assertRaisesRegex(SkillError, "BRAIN_DOCUMENT_CONTENT"):
            self.runtime(packet, cfg).prepare(packet, grant=grant)

    def test_existing_journal_dispatch_and_readback(self):
        packet, grant, cfg = self.mission()
        runtime = self.runtime(packet, cfg)
        journal = ContractJournal(self.root / "journal.sqlite")
        dispatcher = FleetDispatcher()
        raw = canonical_json(packet)
        args = {"journal": journal, "runtime": runtime, "grants": {contract_digest(packet): grant},
                "trusted_verifiers": {packet["verifier"]}, "observe": lambda p: make_observation(p, grant),
                "consume": self.consume_required}
        result = dispatcher.dispatch_skill_fixture(raw, **args)
        self.assertEqual(result["status"], "COMPLETED", result)
        self.assertEqual(result["skill_verification"]["status"], "FIXTURE_CONSUMPTION_VERIFIED", result)
        reservation = result["reservation_id"]
        reopened = ContractJournal(journal.db_path)
        self.assertEqual(dispatcher.inspect_skill_fixture(raw, reservation, journal=reopened,
            runtime=runtime, grant=grant)["status"], "FIXTURE_CONSUMPTION_VERIFIED")
        repeated = dispatcher.dispatch_skill_fixture(raw, **args)
        self.assertTrue(repeated["cached"])
        self.assertEqual(repeated["skill_verification"]["status"], "NOT_REVERIFIED_CACHED_ATTEMPT")

    def test_fixture_dispatch_blocks_unknown_required_native_load(self):
        packet, grant, cfg = self.mission(host="codex")
        journal = ContractJournal(self.root / "journal.sqlite")
        calls = []
        result = FleetDispatcher().dispatch_skill_fixture(canonical_json(packet), journal=journal,
                runtime=self.runtime(packet, cfg), grants={contract_digest(packet): grant},
                trusted_verifiers={packet["verifier"]}, observe=lambda p: make_observation(p, grant),
                consume=lambda p, c: calls.append(p))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
