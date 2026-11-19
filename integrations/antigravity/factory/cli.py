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
        choices=["verify-plugin", "status", "test"],
        help="Factory command to execute",
    )
    args = parser.parse_args(argv)
    if args.command == "verify-plugin":
        return cmd_verify_plugin()
    if args.command == "status":
        return cmd_status()
    if args.command == "test":
        return cmd_test()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
