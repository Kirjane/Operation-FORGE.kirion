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
from contextlib import closing, contextmanager
from itertools import permutations
from unittest.mock import patch
from pathlib import Path

from integrations.antigravity.factory import WORKFLOWS_ROOT
from integrations.antigravity.factory.authority import AuthorityError
from integrations.antigravity.factory.dispatcher import FleetDispatcher
from integrations.antigravity.factory.dispatch_preflight import ContractJournal, FixtureDispatchAdapter, archive_historical_journal
from integrations.antigravity.factory.mission_contract import contract_digest, digest_json
from integrations.antigravity.factory.delivery import NairuDeliveryBroker, DeliveryBrokerError
from integrations.antigravity.factory.scheduler import FactoryJournal, SchedulerError, storage_catalog
from integrations.antigravity.factory.ownership import LeaseManager, LeaseConflictError
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


class ControlledClock:
    """Advance UTC explicitly; no wall-time sleeps are needed for expiry tests."""

    def __init__(self):
        self.current = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)

    def advance(self, seconds):
        self.current += dt.timedelta(seconds=seconds)

    @contextmanager
    def installed(self):
        clock = self

        class ClockedDatetime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return clock.current.astimezone(tz) if tz else clock.current.replace(tzinfo=None)

        with patch.object(dt, "datetime", ClockedDatetime):
            yield self


def successor_contract(prior):
    successor = copy.deepcopy(prior)
    successor.update(revision=prior["revision"] + 1, previous_contract_sha256=contract_digest(prior),
                     revision_reason="Explicit successor", run_id="run-successor",
                     authorization_ref="FORGE-AUTH-successor")
    successor["authority"].update(parent_grant_ref=prior["authorization_ref"],
                                  directive_ref=successor["authorization_ref"])
    return successor


def review_contract():
    packet = make_contract()
    packet.update(assigned_persona="Antigravity-Nox", formal_role="Reviewer",
                  allowed_operations=["REVIEW_READONLY"])
    packet["authority"]["grant_scope"] = ["REVIEW_READONLY"]
    packet["required_capabilities"] = [{"capability_id": "independent_review_context",
        "operation": "REVIEW_READONLY", "scope": ["docs"], "environment": "fixture",
        "independence_required": True}]
    return packet


