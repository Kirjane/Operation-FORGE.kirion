"""Focused non-live boundary regressions."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from integrations.antigravity.factory.authority import AuthorityError
from integrations.antigravity.factory.dispatch_preflight import ContractJournal
from integrations.antigravity.factory.fenced_file import FenceDenied, fixed_file, identity, supported
from integrations.antigravity.factory.native_boundary import FixtureNativeBoundary, WORKFLOWS, native_workflow_entry
from integrations.antigravity.factory.mission_contract import contract_digest
from integrations.antigravity.factory.scoped_fixture import ScopedGitFixtureAdapter
from integrations.antigravity.tests.test_dispatch_preflight import make_grant
from integrations.antigravity.tests.test_mission_contract import make_contract


class NativeEntryTests(unittest.TestCase):
    def test_all_hosts_and_workflows_deny_claimed_trust(self):
        for host in ("antigravity", "chatgpt", "codex", "forged"):
            for workflow in WORKFLOWS:
                result = native_workflow_entry(workflow, host, {
                    "actor_id": 339503629, "authorized": True,
                    "capabilities": {"trusted_native_execution": "AVAILABLE"},
                    "fixture_adapter": object(),
                })
                self.assertEqual(result["status"], "BLOCKED")
                self.assertFalse(result["invoked"])
                self.assertIsNone(result["capabilities"]["actor_id"])
                self.assertFalse(result["promotion_authorized"])

    def test_non_scoped_composition_denied(self):
        with self.assertRaises(AuthorityError):
            FixtureNativeBoundary(object(), object())


class ScopedNativeCompositionTests(unittest.TestCase):
    def setUp(self):
        self.adapter = ScopedGitFixtureAdapter(grants={}, trusted_verifiers=set())
        self.addCleanup(self.adapter.close)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.journal = ContractJournal(Path(temp.name) / "contract.sqlite")
        self.boundary = FixtureNativeBoundary(self.journal, self.adapter)
        packet = make_contract()
        packet["base_sha"] = self.adapter.base_sha
        packet["source_authorities"][0]["commit_sha"] = self.adapter.base_sha
        packet["oracles"][0]["blob_sha"] = self.adapter.oracle_blob_sha
        self.adapter.configure_fixture_grants(
            {contract_digest(packet): make_grant(packet)}, {packet["verifier"]})
        self.raw = json.dumps(packet)

    def test_actual_read_recovery_and_delivery_denial(self):
        result = self.boundary.execute("greenfield_discovery", self.raw)
        self.assertEqual(result["status"], "COMPLETED")
        oracle = result["result"]["observed"]["oracles"]["source_observation"]["byte_observation"]
        self.assertEqual(oracle["blob_sha"], self.adapter.oracle_blob_sha)
        self.assertEqual(oracle["execution"], "GIT_CAT_FILE_FIXED_SOURCE")
        self.assertFalse(oracle["independent"])
        self.assertEqual(oracle["acceptance"], "NOT_EVALUATED")
        reservation = result["reservation_id"]
        recovery = self.boundary.inspect_recovery(self.raw, reservation)
        self.assertFalse(recovery["replay_permitted"])
        self.assertEqual(recovery["observation"]["quiescence"], "NOT_ESTABLISHED")
        delivery = self.boundary.inspect_delivery(self.raw, reservation)
        self.assertFalse(delivery["remote_invoked"])
        self.assertFalse(delivery["promotion_authorized"])
        self.assertTrue(self.boundary.execute("greenfield_discovery", self.raw)["cached"])

    def test_integration_cannot_enter_read_fixture(self):
        result = self.boundary.execute("candidate_integration", self.raw)
        self.assertEqual(result["status"], "BLOCKED")


@unittest.skipUnless(supported(), "descriptor-confinement platform unavailable")
class DescriptorFenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.docs = self.root / "docs"
        self.docs.mkdir()
        self.target = self.docs / "owned.txt"
        self.target.write_bytes(b"before")
        self.ids = [identity(path.stat()) for path in (self.root, self.docs, self.target)]

    def fence(self):
        return fixed_file(self.root, *self.ids, b"before")

    def test_fixed_write(self):
        with self.fence() as replace:
            replace(b"after")
        self.assertEqual(self.target.read_bytes(), b"after")

    def test_hardlink_denied(self):
        alias = self.root / "alias"
        os.link(self.target, alias)
        with self.assertRaises(FenceDenied):
            with self.fence():
                self.fail("hardlink entered")
        self.assertEqual(alias.read_bytes(), b"before")

    def test_symlink_denied(self):
        outside = self.root / "outside"
        outside.write_bytes(b"before")
        self.target.unlink()
        self.target.symlink_to(outside)
        with self.assertRaises(OSError):
            with self.fence():
                self.fail("symlink entered")
        self.assertEqual(outside.read_bytes(), b"before")

    def test_replacement_after_open_denied(self):
        original = self.docs / "original"
        with self.fence() as replace:
            self.target.rename(original)
            self.target.write_bytes(b"before")
            with self.assertRaises(FenceDenied):
                replace(b"after")
        self.assertEqual(original.read_bytes(), b"before")
        self.assertEqual(self.target.read_bytes(), b"before")

    def test_baseline_bytes_changed_denied(self):
        with self.fence() as replace:
            self.target.write_bytes(b"drift")
            with self.assertRaises(FenceDenied):
                replace(b"after")
        self.assertEqual(self.target.read_bytes(), b"drift")

    def test_directory_symlink_denied(self):
        other = self.root / "other"
        self.docs.rename(other)
        self.docs.symlink_to(other, target_is_directory=True)
        with self.assertRaises(OSError):
            with self.fence():
                self.fail("linked directory entered")
        self.assertEqual((other / "owned.txt").read_bytes(), b"before")
