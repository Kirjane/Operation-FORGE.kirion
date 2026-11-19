#!/usr/bin/env python3
"""Fail-closed PreToolUse and PostToolUse lifecycle guard for the KIRION Forge Antigravity plugin."""
from __future__ import annotations

import json
import re
import sys

# Matches optional git global options such as -C <dir>, -c k=v, --git-dir=..., --work-tree=...
_GIT_OPTS = r"(?:\s+(?:-[Cc]\s+\S+|--git-dir(?:=\S+|\s+\S+)|--work-tree(?:=\S+|\s+\S+)|--no-pager|-p|--paginate))*"

FORBIDDEN_COMMAND_PATTERNS = [
    (
        rf"\bgit{_GIT_OPTS}\s+push\b[^\n]*(\s--force\b|\s-f\b|\s--force-with-lease\b|\s--force-if-includes\b|\s--delete\b|\s-d\b|\s\+\S+|\s:\S+)",
        "Force push, '+' refspec, or remote ref deletion is prohibited by KIRION Forge policy.",
    ),
    (
        rf"\bgit{_GIT_OPTS}\s+push\b[^\n]*(\s(?:origin\s+)?(?:refs/heads/|refs/remotes/origin/)?(?:main|master|production|release)(?:\s|$)|:(?:refs/heads/)?(?:main|master|production|release)(?:\s|$))",
        "Direct push to protected branch (main/master/production/release) is prohibited by KIRION Forge policy.",
    ),
    (
        rf"\bgit{_GIT_OPTS}\s+branch\b[^\n]*(\s-D\b|\s--delete\b[^\n]*\s--force\b|\s--force\b[^\n]*\s--delete\b)",
        "Forced local branch deletion (git branch -D) is prohibited by KIRION Forge policy.",
    ),
    (
        r"\b(rm\s+(?:[^\n]*\s)?-[^\s]*[rf][^\s]*\s+(?:[^\n]*\s)?(?:\S*/)?\.git(?:\b|/|\s|$)|remove-item\b[^\n]*\.git(?:\b|/|\\|\s|$)|rmdir\b[^\n]*\.git(?:\b|/|\\|\s|$))",
        "Destructive removal of .git metadata is prohibited by KIRION Forge policy.",
    ),
    (
        r"\bgh\s+pr\s+merge\b",
        "Autonomous PR merge is prohibited; promotion requires independent Engineer acceptance.",
    ),
    (
        r"\bgh\s+pr\s+review\b[^\n]*--approve\b",
        "Self-approval via gh pr review --approve is prohibited.",
    ),
    (
        r"\bgh\s+release\s+(create|delete|edit)\b",
        "Release mutation is prohibited without separate Engineer authorization.",
    ),
    (
        r"\bgh\s+api\b[^\n]*(-X|--method)\s*(PUT|DELETE|PATCH)\s+/?repos/[^\n]*/(branches|rulesets|collaborators|hooks)",
        "Repository admin/branch-protection mutation is prohibited.",
    ),
    (
        r"\b(JetboxWriteState|DeletePlugin|InstallCustomization)\b",
        "Language Server state-mutation RPCs are restricted.",
    ),
    (
        r"\bphp\s+artisan\s+(migrate:fresh|migrate:reset|db:wipe)\b[^\n]*--force\b",
        "Destructive production database reset is prohibited.",
    ),
]

GLOBAL_CONFIG_TREE_RE = re.compile(r"(^|/)\.gemini/config(/|$)", re.IGNORECASE)


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
        raw_path = str(args.get("Path") or "").replace("\\", "/").strip()
        if GLOBAL_CONFIG_TREE_RE.search(raw_path):
            return {
                "decision": "deny",
                "reason": "Global Antigravity configuration tree (~/.gemini/config) is prohibited without explicit user permission.",
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
