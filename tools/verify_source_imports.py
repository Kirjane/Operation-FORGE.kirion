#!/usr/bin/env python3
"""Verify the original convergence import from immutable Git objects, not ZIP relays.

Run against the import commit (not a later modified checkout). Missing donor Git
objects fail closed. This is source custody only; it does not qualify runtime.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}")
MANIFEST = ".forge/source-imports.json"


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def full_sha(value):
    if type(value) is not str or not SHA.fullmatch(value):
        raise ValueError("FULL_GIT_SHA_REQUIRED")
    return value


def leaf_tree(root, commit):
    full_sha(commit)
    result = {}
    for row in git(root, "ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not row:
            continue
        metadata, path = row.split(b"\t", 1)
        mode, kind, sha = metadata.decode("ascii").split(" ")
        name = path.decode("utf-8", errors="strict")
        if name in result:
            raise ValueError("DUPLICATE_TREE_PATH")
        result[name] = (mode, kind, sha)
    return result


def verify(root, commit):
    full_sha(commit)
    data = json.loads(git(root, "show", commit + ":" + MANIFEST))
    if data["format"] != "forge-source-import/v1":
        raise ValueError("UNKNOWN_MANIFEST_FORMAT")
    baseline = full_sha(data["baseline"])
    parents = git(root, "rev-list", "--parents", "-n", "1", commit).decode().split()
    if parents != [commit, baseline]:
        raise ValueError("IMPORT_PARENT_MISMATCH")
    prior, current = leaf_tree(root, baseline), leaf_tree(root, commit)
    if any(current.get(path) != row for path, row in prior.items()):
        raise ValueError("BASELINE_LEAF_CHANGED")
    donors, imported = {}, set()
    for item in data["imports"]:
        path = item["path"]
        donor = full_sha(item["commit"])
        expected = (item["mode"], "blob", full_sha(item["blob"]))
        if path in prior or path in imported or path == MANIFEST:
            raise ValueError("IMPORT_PATH_COLLISION")
        imported.add(path)
        if donor not in donors:
            donors[donor] = leaf_tree(root, donor)
        if donors[donor].get(path) != expected or current.get(path) != expected:
            raise ValueError("DONOR_OR_IMPORT_BLOB_MISMATCH")
        size = int(git(root, "cat-file", "-s", item["blob"]))
        if size != item["size"]:
            raise ValueError("IMPORT_SIZE_MISMATCH")
    if not imported or set(current) - set(prior) != imported | {MANIFEST}:
        raise ValueError("IMPORT_PATH_SET_MISMATCH")
    return {"status": "SOURCE_IMPORT_VERIFIED", "candidate": commit,
            "preserved_leaves": len(prior), "imported_leaves": len(imported),
            "donor_commits": len(donors), "runtime": "NOT_RUN", "promotion_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        result = verify(args.repo, args.commit)
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": type(exc).__name__,
                          "runtime": "NOT_RUN", "promotion_authorized": False}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
