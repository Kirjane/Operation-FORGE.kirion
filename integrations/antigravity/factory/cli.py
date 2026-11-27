"""CLI entrypoint for KIRION Forge Antigravity Software Factory verification and orchestration."""
from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path

from . import ANTIGRAVITY_ROOT, FACTORY_VERSION, PROGRAM_ID, REPO_ROOT
from .authority import verify_git_authority
from .delivery import probe_live_github_actor
from .dispatcher import query_live_host_plugin_discovery, verify_plugin_package


def cmd_verify_plugin() -> int:
    pkg = verify_plugin_package()
    live = query_live_host_plugin_discovery()
    print(json.dumps({"factory_version": FACTORY_VERSION, "package": pkg, "live_host_discovery": live}, indent=2))
    return 0


def cmd_status() -> int:
    git_state = verify_git_authority(REPO_ROOT)
    pkg = verify_plugin_package()
    try:
        actor = probe_live_github_actor()
    except Exception as exc:
        actor = {"status": "UNVERIFIED", "error": str(exc)}
    backlog = json.loads((ANTIGRAVITY_ROOT / "BACKLOG.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "program": PROGRAM_ID,
                "factory_version": FACTORY_VERSION,
                "backlog_status": backlog.get("status"),
                "git": git_state,
                "broker_actor": actor,
                "plugin": pkg,
            },
            indent=2,
        )
    )
    return 0


def cmd_test() -> int:
    tests_dir = ANTIGRAVITY_ROOT / "tests"
    suite = unittest.defaultTestLoader.discover(str(tests_dir), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KIRION Forge Antigravity Software Factory CLI")
    parser.add_argument(
        "command",
        choices=["verify-plugin", "status", "test", "supervised-handoff", "inspect-candidate", "commands", "resolve-command"],
        help="Factory command to execute",
    )
    parser.add_argument("--journal", type=Path, help="Read-only contract journal projection for status")
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--context-config", type=Path)
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--target-root", type=Path)
    parser.add_argument("--candidate-sha")
    parser.add_argument("--workflow", default="feature_delivery")
    parser.add_argument("--alias")
    parser.add_argument("--observed-role")
    parser.add_argument("--observed-stage")
    args = parser.parse_args(argv)
    if args.command in {"commands", "resolve-command"}:
        from .command_registry import describe_commands, propose_command
        if args.command == "commands":
            print(json.dumps(describe_commands(), indent=2))
            return 0
        result = propose_command(args.alias, observed_role=args.observed_role, observed_stage=args.observed_stage)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PROPOSED" else 1
    if args.command in {"supervised-handoff", "inspect-candidate"}:
        from .authority import AuthorityError
        from .mission_contract import parse_mission_packet
        from .skill_registry import PinnedGitSources, SkillRegistry, parse_json
        from .supervised import (FORGE_REPOSITORY_ID, FORGE_REPOSITORY,
                                 supervised_handoff, inspect_supervised_candidate)
        if args.packet is None:
            parser.error("--packet is required")
        try:
            raw = args.packet.read_bytes()
            if args.command == "supervised-handoff":
                if args.context_config is None:
                    parser.error("--context-config is required")
                packet = parse_mission_packet(raw)
                sources = PinnedGitSources({FORGE_REPOSITORY_ID: (FORGE_REPOSITORY, args.source_root)})
                registry = SkillRegistry(sources, repository_id=FORGE_REPOSITORY_ID,
                    repository_name=FORGE_REPOSITORY, registry_commit=packet["selected_skills"]["skill_source_sha"])
                result = supervised_handoff(raw, registry, parse_json(args.context_config.read_bytes()),
                                            workflow=args.workflow)
            else:
                if args.target_root is None or args.candidate_sha is None:
                    parser.error("--target-root and --candidate-sha are required")
                result = inspect_supervised_candidate(raw, target_root=args.target_root, candidate_sha=args.candidate_sha)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except (AuthorityError, OSError, KeyError, TypeError, ValueError) as exc:
            print(json.dumps({"status": "BLOCKED", "reason": str(exc),
                              "native_execution": "UNAVAILABLE", "promotion_authorized": False}))
            return 1
    if args.command == "verify-plugin":
        return cmd_verify_plugin()
    if args.command == "status":
        if args.journal is not None:
            from .operational_state import read_contract_board
            result = read_contract_board(args.journal)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "PROJECTED" else 1
        return cmd_status()
    if args.command == "test":
        return cmd_test()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
