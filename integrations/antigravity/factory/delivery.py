"""F09 — Nairu delivery broker and trust boundary enforcing verified Kirch-Nairu identity and draft-only PR delivery."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Callable

from . import EXPECTED_BROKER_LOGIN, EXPECTED_BROKER_USER_ID
from .authority import SHA40_RE, AuthorityError, verify_mission_packet
from .evidence import redact_secrets
from .policy import (
    PROTECTED_GOVERNANCE_PATHS,
    PolicyViolationError,
    assert_operation_allowed,
    assert_paths_within_ownership,
)
from .quality import NoxReviewEngine

PROHIBITED_BRANCH_NAMES = {"main", "master", "HEAD", "production", "release"}


class DeliveryBrokerError(PolicyViolationError):
    """Raised when the Nairu delivery broker blocks an unauthorized or unsafe remote operation."""


def compute_delivery_key(mission_id: str, branch: str, candidate_sha: str) -> str:
    material = f"{mission_id}:{branch}:{candidate_sha}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def probe_live_github_actor() -> dict[str, Any]:
    """Query `gh api user` on the host to verify the authenticated GitHub actor without exposing token values."""
    p = subprocess.run(
        ["gh", "api", "user", "--jq", "{login: .login, id: .id, type: .type}"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if p.returncode != 0:
        raise DeliveryBrokerError(f"Failed to verify GitHub identity via gh api user: {redact_secrets(p.stderr.strip())}")
    try:
        return json.loads(p.stdout.strip())
    except Exception as exc:
        raise DeliveryBrokerError(f"Malformed gh api user response: {exc}") from exc


class NairuDeliveryBroker:
    """Narrow remote write broker enforcing Kirch-Nairu actor verification, diff scope, and idempotent draft PR receipts."""

    def __init__(
        self,
        db_path: Path,
        *,
        actor_verifier: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.actor_verifier = actor_verifier or probe_live_github_actor
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_receipts (
                    delivery_key TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    base_sha TEXT NOT NULL,
                    candidate_sha TEXT NOT NULL,
                    actor_login TEXT NOT NULL,
                    actor_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    pr_mode TEXT NOT NULL,
                    receipt_markdown TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                """
            )
            conn.execute("COMMIT;")
        finally:
            conn.close()

    def verify_actor_identity(self) -> dict[str, Any]:
        actor = self.actor_verifier()
        login = actor.get("login")
        uid = actor.get("id")
        if login != EXPECTED_BROKER_LOGIN or uid != EXPECTED_BROKER_USER_ID:
            raise DeliveryBrokerError(
                f"Untrusted remote delivery identity: observed login={login!r} id={uid!r}, "
                f"expected login={EXPECTED_BROKER_LOGIN!r} id={EXPECTED_BROKER_USER_ID}"
            )
        return actor

    def deny_forbidden_remote_action(self, action: str) -> None:
        raise DeliveryBrokerError(
            f"Remote action {action!r} (merge, force-push, ref-delete, admin-edit, release, self-approve) "
            "is unconditionally denied by the Nairu delivery broker."
        )

    def format_start_close_receipt(
        self,
        *,
        packet: dict[str, Any],
        candidate_sha: str,
        changed_files: list[str],
        nox_result: dict[str, Any] | None,
        gate_summary: dict[str, Any],
        is_blocked_diagnostic: bool = False,
    ) -> str:
        mode_header = "BLOCKED DIAGNOSTIC DRAFT (NOT VALIDATED)" if is_blocked_diagnostic else "VALIDATED CANDIDATE DRAFT (NO MERGE)"
        nox_verdict = nox_result["verdict"] if nox_result else "NOT_RUN"
        nox_ctx = nox_result["reviewer_context_id"] if nox_result else "N/A"
        lines = [
            f"## KIRION FORGE — {mode_header}",
            "",
            "### START / CLOSE Receipt",
            f"- **Mission ID:** `{packet['mission_id']}` (Run `{packet['run_id']}`)",
            f"- **Authenticated GitHub Broker Actor:** `{EXPECTED_BROKER_LOGIN}` (`id: {EXPECTED_BROKER_USER_ID}`)",
            f"- **Logical Writer Persona:** `{packet['assigned_persona']}` (`{packet['formal_role']}`)",
            f"- **Repository & Permitted Branch:** `{packet['repo_name']}` @ `{packet['permitted_branch']}`",
            f"- **Frozen Base SHA:** `{packet['base_sha']}`",
            f"- **Exact Candidate SHA:** `{candidate_sha}`",
            f"- **Risk Class:** `{packet['risk_class']}`",
            f"- **Gate Suite Status:** `{gate_summary.get('overall_status', 'UNKNOWN')}` (Passed: `{gate_summary.get('passed_gates', [])}`)",
            f"- **Fresh-Context Antigravity-Nox Review (`G13`):** `{nox_verdict}` (`context_id: {nox_ctx}`)",
            f"- **Changed Files ({len(changed_files)}):** `{changed_files}`",
            "- **Authority Return:** Candidate submitted for separate non-author review and Engineer acceptance. No self-promotion or auto-merge.",
        ]
        return redact_secrets("\n".join(lines))

    def prepare_and_record_delivery(
        self,
        *,
        packet: dict[str, Any],
        candidate_sha: str,
        changed_files: list[str],
        gate_summary: dict[str, Any],
        nox_result: dict[str, Any] | None,
        has_symlinks: bool = False,
        allow_blocked_diagnostic_draft: bool = False,
        remote_executor: Callable[[str, str, str], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Verify actor, mission authority, branch policy, path ownership, symlink absence, gate results,
        and exact-SHA Nox review before recording an idempotent delivery receipt.
        """
        verify_mission_packet(packet)
        assert_operation_allowed(packet, "DELIVER_DRAFT_PR", actor_persona="Antigravity-Maintainer")
        actor = self.verify_actor_identity()

        if not SHA40_RE.fullmatch(candidate_sha):
            raise DeliveryBrokerError(f"Invalid 40-char candidate_sha: {candidate_sha!r}")

        branch = packet["permitted_branch"]
        if branch in PROHIBITED_BRANCH_NAMES or branch.startswith("refs/heads/main"):
            raise DeliveryBrokerError(f"Delivery to protected branch {branch!r} is prohibited.")

        if has_symlinks:
            raise DeliveryBrokerError("Candidate contains symlinks; rejected by Nairu delivery broker.")

        if not changed_files:
            raise DeliveryBrokerError("Candidate has zero changed files to deliver.")

        # Verify every changed file is within packet owned_paths and not protected governance
        for f in changed_files:
            norm = f.replace("\\", "/").strip()
            if norm in PROTECTED_GOVERNANCE_PATHS:
                raise DeliveryBrokerError(f"Delivery rejected: protected governance file modified ({norm}).")
        assert_paths_within_ownership(
            {**packet, "allowed_operations": list(set(packet["allowed_operations"]) | {"WRITE_OWNED"})},
            changed_files,
        )

        delivery_key = compute_delivery_key(packet["mission_id"], branch, candidate_sha)
        conn = self._connect()
        try:
            existing = conn.execute("SELECT * FROM delivery_receipts WHERE delivery_key = ?", (delivery_key,)).fetchone()
            if existing is not None and existing["status"] == "DELIVERED":
                result = dict(existing)
                result["idempotent_replay"] = True
                return result
        finally:
            conn.close()

        is_blocked_diag = False
        if gate_summary.get("overall_status") != "PASS":
            if not allow_blocked_diagnostic_draft:
                raise DeliveryBrokerError(
                    f"Required quality gates not satisfied ({gate_summary.get('overall_status')}); "
                    "cannot deliver validated candidate."
                )
            is_blocked_diag = True

        if not is_blocked_diag:
            if nox_result is None:
                raise DeliveryBrokerError("Missing fresh-context Antigravity-Nox review (G13) for validated candidate.")
            NoxReviewEngine().assert_review_valid_for_sha(nox_result, candidate_sha)

        receipt_md = self.format_start_close_receipt(
            packet=packet,
            candidate_sha=candidate_sha,
            changed_files=changed_files,
            nox_result=nox_result,
            gate_summary=gate_summary,
            is_blocked_diagnostic=is_blocked_diag,
        )
        pr_mode = "BLOCKED_DIAGNOSTIC_DRAFT" if is_blocked_diag else "VALIDATED_DRAFT_PR"
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        # Pre-write INTENT before calling remote executor for crash recovery
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_receipts (
                    delivery_key, mission_id, branch, base_sha, candidate_sha,
                    actor_login, actor_id, status, pr_mode, receipt_markdown, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING_REMOTE', ?, ?, ?)
                """,
                (
                    delivery_key,
                    packet["mission_id"],
                    branch,
                    packet["base_sha"],
                    candidate_sha,
                    actor["login"],
                    actor["id"],
                    pr_mode,
                    receipt_md,
                    now,
                ),
            )
            conn.execute("COMMIT;")
        finally:
            conn.close()

        if remote_executor is not None:
            remote_executor(branch, candidate_sha, receipt_md)

        now_done = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                "UPDATE delivery_receipts SET status = 'DELIVERED', updated_at_utc = ? WHERE delivery_key = ?",
                (now_done, delivery_key),
            )
            row = conn.execute("SELECT * FROM delivery_receipts WHERE delivery_key = ?", (delivery_key,)).fetchone()
            conn.execute("COMMIT;")
            out = dict(row)
            out["idempotent_replay"] = False
            return out
        finally:
            conn.close()
