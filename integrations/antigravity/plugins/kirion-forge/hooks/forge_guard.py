#!/usr/bin/env python3
"""Fail-closed PreToolUse and PostToolUse lifecycle guard for the KIRION Forge Antigravity plugin."""
from __future__ import annotations

import json
import posixpath
import re
import sys

# Matches quoted, unquoted, or mixed key="value with spaces" shell argument tokens
_ARG = r'''(?:(?:"[^"]*"|'[^']*'|[^\s"'])+)'''
_GIT_BIN = r"""\bgit(?:\.exe)?['"]?"""
_GH_BIN = r"""\bgh(?:\.exe)?['"]?"""
_PHP_BIN = r"""\bphp(?:\.exe)?['"]?"""
_GIT_OPTS = rf"(?:\s+(?:-[Cc]\s*{_ARG}|--(?:git-dir|work-tree|namespace|config-env|super-prefix)(?:={_ARG}|\s+{_ARG})|--[a-z][a-z0-9-]*(?:={_ARG})?|-p))*"
_SEP_END = r"""(?:['"]?(?:\s|[;&|`)<>$]|$))"""

FORBIDDEN_COMMAND_PATTERNS = [
    (
        rf"{_GIT_BIN}{_GIT_OPTS}\s+push\b[^\n]*(\s--force\b|\s--force-with-lease\b|\s--force-if-includes\b|\s--delete\b|\s--mirror\b|\s--prune\b|\s-[a-z]*[fd][a-z]*\b|\s['\"]?\+\S+|\s['\"]?:\S+)",
        "Force push, combined -f/-d flag, --mirror/--prune, '+' refspec, or remote ref deletion is prohibited by KIRION Forge policy.",
    ),
    (
        rf"{_GIT_BIN}{_GIT_OPTS}\s+push\b[^\n]*(?:(?:\s|['\":/])(?:refs/heads/|refs/remotes/[^/\s\"']+/|origin/)?(?:main|master|production|release)){_SEP_END}",
        "Direct push to protected branch (main/master/production/release) is prohibited by KIRION Forge policy.",
    ),
    (
        rf"{_GIT_BIN}{_GIT_OPTS}\s+branch\b[^\n]*("
        r"(?-i:\s-[A-Za-z]*D[A-Za-z]*\b)"
        r"|(?-i:\s-(?:[A-Za-z]*d[A-Za-z]*f|[A-Za-z]*f[A-Za-z]*d)[A-Za-z]*\b)"
        r"|(?:\s--delete\b|(?-i:\s-d\b))[^\n]*(?:\s--force\b|(?-i:\s-f\b))"
        r"|(?:\s--force\b|(?-i:\s-f\b))[^\n]*(?:\s--delete\b|(?-i:\s-d\b))"
        r")",
        "Forced local branch deletion (git branch -D / -df / --delete --force) is prohibited by KIRION Forge policy.",
    ),
    (
        r"\b(rm(?:\.exe)?\s+(?:[^\n]*\s)?-[^\s]*[rf][^\s]*\s+(?:[^\n]*\s)?['\"]?(?:\S*/)?\.git['\"]?(?:\b|/|\s|[;&|]|$)|remove-item\b[^\n]*\.git(?:\b|/|\\|\s|[;&|]|$)|rmdir\b[^\n]*\.git(?:\b|/|\\|\s|[;&|]|$))",
        "Destructive removal of .git metadata is prohibited by KIRION Forge policy.",
    ),
    (
        rf"{_GH_BIN}\s+pr\s+merge\b",
        "Autonomous PR merge is prohibited; promotion requires independent Engineer acceptance.",
    ),
    (
        rf"{_GH_BIN}\s+pr\s+review\b[^\n]*(\s--approve\b|\s-[a-z]*a[a-z]*\b)",
        "Self-approval via gh pr review (--approve / -a) is prohibited.",
    ),
    (
        rf"{_GH_BIN}\s+release\s+(create|delete|edit)\b",
        "Release mutation is prohibited without separate Engineer authorization.",
    ),
    (
        rf"{_GH_BIN}\s+repo\s+(delete|edit|archive|rename)\b",
        "Repository admin mutation via gh repo (delete/edit/archive/rename) is prohibited.",
    ),
    (
        r"\b(JetboxWriteState|DeletePlugin|InstallCustomization)\b",
        "Language Server state-mutation RPCs are restricted.",
    ),
    (
        rf"{_PHP_BIN}\s+artisan\s+(migrate:fresh|migrate:reset|db:wipe)\b[^\n]*--force\b",
        "Destructive production database reset is prohibited.",
    ),
]

