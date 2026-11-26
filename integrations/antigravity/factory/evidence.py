"""F10 — Trusted command runner, secret redaction, content-addressed artifact store, and Evidence Crosswalk."""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .authority import AuthorityError, is_valid_git_sha, validate_contract
from .ownership import sanitize_worker_env

VALID_COMMAND_EVIDENCE_TYPES = {"SOURCE", "UNIT", "INTEGRATION", "BUILD", "RUNTIME", "SECURITY"}

SECRET_REDACTION_PATTERNS = [
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{8,})\b"),
    re.compile(r"\b(github_pat_[A-Za-z0-9_]{8,})\b"),
    re.compile(r"(Bearer\s+)[\"']?[A-Za-z0-9._\-]{8,}[\"']?", re.IGNORECASE),
    re.compile(r"[\"']?x-codeium-csrf-token[\"']?\s*[:=]\s*[\"']?[^\s;&\"',}\]]+[\"']?", re.IGNORECASE),
    re.compile(r"[\"']?ANTIGRAVITY_CSRF_TOKEN[\"']?\s*[:=]\s*[\"']?[^\s;&\"',}\]]+[\"']?", re.IGNORECASE),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,})\b"),
    re.compile(r"[\"']?password[\"']?\s*[:=]\s*[\"']?[^\s;&\"',}\]]+[\"']?", re.IGNORECASE),
]

FORGE_LEVEL_TO_CERTAINTY_CEILING: dict[str, str] = {
    "E0": "HYPOTHESIS",
    "E1": "SUPPORTED",
    "E2": "SUPPORTED",
    "E3": "VERIFIED",
    "E4": "VERIFIED",
    "E5": "VERIFIED",
    "E6": "OBSERVED_IN_OPERATION",
    "E7": "PRODUCTION_PROVEN",
}


def redact_secrets(text: str) -> str:
    out = text
    for pat in SECRET_REDACTION_PATTERNS:
        out = pat.sub("[REDACTED_SECRET]", out)
    return out


def translate_harness_capabilities_to_forge(
    capabilities: set[str],
    *,
    has_automated_provenance: bool,
    has_durable_sha: bool,
) -> dict[str, str]:
    """Normative translation per EVIDENCE_CROSSWALK.md."""
    if not capabilities or capabilities == {"DEPLOYED"} or "INTENDED" in capabilities:
        level, ev_type, prov = "E0", "NONE", "ASSUMED"
    elif "OBSERVED" in capabilities and "DEPLOYED" in capabilities:
        level, ev_type, prov = "E6", "RUNTIME", "DIRECTLY_OBSERVED"
    elif "OBSERVED" in capabilities:
        level, ev_type, prov = "E5", "RUNTIME", "DIRECTLY_OBSERVED"
    elif "TESTED" in capabilities:
        if has_automated_provenance:
            level, ev_type, prov = "E4", "INTEGRATION", "AUTOMATED"
        else:
            level, ev_type, prov = "E2", "UNIT", "REPORTED"
    elif "IMPLEMENTED" in capabilities:
        level, ev_type, prov = "E1", "SOURCE", "DIRECTLY_OBSERVED"
    else:
        level, ev_type, prov = "E0", "NONE", "ASSUMED"

    # Crosswalk Rule: DURABLE (exact SHA binding) is a precondition on E4+
    if level in ("E4", "E5", "E6", "E7") and not has_durable_sha:
        level = "E2"
        prov = "REPORTED"

    if "VERIFIED" in capabilities and level not in ("E0", "E2"):
        prov = "REPRODUCED"

    return {
        "evidence_level": level,
        "evidence_type": ev_type,
        "provenance": prov,
        "certainty_ceiling": FORGE_LEVEL_TO_CERTAINTY_CEILING[level],
    }


