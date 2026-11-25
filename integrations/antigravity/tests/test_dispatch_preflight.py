"""Discriminating dispatch, reservation, migration and native-entry tests.

All handler and observation callbacks are isolated synthetic fixtures, not live host evidence.
"""
from __future__ import annotations

import ast
import asyncio
import copy
import datetime as dt
import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from integrations.antigravity.factory import WORKFLOWS_ROOT
from integrations.antigravity.factory.authority import AuthorityError
from integrations.antigravity.factory.dispatcher import FleetDispatcher
from integrations.antigravity.factory.dispatch_preflight import ContractJournal, FixtureDispatchAdapter, archive_historical_journal
from integrations.antigravity.factory.mission_contract import contract_digest
from integrations.antigravity.factory.scheduler import FactoryJournal, SchedulerError
from integrations.antigravity.tests.test_mission_contract import make_contract, historical_packet


def timestamp(seconds=0):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)).isoformat()


def make_grant(packet, worker="fixture-worker", ordinal=1):
    return {**{key: packet["authority"][key] for key in
               ("issuer_actor_id", "issuer_role", "directive_ref", "directive_sha256")},
            "contract_sha256": contract_digest(packet), "revision": packet["revision"],
            "verifier": packet["verifier"], "persona": packet["assigned_persona"],
            "formal_role": packet["formal_role"], "worker_id": worker,
            "actor_id": worker + "-actor", "host_id": "fixture-host",
            "attempt_ordinal": ordinal, "revoked": False,
            "observed_at_utc": timestamp(-60), "valid_until_utc": timestamp(3600)}


def make_observation(packet, grant):
    return {
        "target": {key: packet[key] for key in
                   ("repo_id", "repo_name", "base_sha", "permitted_branch", "delivery_destination")},
        "sources": {s["source_id"]: {key: s[key] for key in ("repository_id", "repository_name", "commit_sha")}
                    for s in packet["source_authorities"]},
        "oracles": {o["oracle_id"]: {key: o[key] for key in ("source_id", "path", "blob_sha", "fixture_sha256")}
                    for o in packet["oracles"]},
        "cognition": packet["cognition"],
        "capabilities": {c["capability_id"]: {
            "contract_sha256": contract_digest(packet), "revision": packet["revision"],
            "mission_id": packet["mission_id"], "worker_id": grant["worker_id"],
            "actor_id": grant["actor_id"], "host_id": grant["host_id"],
            "capability_id": c["capability_id"], "operation": c["operation"],
            "environment": c["environment"], "scope": c["scope"], "status": "AVAILABLE",
            "independent": c["independence_required"], "probe_ref": "synthetic-probe",
            "probe_sha256": "e" * 64, "observed_at_utc": timestamp(-1),
            "valid_until_utc": timestamp(3600)} for c in packet["required_capabilities"]},
    }


class DispatchPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = ContractJournal(self.root / "contract.sqlite")
        self.packet = make_contract()
        self.calls = []
        self.dispatcher = FleetDispatcher()

    def adapter(self, packet=None, *, worker="fixture-worker", ordinal=1, grant=None,
                observe=None, handler=None, verifiers=None, reconciliations=None):
        packet = packet or self.packet
        grant = grant if grant is not None else make_grant(packet, worker, ordinal)
        def default_handler(p):
            self.calls.append(p["run_id"])
            return {"checked": True}
        return FixtureDispatchAdapter(
            grants={contract_digest(packet): grant},
            trusted_verifiers={packet["verifier"]} if verifiers is None else verifiers,
            observe=observe or (lambda p: make_observation(p, grant)),
            handler=handler or default_handler, reconciliations=reconciliations)

    def dispatch(self, adapter, packet=None, journal=None):
        return self.dispatcher.dispatch_worker(json.dumps(packet or self.packet),
            journal=journal or self.journal, fixture_adapter=adapter)

    def blockers(self):
        return [e for e in self.journal.list_events() if e["event_type"] == "DISPATCH_BLOCKED"]

    def test_forged_grant_and_empty_verifier_set(self):
        packet = self.packet
        valid = make_grant(packet)
        for grant in ({}, {**valid, "issuer_actor_id": 999}, {**valid, "revoked": True},
                      {**valid, "valid_until_utc": timestamp(-2)}):
            self.assertEqual(self.dispatch(self.adapter(grant=grant))["status"], "BLOCKED")
        self.assertEqual(self.dispatch(self.adapter(verifiers=set()))["status"], "BLOCKED")
        changed = copy.deepcopy(packet)
        changed["objective"]["statement"] = "Unauthorized objective"
        self.assertEqual(self.dispatch(self.adapter(), changed)["status"], "BLOCKED")
        self.assertEqual(self.calls, [])
        with self.assertRaises(SchedulerError):
            self.journal.get_mission(packet["mission_id"])

    def test_target_source_oracle_and_capability_mismatch(self):
        grant = make_grant(self.packet)
        for group, field, value in (
            ("target", "repo_id", 43), ("target", "base_sha", "f" * 40),
            ("target", "permitted_branch", "feat/wrong"), ("target", "repo_name", "wrong/repo"),
            ("target", "delivery_destination", "wrong-destination"),
            ("sources", "contract", {}), ("oracles", "source_observation", {}),
        ):
            def observe(p, group=group, field=field, value=value):
                observed = make_observation(p, grant)
                observed[group][field] = value
                return observed
            with self.subTest(group=group, field=field):
                self.assertEqual(self.dispatch(self.adapter(grant=grant, observe=observe))["status"], "BLOCKED")
        for field, value in (("status", "UNKNOWN"), ("status", "UNAVAILABLE"), ("status", "MADE_UP"),
                             ("valid_until_utc", timestamp(-1)), ("scope", ["wrong"]),
                             ("worker_id", "spoof"), ("contract_sha256", "f" * 64),
                             ("environment", "wrong"), ("probe_sha256", "0" * 64)):
            def observe(p, field=field, value=value):
                observed = make_observation(p, grant)
                observed["capabilities"]["repository_read"][field] = value
                return observed
            with self.subTest(field=field, value=value):
                self.assertEqual(self.dispatch(self.adapter(grant=grant, observe=observe))["status"], "BLOCKED")
        self.assertEqual(self.calls, [])

    def test_relevant_prerequisite_replay_and_positive_control(self):
        grant = make_grant(self.packet)
        status = {"available": False, "unrelated": False, "missing": True}
        def observe(p):
            observed = make_observation(p, grant)
            if status["missing"]:
                observed["capabilities"] = {}
            else:
                observed["capabilities"]["repository_read"]["status"] = (
                    "AVAILABLE" if status["available"] else "UNAVAILABLE")
            if status["unrelated"]:
                observed["capabilities"]["unrelated"] = {"status": "AVAILABLE"}
            return observed
        adapter = self.adapter(grant=grant, observe=observe)
        first = self.dispatch(adapter)
        self.assertEqual(first["status"], "BLOCKED")
        self.assertEqual(self.journal.get_mission(self.packet["mission_id"])["state"], "BLOCKED")
        other = {**self.packet, "run_id": "run-restarted"}
        status["unrelated"] = True
        again = self.dispatch(adapter, other)
        self.assertTrue(again["cached"])
        self.assertEqual(first["prerequisite_fingerprint"], again["prerequisite_fingerprint"])
        self.assertEqual(len(self.blockers()), 1)
        status["missing"] = False
        unavailable = self.dispatch(adapter, other)
        self.assertEqual(unavailable["status"], "BLOCKED")
        self.assertTrue(self.dispatch(adapter)["cached"])  # fresh timestamps only
        self.assertEqual(len(self.blockers()), 2)
        self.assertEqual(self.calls, [])
        status["available"] = True
        completed = self.dispatch(adapter, other)
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertTrue(completed["fixture_only"])
        self.assertEqual(completed["result"], {"checked": True})
        self.assertTrue(self.dispatch(adapter)["cached"])
        self.assertEqual(self.calls, ["run-restarted"])
        self.assertTrue(self.journal.verify_hash_chain())

    def test_stale_observation_cannot_resolve_blocker(self):
        grant = make_grant(self.packet)
        recent = make_observation(self.packet, grant)
        recent["capabilities"]["repository_read"]["status"] = "UNAVAILABLE"
        recent["capabilities"]["repository_read"]["observed_at_utc"] = timestamp(-2)
        stale = copy.deepcopy(recent)
        stale["capabilities"]["repository_read"]["status"] = "AVAILABLE"
        stale["capabilities"]["repository_read"]["observed_at_utc"] = timestamp(-20)
        self.assertEqual(self.dispatch(self.adapter(grant=grant, observe=lambda p: recent))["status"], "BLOCKED")
        result = self.dispatch(self.adapter(grant=grant, observe=lambda p: stale))
        self.assertIn("STALE_OBSERVATION", result["reason"])
        self.assertEqual(self.calls, [])

    def test_concurrent_claims_distinct_worker_and_run(self):
        barrier = threading.Barrier(2)
        def claim(worker):
            packet = {**self.packet, "run_id": "run-" + worker}
            adapter = self.adapter(worker=worker)
            barrier.wait(timeout=5)
            return self.journal.reserve_dispatch(json.dumps(packet), adapter)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ["fixture-a", "fixture-b"]))
        self.assertEqual(sum(not r["cached"] for r in results), 1)
        self.assertEqual({r["status"] for r in results}, {"RESERVED"})
        self.assertEqual(self.calls, [])
        winner = next(r for r in results if not r["cached"])
        with closing(sqlite3.connect(self.journal.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM contract_attempts").fetchone()[0], 1)
        self.assertTrue(self.journal.verify_hash_chain())
        # Stranded reservation remains non-replayable after reopen.
        reopened = ContractJournal(self.journal.db_path)
        self.assertTrue(self.dispatch(self.adapter(worker="fixture-c"), journal=reopened)["cached"])
        self.assertEqual(self.calls, [])
        with self.assertRaises(SchedulerError):
            reopened.complete_dispatch(json.dumps(self.packet), winner["reservation_id"], {"forged": True}, self.adapter())

    def test_running_attempt_blocks_competing_handler(self):
        entered, release = threading.Event(), threading.Event()
        def handler(packet):
            self.calls.append(packet["run_id"])
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Fixture timeout")
            return {"checked": True}
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(self.dispatch, self.adapter(worker="first", handler=handler))
            try:
                self.assertTrue(entered.wait(5))
                second = pool.submit(self.dispatch, self.adapter(worker="second"),
                                     {**self.packet, "run_id": "run-competitor"})
                self.assertEqual(second.result(timeout=5)["status"], "RUNNING")
                self.assertEqual(self.calls, [self.packet["run_id"]])
            finally:
                release.set()
            self.assertEqual(future.result(timeout=5)["status"], "COMPLETED")

    def test_unknown_effect_requires_reconciliation_and_explicit_attempt(self):
        def interrupted(packet):
            self.calls.append(packet["run_id"])
            raise RuntimeError("Simulated uncertain effect")
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            self.dispatch(self.adapter(handler=interrupted))
        reservation = next(e["payload"]["reservation_id"] for e in self.journal.list_events()
                           if e["event_type"] == "DISPATCH_RESERVED")
        reopened = ContractJournal(self.journal.db_path)
        other = {**self.packet, "run_id": "run-retry"}
        self.assertEqual(self.dispatch(self.adapter(worker="other"), other, reopened)["status"], "UNKNOWN")
        self.assertEqual(self.dispatch(self.adapter(ordinal=2), other, reopened)["status"], "BLOCKED")
        raw = json.dumps(self.packet)
        with self.assertRaises(SchedulerError):
            reopened.reconcile_unknown(raw, reservation, self.adapter())
        evidence = {reservation: {"contract_sha256": contract_digest(self.packet),
                    "reservation_id": reservation, "quiescent": True, "effect": "NO_EFFECT",
                    "evidence_ref": "fixture-reconciliation"}}
        reopened.reconcile_unknown(raw, reservation, self.adapter(reconciliations=evidence))
        self.assertEqual(self.dispatch(self.adapter(), other, reopened)["status"], "RECONCILED")
        with self.assertRaises(SchedulerError):
            reopened.complete_dispatch(raw, reservation, {"stale": True}, self.adapter())
        self.assertEqual(self.dispatch(self.adapter(ordinal=2), other, reopened)["status"], "COMPLETED")
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(reopened.verify_hash_chain())

    def test_revision_and_scope_binding(self):
        first = self.dispatch(self.adapter())
        self.assertEqual(first["status"], "COMPLETED")
        prior = self.packet
        revised = copy.deepcopy(prior)
        revised.update(revision=2, previous_contract_sha256=contract_digest(prior),
                       revision_reason="Explicit successor", run_id="run-successor",
                       authorization_ref="FORGE-AUTH-successor")
        revised["authority"].update(parent_grant_ref=prior["authorization_ref"],
                                     directive_ref=revised["authorization_ref"])
        revised["objective"]["statement"] = "Inspect revised contract"
        self.assertEqual(self.dispatch(self.adapter(), revised)["status"], "BLOCKED")
        for key, value in (("excluded_paths", ["docs/other"]), ("base_sha", "f" * 40)):
            changed = copy.deepcopy(revised)
            changed[key] = value
            self.assertIn("UNAUTHORIZED_REVISION", self.dispatch(self.adapter(changed), changed)["reason"])
        changed = copy.deepcopy(revised)
        changed["oracles"][0]["blob_sha"] = "f" * 40
        self.assertIn("UNAUTHORIZED_REVISION", self.dispatch(self.adapter(changed), changed)["reason"])
        self.assertEqual(self.dispatch(self.adapter(revised), revised)["status"], "COMPLETED")
        with self.assertRaises(SchedulerError):
            self.journal.complete_dispatch(json.dumps(prior), first["reservation_id"], {}, self.adapter())
        self.assertEqual(self.journal.get_mission(prior["mission_id"])["revision"], 2)
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(self.journal.verify_hash_chain())

    def test_no_direct_lifecycle_or_live_handler_bypass(self):
        self.assertEqual(self.dispatcher.dispatch_worker(json.dumps(self.packet), lambda *a: self.calls.append(1))["status"], "BLOCKED")
        self.assertEqual(self.dispatcher.dispatch_worker(historical_packet(), lambda *a: self.calls.append(1))["status"], "BLOCKED")
        for state in ("ACTIVE", "ACCEPTED", "PROMOTED"):
            with self.assertRaises(SchedulerError):
                self.journal.transition_state(self.packet["mission_id"], state, expected_version=1, actor_role="Engineer")
        with self.assertRaises(SchedulerError):
            self.journal.record_idempotent_dispatch("key", self.packet["mission_id"], "spoof", "ctx", {})
        self.assertEqual(self.calls, [])

    def test_historical_archive_and_old_client_fence(self):
        original = FactoryJournal(self.root / "legacy.sqlite")
        packet = historical_packet()
        original.register_mission(packet)
        with self.assertRaises(SchedulerError):
            original.transition_state(packet["mission_id"], "AUTHORIZED", expected_version=1,
                                      actor_role="Maintainer", details={"actor_role": "Engineer"})
        old_events = original.list_events()
        backup = self.root / "legacy-backup.sqlite"
        digest = archive_historical_journal(original.db_path, backup)
        self.assertEqual(digest, hashlib.sha256(backup.read_bytes()).hexdigest())
        self.assertEqual(original.list_events(), old_events)
        self.assertTrue(original.verify_hash_chain())
        with closing(sqlite3.connect(backup.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            self.assertEqual(json.loads(conn.execute("SELECT packet_json FROM missions").fetchone()[0]), packet)
        with self.assertRaises(SchedulerError):
            ContractJournal(original.db_path)
        with self.assertRaises(SchedulerError):
            FactoryJournal(self.journal.db_path)
        self.dispatch(self.adapter())
        current = self.journal.list_events()
        # Bypass the new constructor only to emulate the exact unchanged old
        # initialization and write methods; do not rely on the new startup guard.
        legacy = object.__new__(FactoryJournal)
        legacy.db_path = self.journal.db_path
        legacy._init_db()
        with self.assertRaises(sqlite3.OperationalError):
            legacy.register_mission(packet)
        with self.assertRaises(sqlite3.OperationalError):
            legacy.record_idempotent_dispatch("old-key", packet["mission_id"], "old-worker", "old-context", {})
        with self.assertRaises(SchedulerError):
            legacy.transition_state(packet["mission_id"], "ACTIVE", expected_version=1, actor_role="Engineer")
        self.assertEqual(self.journal.list_events(), current)
        self.assertTrue(ContractJournal(self.journal.db_path).verify_hash_chain())
        self.assertEqual(original.list_events(), old_events)


class NativeWorkflowPreflightTests(unittest.TestCase):
    def test_all_native_workflows_block_before_any_agent_call(self):
        names = ("candidate_integration", "feature_delivery", "greenfield_discovery",
                 "nox_adversarial_audit", "recovery_reconcile", "self_healing_repair")
        for name in names:
            with self.subTest(workflow=name):
                path = WORKFLOWS_ROOT / (name + ".py")
                source = path.read_text(encoding="utf-8")
                code = compile(source, str(path), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
                for args in ({}, {"status": "AUTHORIZED", "trusted": True,
                                  "fixture_only": True, "base_sha": "a" * 40}):
                    reports, calls = [], []
                    def forbidden(*a, **k):
                        calls.append((a, k))
                        raise AssertionError("Native execution occurred")
                    env = {"args": args, "agent": forbidden, "parallel": forbidden,
                           "phase": forbidden, "log": forbidden, "print": reports.append}
                    execution = eval(code, env)
                    if asyncio.iscoroutine(execution):
                        asyncio.run(execution)
                    self.assertEqual(calls, [])
                    self.assertEqual(reports, [{"status": "BLOCKED",
                        "reason": "TRUSTED_NATIVE_PREFLIGHT_BRIDGE_UNAVAILABLE"}])
                self.assertNotIn('args.get(', source)


if __name__ == "__main__":
    unittest.main()
