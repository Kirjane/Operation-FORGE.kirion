"""KIRION Forge Autonomous Software Engineering Factory for Antigravity."""
from __future__ import annotations

from pathlib import Path

FACTORY_VERSION = "1.0.0-r1"
PROGRAM_ID = "FORGE-ANTIGRAVITY-SOFTWARE-FACTORY-R1"
EPIC_NUMBER = 13
PR_NUMBER = 14
EXPECTED_BROKER_LOGIN = "Kirch-Nairu"
EXPECTED_BROKER_USER_ID = 291564617

FACTORY_DIR = Path(__file__).resolve().parent
ANTIGRAVITY_ROOT = FACTORY_DIR.parent
REPO_ROOT = ANTIGRAVITY_ROOT.parents[1]
PLUGIN_ROOT = ANTIGRAVITY_ROOT / "plugins" / "kirion-forge"
SCHEMAS_ROOT = ANTIGRAVITY_ROOT / "schemas"
PROFILES_ROOT = ANTIGRAVITY_ROOT / "profiles"
BENCHMARKS_ROOT = ANTIGRAVITY_ROOT / "benchmarks"
WORKFLOWS_ROOT = ANTIGRAVITY_ROOT / "workflows"