GH_API_BIN_RE = re.compile(rf"{_GH_BIN}\s+api\b", re.IGNORECASE)
GH_API_MUTATING_METHOD_RE = re.compile(
    r"(?:^|\s)(?:(?:-X\s*|--method(?:\s+|=))['\"]?(?:PUT|DELETE|PATCH|POST)\b|(?:-[fF](?:\s+|=|\S)|--(?:raw-)?field(?:\s+|=)|--input(?:\s+|=)))",
    re.IGNORECASE,
)
_GH_REPO_PREFIX = r"(?:https?://[^/\s\"']+)?/?repos/[^/\s\"']+/[^/\s\"']+"
GH_API_PROTECTED_ENDPOINT_RE = re.compile(
    rf"{_GH_REPO_PREFIX}/(?:branches|rulesets|collaborators|hooks|git/refs|merges|releases|pulls/[^/\s\"']+/merge|pulls/[^/\s\"']+/reviews)(?:[/\s\"';&|]|$)",
    re.IGNORECASE,
)
GH_API_DIRECT_REPO_ENDPOINT_RE = re.compile(
    rf"(?:^|[\s'\"]){_GH_REPO_PREFIX}(?:['\"]?(?:\s|[;&|]|$))",
    re.IGNORECASE,
)
GH_API_GRAPHQL_RE = re.compile(rf"{_GH_BIN}\s+api\b[^\n]*\bgraphql\b", re.IGNORECASE)
GH_GRAPHQL_MUTATION_RE = re.compile(r"\bmutation\b", re.IGNORECASE)

GLOBAL_CONFIG_TREE_RE = re.compile(r"(^|/)\.gemini/config(/|$)", re.IGNORECASE)


def _normalize_shell_continuations(cmd: str) -> str:
    """Collapse POSIX backslash-newline and PowerShell backtick-newline continuations before policy matching."""
    return re.sub(r"(?:\\|`)[ \t]*\r?\n[ \t]*", " ", cmd)


def evaluate_pre_tool_use(payload: dict) -> dict:
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict):
        return {"decision": "deny", "reason": "Fail-closed: missing or invalid toolCall object in PreToolUse payload."}

    tool_name = str(tool_call.get("name") or "")
    args = tool_call.get("args")
    if not isinstance(args, dict):
        return {"decision": "deny", "reason": "Fail-closed: missing or invalid toolCall.args in PreToolUse payload."}

    if tool_name == "run_command":
        cmd = _normalize_shell_continuations(str(args.get("CommandLine") or ""))
        for pattern, reason in FORBIDDEN_COMMAND_PATTERNS:
            if re.search(pattern, cmd, flags=re.IGNORECASE):
                return {"decision": "deny", "reason": reason}
        # Order-independent gh api mutating check for protected repo/PR/release/ref endpoints
        if (
            GH_API_BIN_RE.search(cmd)
            and GH_API_MUTATING_METHOD_RE.search(cmd)
            and (GH_API_PROTECTED_ENDPOINT_RE.search(cmd) or GH_API_DIRECT_REPO_ENDPOINT_RE.search(cmd))
        ):
            return {
                "decision": "deny",
                "reason": "Repository admin, branch-protection, PR merge/review, release, or git/refs API mutation is prohibited.",
            }
        # Block GraphQL mutations via gh api graphql
        if GH_API_GRAPHQL_RE.search(cmd) and GH_GRAPHQL_MUTATION_RE.search(cmd):
            return {
                "decision": "deny",
                "reason": "GraphQL mutation via gh api graphql is prohibited.",
            }

    if tool_name in ("write_file", "edit_file"):
        raw_path = str(args.get("Path") or "").replace("\\", "/").strip()
        norm_path = posixpath.normpath(raw_path) if raw_path else ""
        if GLOBAL_CONFIG_TREE_RE.search(raw_path) or GLOBAL_CONFIG_TREE_RE.search(norm_path):
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
