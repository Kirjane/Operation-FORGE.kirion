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
