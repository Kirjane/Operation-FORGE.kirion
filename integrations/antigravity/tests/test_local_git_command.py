"""Real local Git ref CAS and canonical reservation regressions; never live acceptance."""
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from integrations.antigravity.factory.authority import AuthorityError
from integrations.antigravity.factory.dispatch_preflight import ContractJournal
from integrations.antigravity.factory.local_git_command import LocalGitCommandAdapter, grant_mac
from integrations.antigravity.factory.mission_contract import contract_digest
from integrations.antigravity.factory.scheduler import SchedulerError
from integrations.antigravity.tests.test_dispatch_preflight import make_grant
from integrations.antigravity.tests.test_mission_contract import make_contract


class LocalGitCommandTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "bare"
        work = self.root / "work"
        self.repo.mkdir()
        work.mkdir()
        self.branch = "feat/read-contract"
        self.git(self.repo, "init", "--bare", "-q")
        self.git(work, "init", "-q", "-b", self.branch)
        self.git(work, "config", "user.name", "Fixture")
        self.git(work, "config", "user.email", "fixture@example.invalid")
        (work / "docs").mkdir()
        for name in ("contract.md", "skill.md", "owned.txt"):
            (work / "docs" / name).write_text("before\n")
        self.git(work, "add", ".")
        self.git(work, "commit", "-qm", "base")
        self.base = self.git(work, "rev-parse", "HEAD")
        self.git(work, "push", str(self.repo), "HEAD:refs/heads/" + self.branch)
        (work / "docs/owned.txt").write_text("after\n")
        self.git(work, "add", ".")
        self.git(work, "commit", "-qm", "candidate")
        self.target = self.git(work, "rev-parse", "HEAD")
        self.tree = self.git(work, "rev-parse", "HEAD^{tree}")
        self.git(work, "push", str(self.repo), "HEAD:refs/heads/fixture-candidate")
        self.key = b"k" * 32
        self.grant_file = self.root / "grant.json"
        self.grant_file.touch()
        self.packet = make_contract()
        self.packet.update(base_sha=self.base, assigned_persona="Antigravity-Jane",
                           formal_role="Code Writer", work_mode="IN_FLIGHT",
                           owned_paths=["docs/owned.txt"], allowed_operations=["READ", "WRITE_OWNED"])
        self.packet["source_authorities"][0]["commit_sha"] = self.base
        self.packet["oracles"][0]["blob_sha"] = self.git(work, "rev-parse", self.base + ":docs/contract.md")
        self.packet["selected_skills"]["skill_source_sha"] = self.base
        self.packet["authority"]["grant_scope"] = self.packet["allowed_operations"]
        self.packet["required_capabilities"].append({"capability_id": "scoped_worktree_write",
            "operation": "WRITE_OWNED", "scope": ["docs/owned.txt"], "environment": "fixture",
            "independence_required": False})
        self.adapter = LocalGitCommandAdapter(repository=self.repo, grant_file=self.grant_file,
            issuer_key=self.key, trusted_verifiers={self.packet["verifier"]})
        self.journal = ContractJournal(self.root / "journal.sqlite")
        self.authorize(self.packet)

    def git(self, cwd, *args):
        return subprocess.check_output(["git", *args], cwd=cwd, stderr=subprocess.PIPE).decode().strip()

    def authorize(self, packet, **changes):
        grant = make_grant(packet)
        grant["local_command"] = {"version": 1, "resource": self.adapter.identity,
            "repo_id": packet["repo_id"], "repo_name": packet["repo_name"], "branch": self.branch,
            "base": self.base, "run_id": packet["run_id"], "contract_sha256": contract_digest(packet),
            "stage": "AUTHORIZED", "alias": "/forge.write", "candidate": self.target,
            "tree": self.tree, "paths": ["docs/owned.txt"]}
        grant["local_command"].update(changes)
        self.grant_file.write_text(json.dumps({"grant": grant, "mac": grant_mac(self.key, grant)}))
        return grant

    def raw(self):
        return json.dumps(self.packet)

    def head(self):
        return self.git(self.repo, "rev-parse", "refs/heads/" + self.branch)

    def test_actual_command_cas_and_canonical_receipt(self):
        result = self.journal.dispatch_fixture(self.raw(), self.adapter)
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(self.head(), self.target)
        receipt = result["result"]["receipt"]
        self.assertEqual(receipt["reservation_id"], result["reservation_id"])
        self.assertEqual(receipt["acceptance"], "NOT_EVALUATED")
        self.assertTrue(self.journal.dispatch_fixture(self.raw(), self.adapter)["cached"])
        # A different ledger cannot replay the already-applied resource/base.
        other = ContractJournal(self.root / "other.sqlite")
        self.assertEqual(other.dispatch_fixture(self.raw(), self.adapter)["status"], "BLOCKED")

    def test_wrong_mac_or_command_denied_before_cas(self):
        grant = self.authorize(self.packet)
        self.grant_file.write_text(json.dumps({"grant": grant, "mac": "0" * 64}))
        self.assertEqual(self.journal.dispatch_fixture(self.raw(), self.adapter)["status"], "BLOCKED")
        self.authorize(self.packet, alias="/forge.accept")
        self.assertEqual(self.journal.dispatch_fixture(self.raw(), self.adapter)["status"], "BLOCKED")
        self.assertEqual(self.head(), self.base)

    def test_direct_call_without_durable_reservation_denied(self):
        with self.assertRaises(SchedulerError):
            self.adapter.invoke(self.packet, before_invoke=lambda: None,
                                reservation_id="forged", journal=self.journal)
        self.assertEqual(self.head(), self.base)

    def test_uncertain_receipt_recovers_without_second_effect(self):
        original = self.adapter.invoke
        def lose(*args, **kwargs):
            original(*args, **kwargs)
            raise TimeoutError("lost local response")
        with patch.object(self.adapter, "invoke", side_effect=lose):
            with self.assertRaises(TimeoutError):
                self.journal.dispatch_fixture(self.raw(), self.adapter)
        rid = next(e["payload"]["reservation_id"] for e in self.journal.list_events()
                   if e["event_type"] == "DISPATCH_RESERVED")
        self.assertEqual(self.head(), self.target)
        result = self.journal.reconcile_local_git(self.raw(), rid, self.adapter)
        self.assertEqual(result["status"], "RECONCILED")
        self.assertFalse(result["replay_permitted"])
        self.assertEqual(self.journal.inspect_attempt(self.raw(), rid)["status"], "RECONCILED")

    def test_head_only_is_not_recovery(self):
        original = self.adapter.invoke
        def lose(*args, **kwargs):
            original(*args, **kwargs)
            raise TimeoutError("lost local response")
        with patch.object(self.adapter, "invoke", side_effect=lose):
            with self.assertRaises(TimeoutError):
                self.journal.dispatch_fixture(self.raw(), self.adapter)
        rid = next(e["payload"]["reservation_id"] for e in self.journal.list_events()
                   if e["event_type"] == "DISPATCH_RESERVED")
        receipt_ref = self.adapter._receipt_ref(json.loads(self.grant_file.read_bytes())["grant"]["local_command"])
        self.git(self.repo, "update-ref", "-d", receipt_ref)
        with self.assertRaises((AuthorityError, SchedulerError, subprocess.CalledProcessError)):
            self.journal.reconcile_local_git(self.raw(), rid, self.adapter)
        self.assertEqual(self.journal.inspect_attempt(self.raw(), rid)["status"], "UNKNOWN")

    def test_reserved_resource_blocks_other_mission_in_same_journal(self):
        self.assertEqual(self.journal.reserve_dispatch(self.raw(), self.adapter)["status"], "RESERVED")
        self.packet["mission_id"] = "FIXTURE-OTHER"
        self.packet["run_id"] = "run-other"
        self.authorize(self.packet)
        result = self.journal.reserve_dispatch(self.raw(), self.adapter)
        self.assertEqual(result["reason"], "RESOURCE_EFFECT_UNRECONCILED")
        self.assertEqual(self.head(), self.base)

    def test_grant_change_after_reservation_denied(self):
        original=self.adapter.invoke
        def revoked(*args,**kwargs):
            grant=json.loads(self.grant_file.read_bytes())["grant"]
            grant["revoked"]=True
            self.grant_file.write_text(json.dumps({"grant":grant,"mac":grant_mac(self.key,grant)}))
            return original(*args,**kwargs)
        with patch.object(self.adapter,"invoke",side_effect=revoked):
            result=self.journal.dispatch_fixture(self.raw(),self.adapter)
        self.assertEqual(result["status"],"NO_EFFECT")
        self.assertIn("GRANT_CHANGED",result["reason"])
        self.assertEqual(self.head(), self.base)

    def test_pending_resource_claim_blocks_independent_journal(self):
        original=self.adapter._git
        def interrupted(*args,**kwargs):
            if args[:2]==("update-ref","--stdin") and b"\nupdate refs/heads/" in kwargs.get("data",b""):
                raise TimeoutError("lost effect before CAS")
            return original(*args,**kwargs)
        with patch.object(self.adapter,"_git",side_effect=interrupted):
            with self.assertRaises(TimeoutError):
                self.journal.dispatch_fixture(self.raw(),self.adapter)
        self.assertEqual(self.head(),self.base)
        other=ContractJournal(self.root/"other.sqlite")
        self.assertEqual(other.dispatch_fixture(self.raw(),self.adapter)["status"],"BLOCKED")
        self.assertEqual(self.head(),self.base)

    def test_deleted_reservation_cannot_clear_fence(self):
        claim = self.journal.reserve_dispatch(self.raw(), self.adapter)
        self.assertEqual(claim["status"], "RESERVED")
        with sqlite3.connect(self.journal.db_path) as db:
            db.execute("DELETE FROM contract_attempts")
        with self.assertRaisesRegex(SchedulerError, "materialization"):
            self.journal.dispatch_fixture(self.raw(), self.adapter)
        self.assertEqual(self.head(), self.base)


if __name__ == "__main__":
    unittest.main()