class TrustedEvidenceRunner:
    """Executes validation commands in a sanitized environment and emits hash-addressed EvidenceEnvelopes."""

    def __init__(self, artifact_store_root: Path, environment_versions: dict[str, str] | None = None) -> None:
        self.artifact_store_root = artifact_store_root.resolve()
        self.artifact_store_root.mkdir(parents=True, exist_ok=True)
        self.environment_versions = environment_versions or {"python": "3.13.5", "dotnet": "10.0.401", "php": "8.4.25"}

    def _read_git_state(self, cwd: Path) -> tuple[str, str, bool]:
        head_p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True)
        tree_p = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=cwd, capture_output=True, text=True)
        status_p = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True)
        head_sha = head_p.stdout.strip() if head_p.returncode == 0 and len(head_p.stdout.strip()) == 40 else "0" * 40
        tree_sha = tree_p.stdout.strip() if tree_p.returncode == 0 and len(tree_p.stdout.strip()) == 40 else "0" * 40
        dirty = bool(status_p.stdout.strip()) if status_p.returncode == 0 else True
        return head_sha, tree_sha, dirty

    def _store_artifact(self, content: str) -> tuple[Path, int, str]:
        redacted = redact_secrets(content)
        raw_bytes = redacted.encode("utf-8")
        digest = hashlib.sha256(raw_bytes).hexdigest()
        bucket = self.artifact_store_root / digest[:2]
        bucket.mkdir(parents=True, exist_ok=True)
        if bucket.is_symlink() or bucket.resolve(strict=True) != bucket:
            raise AuthorityError("ARTIFACT_BUCKET_UNSAFE")
        blob_path = bucket / f"{digest}.log"
        # Content-addressed objects are immutable. Never follow or overwrite
        # a preexisting symlink, hardlink or different byte sequence.
        try:
            with blob_path.open("xb") as stream:
                stream.write(raw_bytes)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            pass
        if (blob_path.is_symlink() or blob_path.resolve(strict=True) != blob_path or
                not blob_path.is_file() or blob_path.stat().st_nlink != 1):
            raise AuthorityError("ARTIFACT_PATH_UNSAFE")
        with blob_path.open("rb") as stream:
            stored = stream.read(len(raw_bytes) + 1)
        if stored != raw_bytes:
            raise AuthorityError("ARTIFACT_CONTENT_MISMATCH")
        return blob_path, len(raw_bytes), digest

    def capture_fixture_oracle_artifact(self, *, binding, observe_positive, observe_negative):
        """Capture structured outcomes from two trusted fixture probes.

        Only trusted test composition may supply the probes or binding. This
        does not execute a mission-provided command, authenticate a host or
        qualify a real product. Persist the exact redacted observation bytes
        through the existing evidence store.
        """
        from copy import deepcopy
        from .mission_contract import canonical_json
        if type(binding) is not dict or {"observed", "negative_observed"} & set(binding):
            raise AuthorityError("FIXTURE_OBSERVATION_BINDING_INVALID")
        captured_binding = deepcopy(binding)
        positive = deepcopy(observe_positive())
        negative = deepcopy(observe_negative())
        if type(positive) is not dict or type(negative) is not dict:
            raise AuthorityError("FIXTURE_OBSERVATION_SHAPE_INVALID")
        return self._store_artifact(canonical_json({
            **captured_binding, "observed": positive, "negative_observed": negative}))

    def run_gate_command(
        self,
        *,
        run_id: str,
        mission_id: str,
        stage: str,
        gate_id: str,
        command_argv: list[str],
        cwd: Path,
        evidence_type: str = "INTEGRATION",
        is_runtime_gate: bool = False,
        fixture_sha256: str = "0" * 64,
        timeout_seconds: float = 120.0,
    ) -> dict[str, Any]:
        if not command_argv:
            raise AuthorityError("command_argv cannot be empty.")
        if evidence_type not in VALID_COMMAND_EVIDENCE_TYPES:
            raise AuthorityError(
                f"Invalid evidence_type={evidence_type!r} for executed gate command; "
                f"expected one of {sorted(VALID_COMMAND_EVIDENCE_TYPES)}."
            )

        pre_sha, pre_tree, pre_dirty = self._read_git_state(cwd)
        started = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        try:
            proc = subprocess.run(
                command_argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=sanitize_worker_env(),
            )
            exit_code: int | None = proc.returncode
            status = "PASS" if exit_code == 0 else "FAIL"
            combined_output = f"COMMAND: {' '.join(command_argv)}\nEXIT_CODE: {exit_code}\n--- STDOUT ---\n{proc.stdout}\n--- STDERR ---\n{proc.stderr}\n"
        except FileNotFoundError as exc:
            exit_code = None
            status = "NOT_RUN"
            combined_output = f"COMMAND: {' '.join(command_argv)}\nNOT_RUN: executable not found ({exc})\n"
        except subprocess.TimeoutExpired as exc:
            exit_code = None
            status = "FAIL"
            combined_output = f"COMMAND: {' '.join(command_argv)}\nTIMEOUT after {timeout_seconds}s: {exc}\n"

        post_sha, post_tree, post_dirty = self._read_git_state(cwd)
        drifted = (post_sha != pre_sha) or (post_tree != pre_tree)
        dirty = pre_dirty or post_dirty or drifted
        candidate_sha = post_sha if is_valid_git_sha(post_sha) else pre_sha
        tree_sha = post_tree if is_valid_git_sha(post_tree) else pre_tree

        completed = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        blob_path, size_bytes, digest = self._store_artifact(combined_output)

        # Prevent E4 build from being claimed as E5 runtime; permit G08 SECURITY runtime gates;
        # map SOURCE to E1/DIRECTLY_OBSERVED; downgrade dirty/drifted/unanchored PASS; keep NOT_RUN at E0/NONE/ASSUMED.
        recorded_evidence_type = evidence_type
        unanchored = (not is_valid_git_sha(candidate_sha)) or (not is_valid_git_sha(tree_sha)) or dirty
        if status == "PASS":
            if evidence_type == "SOURCE":
                ev_level = "E1"
                prov = "REPORTED" if unanchored else "DIRECTLY_OBSERVED"
            else:
                if is_runtime_gate and (evidence_type == "RUNTIME" or (gate_id == "G08" and evidence_type == "SECURITY")):
                    ev_level = "E5"
                    prov = "DIRECTLY_OBSERVED"
                else:
                    ev_level = "E4"
                    prov = "AUTOMATED"
                if unanchored:
                    ev_level = "E2"
                    prov = "REPORTED"
        elif status == "NOT_RUN":
            ev_level = "E0"
            recorded_evidence_type = "NONE"
            prov = "ASSUMED"
        else:
            ev_level = "E1"
            prov = "DIRECTLY_OBSERVED"

        envelope = {
            "schema_version": 1,
            "run_id": run_id,
            "mission_id": mission_id,
            "stage": stage,
            "gate_id": gate_id,
            "candidate_sha": candidate_sha,
            "tree_sha": tree_sha,
            "dirty": dirty,
            "command_argv": command_argv,
            "cwd": str(cwd),
            "started_at_utc": started,
            "completed_at_utc": completed,
            "exit_code": exit_code,
            "status": status,
            "environment_versions": dict(self.environment_versions),
            "fixture_sha256": fixture_sha256,
            "artifact_path": str(blob_path),
            "artifact_size_bytes": size_bytes,
            "artifact_sha256": digest,
            "evidence_level": ev_level,
            "evidence_type": recorded_evidence_type,
            "provenance": prov,
            "certainty_ceiling": FORGE_LEVEL_TO_CERTAINTY_CEILING[ev_level],
            "redacted": True,
        }
        validate_contract(envelope, "evidence-envelope.schema.json")
        return envelope


