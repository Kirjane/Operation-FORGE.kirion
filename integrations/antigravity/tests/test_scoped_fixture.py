"""Real disposable Git effects through the W1 dispatcher, not live authorization."""
import json
import tempfile
import unittest
from pathlib import Path

from integrations.antigravity.factory.dispatch_preflight import ContractJournal
from integrations.antigravity.factory.dispatcher import FleetDispatcher
from integrations.antigravity.factory.mission_contract import contract_digest
from integrations.antigravity.factory.scoped_fixture import ScopedGitFixtureAdapter
from integrations.antigravity.tests.test_dispatch_preflight import make_grant
from integrations.antigravity.tests.test_mission_contract import make_contract


class ScopedFixtureTests(unittest.TestCase):
    def setUp(self):
        self.adapter = ScopedGitFixtureAdapter(grants={}, trusted_verifiers=set())
        self.addCleanup(self.adapter.close)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.journal = ContractJournal(Path(temp.name) / "contract.sqlite")
        self.packet = make_contract()
        self.packet["base_sha"] = self.adapter.base_sha
        self.packet["source_authorities"][0]["commit_sha"] = self.adapter.base_sha
        self.packet["oracles"][0]["blob_sha"] = self.adapter.oracle_blob_sha
        self.dispatcher = FleetDispatcher()

    def authorize(self):
        grant = make_grant(self.packet)
        self.adapter.configure_fixture_grants({contract_digest(self.packet): grant}, {self.packet["verifier"]})

    def dispatch(self):
        return self.dispatcher.dispatch_worker(json.dumps(self.packet), journal=self.journal,
                                               fixture_adapter=self.adapter)

    def test_actual_pinned_read_and_duplicate(self):
        self.authorize()
        result = self.dispatch()
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["result"]["effect"], "READ_ONLY")
        self.assertEqual(result["result"]["observed"]["oracles"]["source_observation"]["blob_sha"],
                         self.adapter.oracle_blob_sha)
        self.assertTrue(self.dispatch()["cached"])
        self.assertTrue(self.journal.verify_hash_chain())

    def test_wrong_oracle_cannot_reserve(self):
        self.packet["oracles"][0]["blob_sha"] = "e" * 40
        self.authorize()
        self.assertEqual(self.dispatch()["status"], "BLOCKED")

    def test_dirty_target_cannot_reserve(self):
        self.authorize()
        (self.adapter.repo / "unexpected").write_text("drift")
        self.assertEqual(self.dispatch()["status"], "BLOCKED")

    def test_no_grant_no_effect(self):
        self.assertEqual(self.dispatch()["status"], "BLOCKED")
        self.assertEqual((self.adapter.repo / self.adapter.owned_file).read_bytes(), b"before\n")

    def make_writer(self):
        self.packet.update(assigned_persona="Antigravity-Jane", formal_role="Code Writer",
                           owned_paths=[self.adapter.owned_file], allowed_operations=["READ", "WRITE_OWNED"])
        self.packet["authority"]["grant_scope"] = self.packet["allowed_operations"]
        self.packet["required_capabilities"].append({"capability_id": "scoped_worktree_write",
            "operation": "WRITE_OWNED", "scope": [self.adapter.owned_file],
            "environment": "fixture", "independence_required": False})

    def test_owned_write_has_observed_diff_and_duplicate_is_not_replayed(self):
        self.make_writer()
        self.authorize()
        result = self.dispatch()
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["result"]["changed_paths"], [self.adapter.owned_file])
        self.assertEqual(result["result"]["acceptance"], "NOT_EVALUATED")
        self.assertNotEqual(result["result"]["before_sha256"], result["result"]["after_sha256"])
        self.assertEqual((self.adapter.repo / self.adapter.owned_file).read_bytes(), b"after\n")
        self.assertTrue(self.dispatch()["cached"])
        self.assertTrue(self.journal.verify_hash_chain())

    def test_conflicting_lease_denies_before_write(self):
        self.make_writer()
        self.authorize()
        self.adapter.leases.acquire_leases(self.packet, "other-worker")
        result = self.dispatch()
        self.assertEqual(result["status"], "NO_EFFECT")
        self.assertEqual((self.adapter.repo / self.adapter.owned_file).read_bytes(), b"before\n")
        self.assertTrue(self.journal.verify_hash_chain())

    def test_excluded_owned_file_denies_before_write(self):
        self.make_writer()
        self.packet["excluded_paths"] = [self.adapter.owned_file]
        self.authorize()
        self.assertEqual(self.dispatch()["status"], "BLOCKED")
        self.assertEqual((self.adapter.repo / self.adapter.owned_file).read_bytes(), b"before\n")

    def test_uncertain_write_stays_blocked_and_cannot_use_callback_reconciliation(self):
        from unittest.mock import patch
        from integrations.antigravity.factory.authority import AuthorityError
        from integrations.antigravity.factory.dispatch_preflight import FixtureDispatchAdapter
        from integrations.antigravity.factory.scheduler import SchedulerError
        from integrations.antigravity.tests.test_dispatch_preflight import make_observation
        import sqlite3

        self.make_writer()
        self.authorize()
        real_git = self.adapter._git

        def fail_after_write(*args):
            if args[0] == "diff":
                raise AuthorityError("Injected post-effect observation failure")
            return real_git(*args)

        with patch.object(self.adapter, "_git", side_effect=fail_after_write):
            with self.assertRaises(AuthorityError):
                self.dispatch()
        self.assertEqual((self.adapter.repo / self.adapter.owned_file).read_bytes(), b"after\n")
        with sqlite3.connect(self.journal.db_path) as conn:
            reservation = conn.execute("SELECT reservation_id FROM contract_attempts").fetchone()[0]
        raw = json.dumps(self.packet)
        receipt = self.journal.inspect_attempt(raw, reservation)
        self.assertEqual(receipt["status"], "UNKNOWN")
        self.assertFalse(receipt["replay_permitted"])
        self.assertEqual(self.dispatch()["status"], "UNKNOWN")
        grant = make_grant(self.packet)
        fallback = FixtureDispatchAdapter(grants={contract_digest(self.packet): grant},
            trusted_verifiers={self.packet["verifier"]}, observe=lambda p: make_observation(p, grant),
            handler=lambda p: {}, reconciliations={reservation: {
                "contract_sha256": contract_digest(self.packet), "reservation_id": reservation,
                "quiescent": True, "effect": "NO_EFFECT", "evidence_ref": "synthetic-only"}})
        with self.assertRaises(SchedulerError):
            self.journal.reconcile_unknown(raw, reservation, fallback)
        self.assertEqual(self.journal.inspect_attempt(raw, reservation)["status"], "UNKNOWN")
