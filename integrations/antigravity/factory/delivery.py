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
from .authority import is_valid_git_sha, verify_mission_packet
from .evidence import redact_secrets
from .ownership import parse_git_raw_z_diff
from .policy import (
    PolicyViolationError,
    assert_operation_allowed,
    assert_paths_within_ownership,
    is_prohibited_branch,
    is_protected_governance_path,
    normalize_rel_path,
)
from .quality import (
    GATE_CATALOG,
    MANDATORY_NON_EXEMPTIBLE_GATES,
    RISK_REQUIRED_GATES,
    NoxReviewEngine,
)


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
    """Narrow remote write broker enforcing Kirch-Nairu actor verification, diff scope, and atomic idempotent draft PR receipts."""

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

    def _validate_gate_summary(self, packet: dict[str, Any], candidate_sha: str, gate_summary: dict[str, Any]) -> None:
        if not is_valid_git_sha(candidate_sha):
            raise DeliveryBrokerError(f"Invalid or all-zero candidate_sha forbidden: {candidate_sha!r}")
        if gate_summary.get("overall_status") != "PASS":
            raise DeliveryBrokerError(
                f"Required quality gates not satisfied ({gate_summary.get('overall_status')}); "
                "cannot deliver validated candidate."
            )
        if gate_summary.get("candidate_sha") != candidate_sha:
            raise DeliveryBrokerError(
                f"Gate summary SHA mismatch: summary={gate_summary.get('candidate_sha')!r} != candidate={candidate_sha!r}"
            )
        if gate_summary.get("risk_class") != packet["risk_class"]:
            raise DeliveryBrokerError(
                f"Gate summary risk_class mismatch: summary={gate_summary.get('risk_class')!r} != packet={packet['risk_class']!r}"
            )
        for bad_key in ("failed_gates", "missing_gates", "not_run_gates"):
            if gate_summary.get(bad_key):
                raise DeliveryBrokerError(
                    f"Gate summary reports non-empty {bad_key}={gate_summary.get(bad_key)!r}; delivery denied."
                )

        passed_gates = gate_summary.get("passed_gates")
        if not isinstance(passed_gates, list) or not all(isinstance(g, str) and g in GATE_CATALOG for g in passed_gates):
            raise DeliveryBrokerError(f"Gate summary passed_gates must be a list of valid gate IDs, got {passed_gates!r}")

        raw_na = gate_summary.get("documented_non_applicable")
        if raw_na is None:
            na_map: dict[str, str] = {}
        elif isinstance(raw_na, dict):
            na_map = raw_na
        else:
            raise DeliveryBrokerError("Gate summary documented_non_applicable must be a mapping of gate_id -> justification.")

        packet_req = set(packet["required_gates"])
        packet_na = packet.get("non_applicable_gates") or {}

        for gid, reason in na_map.items():
            if gid not in GATE_CATALOG:
                raise DeliveryBrokerError(f"Unknown gate ID in documented_non_applicable: {gid!r}")
            if gid in MANDATORY_NON_EXEMPTIBLE_GATES:
                raise DeliveryBrokerError(
                    f"Mandatory anchor gate {gid} cannot be exempted via documented_non_applicable; delivery denied."
                )
            if not isinstance(reason, str) or not reason.strip():
                raise DeliveryBrokerError(
                    f"Non-applicable gate {gid} requires a non-empty justification string; delivery denied."
                )
            if gid in packet_req:
                raise DeliveryBrokerError(
                    f"Gate {gid} is required by MissionPacket.required_gates and cannot be exempted post-hoc; delivery denied."
                )
            if gid not in packet_na:
                raise DeliveryBrokerError(
                    f"Gate {gid} in documented_non_applicable was not pre-authorized in MissionPacket.non_applicable_gates; delivery denied."
                )

        passed_set = set(passed_gates)
        missing_mandatory = sorted(MANDATORY_NON_EXEMPTIBLE_GATES - passed_set)
        if missing_mandatory:
            raise DeliveryBrokerError(
                f"Mandatory anchor gates {missing_mandatory} must appear in passed_gates; delivery denied."
            )

        missing_packet_req = sorted(packet_req - passed_set)
        if missing_packet_req:
            raise DeliveryBrokerError(
                f"Gate summary missing passed results for MissionPacket.required_gates {missing_packet_req}; delivery denied."
            )

        required_all = set(RISK_REQUIRED_GATES[packet["risk_class"]]) | packet_req
        passed_or_pre_na = passed_set | (set(na_map.keys()) & set(packet_na.keys()))
        missing_required = sorted(required_all - passed_or_pre_na)
        if missing_required:
            raise DeliveryBrokerError(
                f"Gate summary missing required gates {missing_required} for {packet['risk_class']}; delivery denied."
            )

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
        repo_root: Path | None = None,
    ) -> dict[str, Any]:
        """
        Verify actor, mission authority, branch policy, Git ancestry/diff (when repo_root is supplied),
        path ownership, symlink/gitlink absence, gate results, and exact-SHA Nox review before atomically
        reserving and recording an idempotent delivery receipt.
        """
        verify_mission_packet(packet)
        assert_operation_allowed(packet, "DELIVER_DRAFT_PR", actor_persona="Antigravity-Maintainer")
        actor = self.verify_actor_identity()

        if not is_valid_git_sha(candidate_sha):
            raise DeliveryBrokerError(f"Invalid or all-zero 40-char candidate_sha: {candidate_sha!r}")

        branch = packet["permitted_branch"]
        if is_prohibited_branch(branch):
            raise DeliveryBrokerError(f"Delivery to protected/invalid branch {branch!r} is prohibited.")

        if has_symlinks:
            raise DeliveryBrokerError("Candidate contains symlinks; rejected by Nairu delivery broker.")

        effective_changed_files = list(changed_files)
        if repo_root is not None:
            anc = subprocess.run(
                ["git", "merge-base", "--is-ancestor", packet["base_sha"], candidate_sha],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if anc.returncode != 0:
                raise DeliveryBrokerError(
                    f"History integrity check failed: candidate_sha={candidate_sha} does not descend from base_sha={packet['base_sha']}."
                )
            diff_p = subprocess.run(
                ["git", "-c", "core.quotepath=false", "diff", "--no-renames", "--raw", "-z", packet["base_sha"], candidate_sha],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if diff_p.returncode != 0:
                raise DeliveryBrokerError(
                    f"Failed to inspect git diff {packet['base_sha']}..{candidate_sha}: {redact_secrets(diff_p.stderr.strip())}"
                )
            git_paths, forbidden_modes = parse_git_raw_z_diff(diff_p.stdout)
            if forbidden_modes:
                raise DeliveryBrokerError(
                    f"Candidate commit contains forbidden symlink (120000) or gitlink (160000) entries: {forbidden_modes}"
                )
            effective_changed_files = sorted(set(git_paths))
            if changed_files:
                caller_norm = {normalize_rel_path(p) for p in changed_files}
                actual_norm = {normalize_rel_path(p) for p in effective_changed_files}
                omitted = sorted(actual_norm - caller_norm)
                if omitted:
                    raise DeliveryBrokerError(
                        f"Caller-supplied changed_files omitted actual git diff paths: {omitted}"
                    )

        if not effective_changed_files:
            raise DeliveryBrokerError("Candidate has zero changed files to deliver.")

        packet_ops = set(packet.get("allowed_operations", []))
        formal_role = packet.get("formal_role")
        if formal_role == "Code Writer" and "WRITE_OWNED" not in packet_ops:
            raise DeliveryBrokerError(
                "Code Writer MissionPacket must authorize WRITE_OWNED in allowed_operations to deliver changed files."
            )
        if formal_role == "Integration Writer" and not (packet_ops & {"WRITE_OWNED", "INTEGRATE_BRANCH"}):
            raise DeliveryBrokerError(
                "Integration Writer MissionPacket must authorize WRITE_OWNED or INTEGRATE_BRANCH to deliver changed files."
            )

        for f in effective_changed_files:
            if is_protected_governance_path(f):
                raise DeliveryBrokerError(f"Delivery rejected: protected governance file modified ({f}).")
        assert_paths_within_ownership(packet, effective_changed_files, require_write_operation=False)

        is_blocked_diag = False
        if gate_summary.get("overall_status") != "PASS":
            if not allow_blocked_diagnostic_draft:
                raise DeliveryBrokerError(
                    f"Required quality gates not satisfied ({gate_summary.get('overall_status')}); "
                    "cannot deliver validated candidate."
                )
            is_blocked_diag = True

        if not is_blocked_diag:
            self._validate_gate_summary(packet, candidate_sha, gate_summary)
            if nox_result is None:
                raise DeliveryBrokerError("Missing fresh-context Antigravity-Nox review (G13) for validated candidate.")
            NoxReviewEngine().assert_review_valid_for_sha(
                nox_result,
                candidate_sha,
                expected_mission_id=packet["mission_id"],
            )

        delivery_key = compute_delivery_key(packet["mission_id"], branch, candidate_sha)
        receipt_md = self.format_start_close_receipt(
            packet=packet,
            candidate_sha=candidate_sha,
            changed_files=effective_changed_files,
            nox_result=nox_result,
            gate_summary=gate_summary,
            is_blocked_diagnostic=is_blocked_diag,
        )
        pr_mode = "BLOCKED_DIAGNOSTIC_DRAFT" if is_blocked_diag else "VALIDATED_DRAFT_PR"
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        # Single atomic BEGIN IMMEDIATE check + PENDING_REMOTE reservation (no TOCTOU race, no INSERT OR REPLACE)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            existing = conn.execute("SELECT * FROM delivery_receipts WHERE delivery_key = ?", (delivery_key,)).fetchone()
            if existing is not None:
                if existing["status"] == "DELIVERED":
                    if existing["pr_mode"] == pr_mode:
                        conn.execute("ROLLBACK;")
                        result = dict(existing)
                        result["idempotent_replay"] = True
                        return result
                    if existing["pr_mode"] == "BLOCKED_DIAGNOSTIC_DRAFT" and pr_mode == "VALIDATED_DRAFT_PR":
                        cur = conn.execute(
                            """
                            UPDATE delivery_receipts
                            SET status = 'PENDING_REMOTE', pr_mode = ?, receipt_markdown = ?, updated_at_utc = ?
                            WHERE delivery_key = ? AND status = 'DELIVERED' AND pr_mode = 'BLOCKED_DIAGNOSTIC_DRAFT'
                            """,
                            (pr_mode, receipt_md, now, delivery_key),
                        )
                        if cur.rowcount != 1:
                            conn.execute("ROLLBACK;")
                            raise DeliveryBrokerError(f"Concurrent upgrade conflict for {delivery_key}")
                    else:
                        conn.execute("ROLLBACK;")
                        raise DeliveryBrokerError(
                            f"Cannot overwrite DELIVERED {existing['pr_mode']} receipt with {pr_mode} for {delivery_key}"
                        )
                elif existing["status"] == "PENDING_REMOTE":
                    conn.execute("ROLLBACK;")
                    raise DeliveryBrokerError(
                        f"Uncertain PENDING_REMOTE delivery exists for delivery_key={delivery_key}; "
                        "run RecoveryManager.reconcile_interrupted_mission() read-only before retrying."
                    )
                elif existing["status"] == "RECONCILED_RETRY_ALLOWED":
                    cur = conn.execute(
                        """
                        UPDATE delivery_receipts
                        SET status = 'PENDING_REMOTE', pr_mode = ?, receipt_markdown = ?, updated_at_utc = ?
                        WHERE delivery_key = ? AND status = 'RECONCILED_RETRY_ALLOWED'
                        """,
                        (pr_mode, receipt_md, now, delivery_key),
                    )
                    if cur.rowcount != 1:
                        conn.execute("ROLLBACK;")
                        raise DeliveryBrokerError(f"Concurrent delivery reservation conflict for {delivery_key}")
                else:
                    conn.execute("ROLLBACK;")
                    raise DeliveryBrokerError(f"Unexpected delivery_receipts status {existing['status']!r} for {delivery_key}")
            else:
                conn.execute(
                    """
                    INSERT INTO delivery_receipts (
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
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

        if remote_executor is not None:
            remote_executor(branch, candidate_sha, receipt_md)

        now_done = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                "UPDATE delivery_receipts SET status = 'DELIVERED', updated_at_utc = ? WHERE delivery_key = ? AND status = 'PENDING_REMOTE'",
                (now_done, delivery_key),
            )
            row = conn.execute("SELECT * FROM delivery_receipts WHERE delivery_key = ?", (delivery_key,)).fetchone()
            conn.execute("COMMIT;")
            out = dict(row)
            out["idempotent_replay"] = False
            return out
        finally:
            conn.close()