def add_read_scope(packet):
    packet["allowed_operations"].append("READ")
    packet["authority"]["grant_scope"].append("READ")
    packet["required_capabilities"].append(make_contract()["required_capabilities"][0])


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
        # Current initialization is guarded under the writer lock as well.
        legacy = object.__new__(FactoryJournal)
        legacy.db_path = self.journal.db_path
        with self.assertRaises(SchedulerError):
            legacy._init_db()
        # Reproduce the historical unpatched journal DDL directly, then test
        # its unchanged write methods without relying on the startup guard.
        with closing(sqlite3.connect(original.db_path)) as source:
            historical_ddl = [row[0] for row in source.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        with closing(sqlite3.connect(self.journal.db_path)) as target, target:
            for ddl in historical_ddl:
                target.execute(ddl.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1))
        with self.assertRaises(sqlite3.OperationalError):
            legacy.register_mission(packet)
        with self.assertRaises(sqlite3.OperationalError):
            legacy.record_idempotent_dispatch("old-key", packet["mission_id"], "old-worker", "old-context", {})
        with self.assertRaises(SchedulerError):
            legacy.transition_state(packet["mission_id"], "ACTIVE", expected_version=1, actor_role="Engineer")
        self.assertEqual(self.journal.list_events(), current)
        self.assertTrue(ContractJournal(self.journal.db_path).verify_hash_chain())
        self.assertEqual(original.list_events(), old_events)


    def test_nested_revision_policy_is_not_grant_envelope(self):
        prior = self.packet
        second = copy.deepcopy(prior["source_authorities"][0])
        second.update(source_id="presentation", authority_kind="PRESENTATION")
        prior["source_authorities"].append(second)
        prior["authority"].update(source_precedence=["contract", "presentation"], brain_required=True)
        prior["cognition_hash"] = "f" * 64
        prior["cognition"] = {"mode": "INHERITED", "brain_run_id": "brain-fixture",
            "context_sha256": "f" * 64, "manifest_ref": "fixture-manifest",
            "target_binding": digest_json({key: prior[key] for key in
                ("repo_id", "repo_name", "base_sha", "permitted_branch")}), "reason": None}
        self.assertEqual(self.dispatch(self.adapter(prior), prior)["status"], "COMPLETED")
        for field, value in (("source_precedence", ["presentation", "contract"]),
                             ("brain_required", False),
                             ("permitted_revision_fields", ["objective", "source_authorities"])):
            with self.subTest(field=field):
                changed = successor_contract(prior)
                changed["authority"][field] = value
                # Each changed packet receives its own otherwise valid exact-digest grant.
                outcome = self.dispatch(self.adapter(changed), changed)
                self.assertEqual(outcome["status"], "BLOCKED")
                self.assertIn("UNAUTHORIZED_REVISION_FIELDS", outcome["reason"])
                self.assertEqual(self.journal.get_mission(prior["mission_id"])["digest"], contract_digest(prior))
                self.assertEqual(len(self.calls), 1)
        unknown = successor_contract(prior)
        unknown["authority"]["unknown_policy"] = True
        with self.assertRaises(AuthorityError):
            self.dispatch(self.adapter(prior), unknown)
        self.assertEqual(self.journal.get_mission(prior["mission_id"])["revision"], 1)
        allowed = successor_contract(prior)
        allowed["authority"].update(issuer_actor_id=456, issuer_role="Maintainer", directive_sha256="e" * 64)
        allowed["objective"]["statement"] = "Authorized objective renewal"
        self.assertEqual(self.dispatch(self.adapter(allowed), allowed)["status"], "COMPLETED")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.journal.get_mission(prior["mission_id"])["revision"], 2)
        self.assertTrue(self.journal.verify_hash_chain())

    def test_scope_revision_requires_predecessor_operation_permission(self):
        for permitted in (False, True):
            with self.subTest(permitted=permitted):
                journal = ContractJournal(self.root / ("scope-permitted.sqlite" if permitted else "scope-denied.sqlite"))
                prior = review_contract()
                if permitted:
                    prior["authority"]["permitted_revision_fields"] += ["allowed_operations", "required_capabilities"]
                self.assertEqual(self.dispatch(self.adapter(prior), prior, journal)["status"], "COMPLETED")
                successor = successor_contract(prior)
                add_read_scope(successor)
                outcome = self.dispatch(self.adapter(successor), successor, journal)
                self.assertEqual(outcome["status"], "COMPLETED" if permitted else "BLOCKED")
                if not permitted:
                    self.assertIn("UNAUTHORIZED_REVISION_FIELDS", outcome["reason"])
                self.assertEqual(journal.get_mission(prior["mission_id"])["revision"], 2 if permitted else 1)
                self.assertTrue(journal.verify_hash_chain())

    def test_delayed_probe_crosses_capability_expiry(self):
        with ControlledClock().installed() as clock:
            grant = make_grant(self.packet)
            observed = make_observation(self.packet, grant)
            observed["capabilities"]["repository_read"]["valid_until_utc"] = timestamp(1)
            def delayed(_packet):
                clock.advance(2)
                return observed
            outcome = self.dispatch(self.adapter(grant=grant, observe=delayed))
            self.assertEqual(outcome["status"], "BLOCKED")
            self.assertIn("EXPIRED", outcome["reason"])
            self.assertEqual(self.calls, [])

    def test_fresh_observation_generated_during_probe(self):
        with ControlledClock().installed() as clock:
            grant = make_grant(self.packet)
            def observe(packet):
                clock.advance(5)
                return make_observation(packet, grant)
            self.assertEqual(self.dispatch(self.adapter(grant=grant, observe=observe))["status"], "COMPLETED")
            self.assertEqual(len(self.calls), 1)

    def test_grant_expires_during_probe_independently(self):
        with ControlledClock().installed() as clock:
            grant = make_grant(self.packet)
            grant["valid_until_utc"] = timestamp(1)
            observed = make_observation(self.packet, grant)
            def delayed(_packet):
                clock.advance(2)
                return observed
            outcome = self.dispatch(self.adapter(grant=grant, observe=delayed))
            self.assertEqual(outcome["status"], "BLOCKED")
            self.assertIn("GRANT", outcome["reason"])
            self.assertEqual(self.calls, [])

    def test_reserved_claim_expiry_consumes_slot_without_effect(self):
        with ControlledClock().installed() as clock:
            grant = make_grant(self.packet)
            observed = make_observation(self.packet, grant)
            observed["capabilities"]["repository_read"]["valid_until_utc"] = timestamp(1)
            reserve = self.journal.reserve_dispatch
            def delayed_reserve(*args, **kwargs):
                claim = reserve(*args, **kwargs)
                clock.advance(2)
                return claim
            with patch.object(self.journal, "reserve_dispatch", side_effect=delayed_reserve):
                outcome = self.dispatch(self.adapter(grant=grant, observe=lambda p: observed))
            self.assertEqual(outcome["status"], "NO_EFFECT")
            self.assertIn("CAPABILITY_EXPIRED", outcome["reason"])
            self.assertEqual(self.calls, [])
            reopened = ContractJournal(self.journal.db_path)
            other = {**self.packet, "run_id": "retry-without-authority"}
            self.assertEqual(self.dispatch(self.adapter(), other, reopened)["status"], "NO_EFFECT")
            self.assertEqual(self.calls, [])
            self.assertEqual(self.dispatch(self.adapter(ordinal=3), other, reopened)["status"], "BLOCKED")
            self.assertEqual(self.dispatch(self.adapter(ordinal=2), other, reopened)["status"], "COMPLETED")
            self.assertEqual(self.calls, [other["run_id"]])
            with closing(sqlite3.connect(reopened.db_path)) as conn:
                self.assertEqual(conn.execute("SELECT ordinal,status FROM contract_attempts ORDER BY ordinal").fetchall(),
                                 [(1, "NO_EFFECT"), (2, "COMPLETED")])
            self.assertTrue(reopened.verify_hash_chain())

    def test_expiry_after_running_before_callback(self):
        for expiring in ("capability", "grant"):
            with self.subTest(expiring=expiring), ControlledClock().installed() as clock:
                journal = ContractJournal(self.root / (expiring + ".sqlite"))
                grant = make_grant(self.packet)
                observed = make_observation(self.packet, grant)
                if expiring == "grant":
                    grant["valid_until_utc"] = timestamp(1)
                else:
                    observed["capabilities"]["repository_read"]["valid_until_utc"] = timestamp(1)
                adapter = self.adapter(grant=grant, observe=lambda p: observed)
                invoke = adapter.invoke
                def delayed_invoke(*args, **kwargs):
                    clock.advance(2)
                    return invoke(*args, **kwargs)
                with patch.object(adapter, "invoke", side_effect=delayed_invoke):
                    outcome = self.dispatch(adapter, journal=journal)
                self.assertEqual(outcome["status"], "NO_EFFECT")
                self.assertIn(expiring.upper(), outcome["reason"])
                self.assertEqual(self.calls, [])
                events = journal.list_events()
                self.assertTrue(any(e["event_type"] == "DISPATCH_RUNNING" for e in events))
                self.assertTrue(any(e["event_type"] == "DISPATCH_NO_EFFECT" for e in events))
                self.assertTrue(journal.verify_hash_chain())

    def test_newer_expired_observation_invalidates_older_available(self):
        with ControlledClock().installed() as clock:
            grant = make_grant(self.packet)
            older = make_observation(self.packet, grant)
            older["capabilities"]["repository_read"]["observed_at_utc"] = timestamp(-30)
            newer = copy.deepcopy(older)
            newer["capabilities"]["repository_read"].update(
                observed_at_utc=timestamp(-10), valid_until_utc=timestamp(-5))
            self.assertEqual(self.dispatch(self.adapter(grant=grant, observe=lambda p: newer))["status"], "BLOCKED")
            outcome = self.dispatch(self.adapter(grant=grant, observe=lambda p: older))
            self.assertEqual(outcome["status"], "BLOCKED")
            self.assertIn("STALE_OBSERVATION", outcome["reason"])
            self.assertEqual(self.calls, [])
            clock.advance(2)
            self.assertEqual(self.dispatch(self.adapter(grant=grant))["status"], "COMPLETED")
            self.assertEqual(len(self.calls), 1)

    def test_invalid_observations_do_not_poison_chronology(self):
        with ControlledClock().installed():
            grant = make_grant(self.packet)
            older = make_observation(self.packet, grant)
            older["capabilities"]["repository_read"]["observed_at_utc"] = timestamp(-30)
            for field, value in (("observed_at_utc", timestamp(20)), ("observed_at_utc", "invalid"),
                                 ("worker_id", "wrong-worker"), ("probe_sha256", "0" * 64),
                                 ("scope", ["docs", "../escape"])):
                invalid = make_observation(self.packet, grant)
                invalid["capabilities"]["repository_read"][field] = value
                self.assertEqual(self.dispatch(self.adapter(grant=grant, observe=lambda p: invalid))["status"], "BLOCKED")
            mismatched = make_observation(self.packet, grant)
            mismatched["target"]["repo_id"] = 999
            self.assertEqual(self.dispatch(self.adapter(grant=grant, observe=lambda p: mismatched))["status"], "BLOCKED")
            self.assertEqual(self.calls, [])
            self.assertEqual(self.dispatch(self.adapter(grant=grant, observe=lambda p: older))["status"], "COMPLETED")

    def test_equal_time_conflict_requires_strictly_newer_evidence(self):
        with ControlledClock().installed() as clock:
            grant = make_grant(self.packet)
            unavailable = make_observation(self.packet, grant)
            unavailable["capabilities"]["repository_read"]["status"] = "UNAVAILABLE"
            conflicting = copy.deepcopy(unavailable)
            conflicting["capabilities"]["repository_read"]["status"] = "AVAILABLE"
            # Same instant represented by equivalent UTC spellings.
            conflicting["capabilities"]["repository_read"]["observed_at_utc"] = (
                conflicting["capabilities"]["repository_read"]["observed_at_utc"].replace("+00:00", "Z"))
            self.assertEqual(self.dispatch(self.adapter(grant=grant, observe=lambda p: unavailable))["status"], "BLOCKED")
            for observation in (conflicting, unavailable, conflicting):
                outcome = self.dispatch(self.adapter(grant=grant, observe=lambda p: observation))
                self.assertIn("STALE_OBSERVATION", outcome["reason"])
            self.assertEqual(self.calls, [])
            clock.advance(2)
            self.assertEqual(self.dispatch(self.adapter(grant=grant))["status"], "COMPLETED")

    def test_active_reservation_and_running_reject_recovery(self):
        reserved, start, entered, release = (threading.Event() for _ in range(4))
        claim_info = {}
        reserve = self.journal.reserve_dispatch
        def held_reserve(*args, **kwargs):
            claim = reserve(*args, **kwargs)
            claim_info.update(claim)
            reserved.set()
            if not start.wait(5):
                raise RuntimeError("Fixture start timeout")
            return claim
        def handler(packet):
            self.calls.append(packet["run_id"])
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Fixture completion timeout")
            return {"checked": True}
        with patch.object(self.journal, "reserve_dispatch", side_effect=held_reserve):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.dispatch, self.adapter(handler=handler))
                try:
                    self.assertTrue(reserved.wait(5))
                    reservation = claim_info["reservation_id"]
                    raw = json.dumps(self.packet)
                    evidence = {reservation: {"contract_sha256": contract_digest(self.packet),
                        "reservation_id": reservation, "quiescent": True, "effect": "NO_EFFECT",
                        "evidence_ref": "unproven-fixture-quiescence"}}
                    reopened = ContractJournal(self.journal.db_path)
                    recovery = self.adapter(reconciliations=evidence)
                    with self.assertRaises(SchedulerError):
                        reopened.reconcile_unknown(raw, reservation, recovery)
                    self.assertEqual(self.dispatch(self.adapter(ordinal=2), journal=reopened)["status"], "BLOCKED")
                    self.assertEqual(self.calls, [])
                    start.set()
                    self.assertTrue(entered.wait(5))
                    with self.assertRaises(SchedulerError):
                        reopened.reconcile_unknown(raw, reservation, recovery)
                    competing = {**self.packet, "run_id": "competing-run"}
                    self.assertEqual(self.dispatch(self.adapter(worker="other"), competing, reopened)["status"], "RUNNING")
                    self.assertEqual(self.dispatch(self.adapter(ordinal=2), competing, reopened)["status"], "BLOCKED")
                finally:
                    start.set()
                    release.set()
                self.assertEqual(future.result(timeout=5)["status"], "COMPLETED")
        self.assertEqual(self.dispatch(self.adapter(), journal=reopened)["status"], "COMPLETED")
        with self.assertRaises(SchedulerError):
            reopened.complete_dispatch(raw, reservation, {"late": True}, self.adapter())
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(reopened.verify_hash_chain())

    def test_current_broker_cannot_change_contract_storage(self):
        self.assertEqual(self.dispatch(self.adapter())["status"], "COMPLETED")
        with closing(sqlite3.connect(self.journal.db_path)) as conn:
            before = list(conn.iterdump())
            mode = conn.execute("PRAGMA journal_mode").fetchone()
        actors = []
        with self.assertRaises(DeliveryBrokerError):
            NairuDeliveryBroker(self.journal.db_path, actor_verifier=lambda: actors.append("called"))
        self.assertEqual(actors, [])
        with closing(sqlite3.connect(self.journal.db_path)) as conn:
            self.assertEqual(list(conn.iterdump()), before)
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone(), mode)
        self.assertTrue(ContractJournal(self.journal.db_path).verify_hash_chain())

    def test_historical_shared_storage_and_backup_in_both_orders(self):
        for broker_first in (True, False):
            with self.subTest(broker_first=broker_first):
                db = self.root / ("broker-first.sqlite" if broker_first else "journal-first.sqlite")
                if broker_first:
                    NairuDeliveryBroker(db)
                journal = FactoryJournal(db)
                if not broker_first:
                    NairuDeliveryBroker(db)
                journal.register_mission(historical_packet())
                with closing(sqlite3.connect(db)) as conn, conn:
                    conn.execute("INSERT INTO delivery_receipts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        ("delivery-key", "fixture-mission", "feat/fixture", "a"*40, "b"*40,
                         "Kirch-Nairu", 291564617, "RECORDED", "DRAFT", "fixture receipt", timestamp()))
                backup = db.with_suffix(".backup")
                archive_historical_journal(db, backup)
                self.assertTrue(FactoryJournal(db).verify_hash_chain())
                self.assertTrue(FactoryJournal(backup).verify_hash_chain())
                NairuDeliveryBroker(backup)
                with closing(sqlite3.connect(db)) as conn, closing(sqlite3.connect(backup)) as copied:
                    self.assertEqual(conn.execute("SELECT * FROM delivery_receipts").fetchall(),
                                     copied.execute("SELECT * FROM delivery_receipts").fetchall())
                with self.assertRaises(SchedulerError):
                    ContractJournal(db)

    def test_concurrent_contract_and_legacy_initialization_do_not_mix(self):
        db = self.root / "concurrent-storage.sqlite"
        barrier = threading.Barrier(2)
        def initialize(kind):
            barrier.wait(timeout=5)
            try:
                if kind == "contract":
                    ContractJournal(db)
                else:
                    NairuDeliveryBroker(db)
                return kind
            except (SchedulerError, DeliveryBrokerError):
                return "denied"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(initialize, ["contract", "broker"]))
        self.assertEqual(outcomes.count("denied"), 1)
        with closing(sqlite3.connect(db)) as conn:
            names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
        if "contract" in outcomes:
            self.assertNotIn("delivery_receipts", names)
            self.assertTrue(ContractJournal(db).verify_hash_chain())
        else:
            self.assertIn("delivery_receipts", names)
            self.assertNotIn("contract_heads", names)
            FactoryJournal(db)
            with self.assertRaises(SchedulerError):
                ContractJournal(db)


class OwnershipStorageIsolationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def snapshot(self, db):
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            return (storage_catalog(conn), list(conn.iterdump()),
                    conn.execute("PRAGMA journal_mode").fetchone())

    def exercise_lease_lifecycle(self, leases):
        packet = historical_packet()
        acquired = leases.acquire_leases(packet, "fixture-worker", ttl_seconds=60, now_epoch=100)
        self.assertEqual(len(acquired), 1)
        lease = acquired[0]
        self.assertEqual((lease["version"], lease["expires_at_epoch"]), (1, 160))
        with self.assertRaises(LeaseConflictError):
            leases.acquire_leases(packet, "competitor", now_epoch=101)
        beat = leases.heartbeat(lease["lease_id"], worker_id="fixture-worker", expected_version=1,
                                ttl_seconds=60, now_epoch=110)
        self.assertEqual((beat["version"], beat["expires_at_epoch"]), (2, 170))
        with self.assertRaises(LeaseConflictError):
            leases.heartbeat(lease["lease_id"], worker_id="fixture-worker", expected_version=1, now_epoch=111)
        self.assertEqual(leases.release_worker_leases(packet["mission_id"], "fixture-worker"), 1)
        self.assertEqual(leases.release_worker_leases(packet["mission_id"], "fixture-worker"), 0)
        with self.assertRaises(LeaseConflictError):
            leases.heartbeat(lease["lease_id"], worker_id="fixture-worker", expected_version=3, now_epoch=112)
        again = leases.acquire_leases(packet, "competitor", ttl_seconds=60, now_epoch=120)
        self.assertEqual((again[0]["version"], again[0]["expires_at_epoch"]), (4, 180))
        self.assertEqual(leases.release_worker_leases(packet["mission_id"], "competitor"), 1)

    def test_contract_first_rejects_lease_without_wal_or_catalog_mutation(self):
        for populated in (False, True):
            with self.subTest(populated=populated):
                db = self.root / ("populated.sqlite" if populated else "fresh.sqlite")
                journal = ContractJournal(db)
                if populated:
                    packet = make_contract()
                    grant = make_grant(packet)
                    adapter = FixtureDispatchAdapter(grants={contract_digest(packet): grant},
                        trusted_verifiers={packet["verifier"]}, observe=lambda p: make_observation(p, grant),
                        handler=lambda p: {"checked": True})
                    self.assertEqual(journal.dispatch_fixture(json.dumps(packet), adapter)["status"], "COMPLETED")
                before = self.snapshot(db)
                # Fresh contract storage has not enabled WAL; denial must not enable it.
                if not populated:
                    self.assertEqual(before[2], ("delete",))
                with self.assertRaises(LeaseConflictError) as error:
                    LeaseManager(db)
                self.assertIsInstance(error.exception.__cause__, SchedulerError)
                self.assertEqual(self.snapshot(db), before)
                self.assertNotIn("leases", before[0])
                self.assertTrue(ContractJournal(db).verify_hash_chain())

    def test_lease_first_rejects_contract_and_preserves_lease_operations(self):
        db = self.root / "lease-only.sqlite"
        leases = LeaseManager(db)
        self.exercise_lease_lifecycle(leases)
        before = self.snapshot(db)
        self.assertEqual(before[0], {"leases": "table"})
        with self.assertRaises(SchedulerError):
            ContractJournal(db)
        self.assertEqual(self.snapshot(db), before)
        self.assertEqual(self.snapshot(LeaseManager(db).db_path), before)

    def test_historical_three_way_storage_all_initialization_orders(self):
        constructors = {"journal": FactoryJournal, "broker": NairuDeliveryBroker, "lease": LeaseManager}
        for order in permutations(constructors):
            with self.subTest(order=order):
                db = self.root / ("-".join(order) + ".sqlite")
                instances = {name: constructors[name](db) for name in order}
                journal = instances["journal"]
                journal.register_mission(historical_packet())
                self.exercise_lease_lifecycle(instances["lease"])
                with closing(sqlite3.connect(db)) as conn, conn:
                    conn.execute("INSERT INTO delivery_receipts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        ("delivery-key", "fixture-mission", "feat/fixture", "a"*40, "b"*40,
                         "Kirch-Nairu", 291564617, "RECORDED", "DRAFT", "fixture receipt", timestamp()))
                before = self.snapshot(db)
                self.assertEqual(set(before[0]), {"missions", "dispatches", "journal_events",
                                                  "delivery_receipts", "leases"})
                for name in reversed(order):
                    constructors[name](db)
                with self.assertRaises(SchedulerError):
                    ContractJournal(db)
                self.assertEqual(self.snapshot(db), before)
                self.assertTrue(journal.verify_hash_chain())

    def test_concurrent_contract_and_lease_initialization_do_not_mix(self):
        db = self.root / "competing.sqlite"
        barrier = threading.Barrier(2)
        def initialize(kind):
            barrier.wait(timeout=5)
            try:
                (ContractJournal if kind == "contract" else LeaseManager)(db)
                return kind
            except (SchedulerError, LeaseConflictError):
                return "denied"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(initialize, ("contract", "lease")))
        self.assertEqual(outcomes.count("denied"), 1)
        before = self.snapshot(db)
        if "contract" in outcomes:
            self.assertNotIn("leases", before[0])
            with self.assertRaises(LeaseConflictError):
                LeaseManager(db)
            self.assertEqual(self.snapshot(db), before)
            self.assertTrue(ContractJournal(db).verify_hash_chain())
        else:
            self.assertEqual(before[0], {"leases": "table"})
            with self.assertRaises(SchedulerError):
                ContractJournal(db)
            self.assertEqual(self.snapshot(db), before)
            self.exercise_lease_lifecycle(LeaseManager(db))

    def test_incompatible_legacy_leases_view_denied_before_mutation(self):
        for constructor, error in ((LeaseManager, LeaseConflictError), (FactoryJournal, SchedulerError),
                                   (NairuDeliveryBroker, DeliveryBrokerError), (ContractJournal, SchedulerError)):
            with self.subTest(constructor=constructor.__name__):
                db = self.root / (constructor.__name__ + ".sqlite")
                with closing(sqlite3.connect(db)) as conn, conn:
                    conn.execute("CREATE VIEW leases AS SELECT 1 AS lease_id")
                before = self.snapshot(db)
                with self.assertRaises(error):
                    constructor(db)
                self.assertEqual(self.snapshot(db), before)


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
