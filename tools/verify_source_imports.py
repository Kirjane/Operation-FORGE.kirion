#!/usr/bin/env python3
"""Verify the original convergence import from immutable Git objects, not ZIP relays.

Run against the import commit (not a later modified checkout). Missing donor Git
objects fail closed. This is source custody only; it does not qualify runtime.
"""
import argparse
import json
import hashlib
import os
import re
import subprocess
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}")
MANIFEST = ".forge/source-imports.json"
# Exact approved initial import, independently read from #37/PR36 custody.
APPROVED_IMPORT = "48736c4a71e234204fa5c60be4a172091886b32a"
APPROVED_BASELINE = "928d08edc691dfaeccd4929d2a6566d1f3a3a789"
APPROVED_MANIFEST_BLOB = "594319cb74607d6b94cdf0dcf20f79a79f7fa2c9"
APPROVED_DONORS = frozenset({
    "10083ae9941551fdc88f7a572e82e12826845246",
    "102c8786eea7ee6c3e1d4ea701d1ec48a68de23b",
    "67e95d3e14628499ae9f17b1c02846c2882cd78a",
    "b0355f326bd96bcb29db40e3e358cc8a7bac058e",
    "2a5adf6f573f944d69e5afd97845cd280d7b564c",
    "fbc228ede2da3b4963af773d4db643c4b272d982",
})


def git(root, *args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(root), *args],
                                   stderr=subprocess.PIPE,
                                   env={k:v for k,v in os.environ.items() if not k.upper().startswith("GIT_")})


def full_sha(value):
    if type(value) is not str or not SHA.fullmatch(value) or value == "0"*40:
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
    if commit != APPROVED_IMPORT:
        raise ValueError("UNAPPROVED_IMPORT_COMMIT")
    manifest_bytes = git(root, "show", commit + ":" + MANIFEST)
    manifest_blob = hashlib.sha1(b"blob " + str(len(manifest_bytes)).encode() + b"\x00" + manifest_bytes).hexdigest()
    if manifest_blob != APPROVED_MANIFEST_BLOB:
        raise ValueError("UNAPPROVED_IMPORT_MANIFEST")
    data = json.loads(manifest_bytes)
    if data["format"] != "forge-source-import/v1":
        raise ValueError("UNKNOWN_MANIFEST_FORMAT")
    baseline = full_sha(data["baseline"])
    header = git(root, "cat-file", "commit", commit).split(b"\n\n",1)[0].split(b"\n")
    parents = [row[7:].decode("ascii") for row in header if row.startswith(b"parent ")]
    if baseline != APPROVED_BASELINE or parents != [baseline]:
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
    if len(imported) != 71 or set(donors) != APPROVED_DONORS or set(current) - set(prior) != imported | {MANIFEST}:
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
