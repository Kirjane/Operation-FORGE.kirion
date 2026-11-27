"""Regression for the local derived board; fixture-only, never an acceptance."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from integrations.antigravity.factory.dispatch_preflight import ContractJournal, FixtureDispatchAdapter
from integrations.antigravity.factory.mission_contract import contract_digest
from integrations.antigravity.factory.operational_state import read_contract_board
from integrations.antigravity.tests.test_dispatch_preflight import make_grant, make_observation
from integrations.antigravity.tests.test_mission_contract import make_contract


class OperationalStateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "contract.sqlite"
        self.journal = ContractJournal(self.path)
        self.packet = make_contract()

    def adapter(self, handler):
        grant = make_grant(self.packet)
        return FixtureDispatchAdapter(grants={contract_digest(self.packet): grant},
            trusted_verifiers={self.packet["verifier"]},
            observe=lambda packet: make_observation(packet, grant), handler=handler)

    def test_projection_is_read_only_and_does_not_accept(self):
        self.assertEqual(read_contract_board(self.path)["missions"], [])
        result = self.journal.dispatch_fixture(json.dumps(self.packet), self.adapter(lambda p: {"ok": True}))
        self.assertEqual(result["status"], "COMPLETED")
        events = self.journal.list_events()
        board = read_contract_board(self.path)
        self.assertEqual(board["status"], "PROJECTED")
        mission = board["missions"][0]
        self.assertEqual(mission["attempts"][0]["status"], "COMPLETED")
        self.assertEqual(mission["acceptance"], "NOT_ESTABLISHED")
        self.assertFalse(mission["replay_permitted"])
        self.assertEqual(events, self.journal.list_events())
        self.assertFalse(board["promotion_authorized"])

    def test_unknown_effect_requires_reconciliation(self):
        def fail(packet):
            raise RuntimeError("uncertain fixture effect")
        with self.assertRaises(RuntimeError):
            self.journal.dispatch_fixture(json.dumps(self.packet), self.adapter(fail))
        mission = read_contract_board(self.path)["missions"][0]
        self.assertTrue(mission["reconciliation_required"])
        self.assertFalse(mission["replay_permitted"])

    def test_materialized_head_or_attempt_tampering_blocks(self):
        self.journal.dispatch_fixture(json.dumps(self.packet), self.adapter(lambda p: {"ok": True}))
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE contract_heads SET state='ACCEPTED'")
        self.assertEqual(read_contract_board(self.path)["reason"], "HEAD_PROJECTION_MISMATCH")
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE contract_heads SET state='ACTIVE'")
            db.execute("UPDATE contract_attempts SET status='UNKNOWN'")
        self.assertEqual(read_contract_board(self.path)["reason"], "ATTEMPT_PROJECTION_MISMATCH")

    def test_absent_database_is_not_created(self):
        missing = self.path.with_name("missing.sqlite")
        self.assertEqual(read_contract_board(missing)["status"], "BLOCKED")
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