MAX_ASSURANCE_ARTIFACT_BYTES = 8 * 1024 * 1024


def read_assurance_artifact(root: Path, envelope: dict[str, Any]) -> bytes:
    """Read exact redacted bytes from the existing content-addressed store.

    The store root is trusted composition, never receipt ingress. This is local
    fixture custody, not an OS boundary against concurrent privileged writers.
    """
    digest = envelope["artifact_sha256"]
    size = envelope["artifact_size_bytes"]
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or not 0 < size <= MAX_ASSURANCE_ARTIFACT_BYTES:
        raise AuthorityError("ARTIFACT_IDENTITY_INVALID")
    root = root.resolve(strict=True)
    expected = root / digest[:2] / (digest + ".log")
    if envelope["artifact_path"] != str(expected):
        raise AuthorityError("ARTIFACT_PATH_MISMATCH")
    if (expected.parent.is_symlink() or expected.is_symlink() or
            expected.resolve(strict=True) != expected or not expected.is_file() or
            expected.stat().st_nlink != 1):
        raise AuthorityError("ARTIFACT_PATH_UNSAFE")
    with expected.open("rb") as stream:
        raw = stream.read(MAX_ASSURANCE_ARTIFACT_BYTES + 1)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise AuthorityError("ARTIFACT_CONTENT_MISMATCH")
    return raw
