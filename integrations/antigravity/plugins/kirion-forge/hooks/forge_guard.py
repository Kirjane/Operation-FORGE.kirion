#!/usr/bin/env python3
"""Fail-closed PreToolUse and PostToolUse lifecycle guard for the KIRION Forge Antigravity plugin."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FORBIDDEN_COMMAND_PATTERNS = [
    (r"\bgit\s+push\b[^\n]*(\s--force\b|\s-f\b|\s--force-with-lease\b|\s--delete\b)", "Force push or remote ref deletion is prohibited by KIRION Forge policy."),
    (r"\bgit\s+ push\b[^\n]*\b(origin\s+main|origin\s+master)\b", "Direct push to main/master is prohibited by KIRION Forge policy."),
    (r"\bgh\s+pr\s+merge\b", "Autonomous PR merge is prohibited; promotion requires independent Engineer acceptance."),
    (r"\bgh\s+pr\s+review\b[^\n]*--approve\b", "Self-approval via gh pr review --approve is prohibited."),
    (r"\bgh\s+release\s+(create|delete|edit)\b", "Release mutation is prohibited without separate Engineer authorization."),
    (r"\bgh\s+api\b[^\n]*(-X|--method)\s*(PUT|DELETE|PATCH)\s+/?repos/[^\n]*/(branches|rulesets|collaborators|hooks)", "Repository admin/branch-protection mutation is prohibited."),
    (r"\b(JetboxWriteState|DeletePlugin|InstallCustomization)\b", "Language Server state-mutation RPCs are restricted."),
    (r"\bphp\s+artisan\s+(migrate:fresh|migrate:reset|db:wipe)\b[^\n]*--force\b", "Destructive production database reset is prohibited."),
]

PROTECTED_GLOBAL_PATHS = [
    "/.gemini/config/config.json",
    "/.gemini/config/plugins/",
]


def evaluate_pre_tool_use(payload: dict) -> dict:
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict):
        return {"decision": "deny", "reason": "Fail-closed: missing or invalid toolCall object in PreToolUse payload."}

    tool_name = str(tool_call.get("name") or "")
    args = tool_call.get("args")
    if not isinstance(args, dict):
        return {"decision": "deny", "reason": "Fail-closed: missing or invalid toolCall.args in PreToolUse payload."}

    if tool_name == "run_command":
        cmd = str(args.get("CommandLine") or "")
        for pattern, reason in FORBIDDEN_COMMAND_PATTERNS:
            if re.search(pattern, cmd, flags=re.IGNORECASE):
                return {"decision": "deny", "reason": reason}

    if tool_name in ("write_file", "edit_file"):
        raw_path = str(args.get("Path") or "").replace("\\", "/")
        for protected in PROTECTED_GLOBAL_PATHS:
            if protected.lower() in raw_path.lower():
                return {
                    "decision": "deny",
                    "reason": f"Global Antigravity configuration write ({protected}) is prohibited without explicit user permission.",
                }

    return {"decision": "allow"}


def main() -> int:
    is_post = "--post" in sys.argv[1:]
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            print(json.dumps({} if is_post else {"decision": "deny", "reason": "Fail-closed: empty stdin payload."}))
            return 0
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            print(json.dumps({} if is_post else {"decision": "deny", "reason": "Fail-closed: stdin payload must be a JSON object."}))
            return 0
    except Exception as exc:
        if is_post:
            print(json.dumps({}))
        else:
            print(json.dumps({"decision": "deny", "reason": f"Fail-closed hook JSON parse error: {exc}"}))
        return 0

    if is_post:
        print(json.dumps({}))
        return 0

    result = evaluate_pre_tool_use(payload)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
