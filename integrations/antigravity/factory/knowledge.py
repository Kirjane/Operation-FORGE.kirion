"""F14 — Knowledge management, Forge/Second Brain Crosswalk translation, instrumented metrics, and lesson proposals."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from .authority import MISSION_ID_RE, AuthorityError, is_valid_git_sha
from .evidence import FORGE_LEVEL_TO_CERTAINTY_CEILING, translate_harness_capabilities_to_forge


class KnowledgeManager:
    """Manages canonical evidence/lesson mapping and emits review-only skill/test proposals without self-modifying policy."""

    def __init__(self, knowledge_dir: Path) -> None:
        self.knowledge_dir = knowledge_dir.resolve()
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self._instrumented_runs: list[dict[str, Any]] = []

    def build_crosswalk_record(
        self,
        *,
        mission_id: str,
        run_id: str,
        context_sha256: str,
        candidate_sha: str,
        harness_capabilities: set[str],
        has_automated_provenance: bool,
        is_stale: bool = False,
    ) -> dict[str, Any]:
        """Translate evidence between Second Brain harness capabilities, Forge E-levels, and Brain certainty states."""
        has_durable = is_valid_git_sha(candidate_sha)
        translated = translate_harness_capabilities_to_forge(
            harness_capabilities,
            has_automated_provenance=has_automated_provenance,
            has_durable_sha=has_durable,
        )
        certainty = "STALE" if is_stale else translated["certainty_ceiling"]

        # Normative rule: E5 runtime acceptance never reaches OBSERVED_IN_OPERATION (E6)
        if translated["evidence_level"] == "E5" and certainty == "OBSERVED_IN_OPERATION":
            raise AuthorityError("Crosswalk violation: E5 cannot be elevated to OBSERVED_IN_OPERATION.")

        return {
            "mission_id": mission_id,
            "run_id": run_id,
            "context_sha256": context_sha256,
            "candidate_sha": candidate_sha,
            "harness_capabilities": sorted(harness_capabilities),
            "forge_evidence_level": translated["evidence_level"],
            "forge_evidence_type": translated["evidence_type"],
            "forge_provenance": translated["provenance"],
            "brain_certainty_state": certainty,
            "certainty_ceiling": FORGE_LEVEL_TO_CERTAINTY_CEILING[translated["evidence_level"]],
        }

    def propose_skill_or_test_lesson(
        self,
        *,
        mission_id: str,
        observed_sha: str,
        failure_signature: str,
        root_cause: str,
        target_skill_name: str,
        proposed_guidance: str,
        discriminating_test_name: str,
    ) -> dict[str, Any]:
        """
        Emit a review-only lesson proposal file in `proposals/` without mutating `.agents/skills/`
        or `plugins/kirion-forge/skills/` in place.
        """
        if not isinstance(mission_id, str) or not MISSION_ID_RE.fullmatch(mission_id):
            raise AuthorityError(f"Invalid mission_id for lesson proposal: {mission_id!r}")
        if not is_valid_git_sha(observed_sha):
            raise AuthorityError(f"Lesson proposal requires valid non-zero 40-char observed_sha, got {observed_sha!r}")

        proposal_id = f"LESSON-{mission_id}-{hashlib.sha256(failure_signature.encode('utf-8')).hexdigest()[:8]}"
        proposals_dir = (self.knowledge_dir / "proposals").resolve()
        proposals_dir.mkdir(parents=True, exist_ok=True)
        proposal_path = (proposals_dir / f"{proposal_id}.json").resolve()
        try:
            proposal_path.relative_to(proposals_dir)
        except ValueError as exc:
            raise AuthorityError(f"Proposal path escapes proposals directory: {proposal_path}") from exc

        payload = {
            "proposal_id": proposal_id,
            "status": "PROPOSED_REVIEW_ONLY_NOT_ADOPTED",
            "auto_policy_elevation": False,
            "mission_id": mission_id,
            "observed_sha": observed_sha,
            "failure_signature": failure_signature,
            "root_cause": root_cause,
            "target_skill_name": target_skill_name,
            "proposed_guidance": proposed_guidance,
            "discriminating_test_name": discriminating_test_name,
            "created_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        proposal_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {**payload, "proposal_path": str(proposal_path)}

    def record_instrumented_run(
        self,
        *,
        run_id: str,
        mission_id: str,
        first_pass_valid: bool,
        repair_cycles: int,
        escaped_defects: int,
        human_interventions: int,
        lead_time_seconds: float,
        recovered_from_interruption: bool,
        evidence_hashes_valid: bool,
    ) -> None:
        self._instrumented_runs.append(
            {
                "run_id": run_id,
                "mission_id": mission_id,
                "first_pass_valid": first_pass_valid,
                "repair_cycles": repair_cycles,
                "escaped_defects": escaped_defects,
                "human_interventions": human_interventions,
                "lead_time_seconds": lead_time_seconds,
                "recovered_from_interruption": recovered_from_interruption,
                "evidence_hashes_valid": evidence_hashes_valid,
            }
        )

    def summarize_metrics(self) -> dict[str, Any]:
        """Compute factory operational metrics strictly from instrumented runs (never LOC/commit count)."""
        total = len(self._instrumented_runs)
        if total == 0:
            return {"instrumented_runs": 0}
        first_pass = sum(1 for r in self._instrumented_runs if r["first_pass_valid"])
        total_repairs = sum(r["repair_cycles"] for r in self._instrumented_runs)
        total_escaped = sum(r["escaped_defects"] for r in self._instrumented_runs)
        total_interventions = sum(r["human_interventions"] for r in self._instrumented_runs)
        valid_evidence = sum(1 for r in self._instrumented_runs if r["evidence_hashes_valid"])
        latencies = sorted(r["lead_time_seconds"] for r in self._instrumented_runs)
        median_lead = latencies[total // 2]
        return {
            "instrumented_runs": total,
            "first_pass_validation_rate": round(first_pass / total, 4),
            "total_repair_cycles": total_repairs,
            "escaped_defects": total_escaped,
            "human_interventions": total_interventions,
            "median_lead_time_seconds": round(median_lead, 4),
            "evidence_integrity_rate": round(valid_evidence / total, 4),
        }
