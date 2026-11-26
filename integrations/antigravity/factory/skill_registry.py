"""W5: existing Arsenal registry, immutable source reads and progressive plans.

Local Git object stores are independently configured by trusted composition;
a repository name in a packet never creates a source mapping. No fetching,
installation, shell execution of skill text, or host authority is performed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from copy import deepcopy
from pathlib import Path, PurePosixPath

from .authority import AuthorityError

REGISTRY_PATH = "arsenal/manifest.json"
MAX_FILE_BYTES = 256 * 1024
MAX_REGISTRY_BYTES = 512 * 1024
MAX_FILES = 8
STAGES = ("PRE_DESIGN", "PRE_IMPLEMENTATION", "PRE_DELIVERY", "POST_DEPLOY")
HOSTS = {"chatgpt", "codex", "antigravity", "fixture"}
MODES = {"MANUAL", "ADVISORY_ONLY", "UNAVAILABLE", "FIXTURE"}
SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class SkillError(AuthorityError):
    pass


def require(ok, reason):
    if not ok:
        raise SkillError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def sha_ok(value):
    return isinstance(value, str) and SHA.fullmatch(value) and value != "0" * 40


def canonical_path(value):
    require(type(value) is str and value and "\\" not in value and ":" not in value
            and not any(ord(c) < 32 or ord(c) == 127 for c in value), "SKILL_PATH_INVALID")
    p = PurePosixPath(value)
    require(not p.is_absolute() and p.as_posix() == value and
            all(x not in {".", "..", ".git"} for x in p.parts)
            and value.endswith(".md") and not value.startswith("-"), "SKILL_PATH_INVALID")
    return value


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        require(k not in out, "REGISTRY_DUPLICATE_KEY")
        out[k] = v
    return out


def parse_json(raw):
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(SkillError("REGISTRY_NONFINITE")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SkillError("REGISTRY_JSON_INVALID") from exc


def unique_strings(value):
    return (type(value) is list and all(type(x) is str and bool(x) for x in value)
            and len(value) == len(set(value)))


class PinnedGitSources:
    """Read immutable commit trees, never working-tree paths or fallback roots."""

    def __init__(self, repositories):
        self._repos = {}
        for repo_id, item in repositories.items():
            require(type(repo_id) is int and repo_id > 0 and type(item) is tuple and len(item) == 2,
                    "SOURCE_CONFIGURATION_INVALID")
            name, root = item
            require(type(name) is str and bool(name), "SOURCE_CONFIGURATION_INVALID")
            self._repos[repo_id] = (name, Path(root).resolve(strict=True))

    def _git(self, root, *args):
        # Do not inherit repository redirects, replace refs or lazy fetch.
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1",
                   GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0")
        try:
            p = subprocess.run(["git", "--no-replace-objects", "-C", str(root), *args],
                               env=env, capture_output=True, check=False, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SkillError("PINNED_SOURCE_UNAVAILABLE") from exc
        require(p.returncode == 0, "PINNED_SOURCE_UNAVAILABLE")
        return p.stdout

    def read(self, repo_id, repo_name, commit, path, *, max_bytes=MAX_FILE_BYTES,
             expected_blob=None, expected_bytes=None, expected_sha256=None):
        require(type(repo_id) is int and repo_id in self._repos and
                self._repos[repo_id][0] == repo_name, "SOURCE_REPOSITORY_UNTRUSTED")
        require(sha_ok(commit), "SOURCE_COMMIT_INVALID")
        if path != REGISTRY_PATH:
            canonical_path(path)
        root = self._repos[repo_id][1]
        actual = self._git(root, "rev-parse", "--verify", commit + "^{commit}").decode("ascii").strip()
        require(actual == commit, "SOURCE_COMMIT_MISMATCH")
        # Literal pathspec and exact leaf; reject symlink and submodule objects.
        records = self._git(root, "ls-tree", "-z", commit, "--", ":(literal)" + path).split(b"\0")
        require(len(records) == 2 and not records[1], "PINNED_PATH_MISSING_OR_AMBIGUOUS")
        header, sep, leaf = records[0].partition(b"\t")
        mode, typ, blob = header.decode("ascii").split()
        require(sep and leaf == path.encode("utf-8") and mode in {"100644", "100755"}
                and typ == "blob" and sha_ok(blob), "PINNED_PATH_NOT_REGULAR_BLOB")
        require(expected_blob is None or blob == expected_blob, "PINNED_BLOB_MISMATCH")
        size = int(self._git(root, "cat-file", "-s", blob))
        require(0 < size <= max_bytes and (expected_bytes is None or size == expected_bytes),
                "PINNED_SIZE_MISMATCH_OR_LIMIT")
        raw = self._git(root, "cat-file", "blob", blob)
        calculated = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        content_hash = hashlib.sha256(raw).hexdigest()
        require(len(raw) == size and calculated == blob and
                (expected_sha256 is None or content_hash == expected_sha256), "PINNED_CONTENT_MISMATCH")
        return raw, {"repository_id": repo_id, "repository_name": repo_name, "commit_sha": commit,
                     "path": path, "blob_sha": blob, "sha256": content_hash, "bytes": size}


class SkillRegistry:
    """One registry rooted in the existing Arsenal manifest, not an install list."""

    def __init__(self, sources, *, repository_id, repository_name, registry_commit):
        require(type(sources) is PinnedGitSources, "TRUSTED_SOURCE_RESOLVER_REQUIRED")
        raw, self._identity = sources.read(repository_id, repository_name, registry_commit,
                                          REGISTRY_PATH, max_bytes=MAX_REGISTRY_BYTES)
        m = parse_json(raw)
        require(type(m) is dict and type(m.get("registry_version")) is int and m["registry_version"] == 1
                and m.get("status") == "draft-not-adopted", "REGISTRY_VERSION_OR_STATUS_INVALID")
        entries = m.get("registry")
        require(type(entries) is list and 0 < len(entries) <= 128 and m.get("candidate_count") == len(entries),
                "REGISTRY_INVENTORY_INVALID")
        self._sources = sources
        self._entries = {}
        seen_paths = set()
        for entry in entries:
            require(type(entry) is dict and set(entry) == {"id", "kind", "source", "dependencies",
                    "hosts", "status", "description"}, "REGISTRY_ENTRY_INVALID")
            name = entry["id"]
            require(type(name) is str and SLUG.fullmatch(name) and name not in self._entries,
                    "REGISTRY_DUPLICATE_OR_INVALID_ID")
            require(entry["kind"] in {"skill", "reference"} and entry["status"] == "CANDIDATE"
                    and type(entry["description"]) is str and bool(entry["description"].strip()),
                    "REGISTRY_ENTRY_INVALID")
            src = entry["source"]
            require(type(src) is dict and set(src) in ({"repository_id", "repository_name", "commit_sha",
                    "path", "blob_sha", "bytes"}, {"repository_id", "repository_name", "commit_sha",
                    "path", "blob_sha", "bytes", "sha256"}), "REGISTRY_SOURCE_INVALID")
            path = canonical_path(src["path"])
            require(path.casefold() not in seen_paths, "REGISTRY_DUPLICATE_PATH")
            seen_paths.add(path.casefold())
            require(type(src["repository_id"]) is int and src["repository_id"] > 0 and
                    type(src["repository_name"]) is str and bool(src["repository_name"]) and
                    sha_ok(src["commit_sha"]) and sha_ok(src["blob_sha"]) and type(src["bytes"]) is int
                    and 0 < src["bytes"] <= MAX_FILE_BYTES, "REGISTRY_SOURCE_INVALID")
            if "sha256" in src:
                require(type(src["sha256"]) is str and DIGEST.fullmatch(src["sha256"]), "REGISTRY_DIGEST_INVALID")
            if entry["kind"] == "skill":
                require(path in {f".agents/skills/{name}/SKILL.md",
                        f"integrations/antigravity/plugins/kirion-forge/skills/{name}/SKILL.md"}
                        and src["repository_id"] == repository_id and src["repository_name"] == repository_name,
                        "CANONICAL_SKILL_PATH_MISMATCH")
            require(unique_strings(entry["dependencies"]) and name not in entry["dependencies"],
                    "REGISTRY_DEPENDENCIES_INVALID")
            hosts = entry["hosts"]
            require(type(hosts) is dict and set(hosts) == HOSTS and
                    all(type(v) is str and v in MODES for v in hosts.values()) and
                    all(hosts[h] != "FIXTURE" for h in HOSTS - {"fixture"}), "REGISTRY_HOST_MODE_INVALID")
            self._entries[name] = deepcopy(entry)
        self._stage = self._validate_routes(m.get("stage_optional"), set(STAGES))
        self._task = self._validate_routes(m.get("task_optional"))
        for name in self._entries:
            self._closure([name])

    @property
    def identity(self):
        return deepcopy(self._identity)

    def inventory(self):
        return [{"id": name, "kind": e["kind"], "path": e["source"]["path"],
                 "status": "AVAILABLE_METADATA", "adopted": False, "hosts": deepcopy(e["hosts"])}
                for name, e in sorted(self._entries.items())]

    def _validate_routes(self, routes, keys=None):
        require(type(routes) is dict and (keys is None or set(routes) == keys), "REGISTRY_ROUTES_INVALID")
        for names in routes.values():
            require(unique_strings(names) and set(names) <= set(self._entries), "REGISTRY_ROUTE_UNKNOWN_SKILL")
        return deepcopy(routes)

    def _closure(self, names):
        ordered, active, done = [], set(), set()
        def visit(name):
            require(type(name) is str and name in self._entries, "SKILL_UNKNOWN")
            require(name not in active, "SKILL_DEPENDENCY_CYCLE")
            if name in done:
                return
            active.add(name)
            for dep in self._entries[name]["dependencies"]:
                visit(dep)
            active.remove(name)
            done.add(name)
            ordered.append(name)
        for name in names:
            visit(name)
        return ordered

    def retrieve(self, name, *, source_authorities=()):
        entry = self._entries[name]
        src = entry["source"]
        if entry["kind"] == "reference":
            # Generic cross-branch/cross-repository standard inputs must be
            # explicitly scoped by the existing authorized source contract.
            require(any(a["repository_id"] == src["repository_id"] and
                        a["repository_name"] == src["repository_name"] and
                        a["commit_sha"] == src["commit_sha"] and
                        any(src["path"] == scope.rstrip("/") or
                            src["path"].startswith(scope.rstrip("/") + "/") for scope in a["scope"])
                        for a in source_authorities), "REFERENCE_SOURCE_NOT_AUTHORIZED")
        raw, identity = self._sources.read(src["repository_id"], src["repository_name"], src["commit_sha"],
                src["path"], expected_blob=src["blob_sha"], expected_bytes=src["bytes"],
                expected_sha256=src.get("sha256"))
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise SkillError("SKILL_UTF8_INVALID") from exc
        require(bool(text.strip()) and "\0" not in text, "SKILL_CONTENT_INVALID")
        if entry["kind"] == "skill":
            lines = text.splitlines()
            require(lines and lines[0] == "---" and "---" in lines[1:], "SKILL_FRONTMATTER_MISSING")
            fields = lines[1:lines.index("---", 1)]
            names = [line.split(":", 1)[1].strip().strip("'\"") for line in fields if line.startswith("name:")]
            require(names == [name], "SKILL_FRONTMATTER_ID_MISMATCH")
        return raw, identity

    def plan(self, required, optional=(), *, host, stage, task="general", max_bytes,
             context_used_bytes=0, max_files=MAX_FILES, source_authorities=(), include_routes=True):
        require(host in HOSTS and stage in STAGES and task in self._task, "SKILL_ROUTE_OR_HOST_UNKNOWN")
        require(type(max_bytes) is int and type(context_used_bytes) is int and
                0 <= context_used_bytes <= max_bytes <= 8 * 1024 * 1024 and type(max_files) is int
                and 1 <= max_files <= MAX_FILES, "SKILL_BUDGET_INVALID")
        required = self._closure(required)
        optional = list(dict.fromkeys([*optional, *(self._stage[stage] if include_routes else []),
                                      *(self._task[task] if include_routes else [])]))
        require(bool(required), "REQUIRED_SKILL_SET_EMPTY")
        for name in optional:
            self._closure([name])
        selected, contents, omitted = [], {}, []
        used = context_used_bytes

        def add_group(group, mandatory):
            nonlocal used
            todo = [n for n in group if n not in contents]
            if not todo:
                return
            def reject(reason):
                if mandatory:
                    raise SkillError(reason)
                omitted.append({"id": group[-1], "reason": reason, "status": "OMITTED_OPTIONAL"})
            if any(self._entries[n]["hosts"][host] not in {"MANUAL", "FIXTURE"} for n in todo):
                reject("SKILL_HOST_UNAVAILABLE_OR_ADVISORY")
                return
            if len(selected) + len(todo) > max_files or used + sum(
                    self._entries[n]["source"]["bytes"] for n in todo) > max_bytes:
                reject("SKILL_CONTEXT_BUDGET_EXCEEDED")
                return
            pending = []
            try:
                for n in todo:
                    raw, identity = self.retrieve(n, source_authorities=source_authorities)
                    pending.append((n, raw, identity))
            except SkillError as exc:
                reject(str(exc))
                return
            if used + sum(len(raw) for _, raw, _ in pending) > max_bytes:
                reject("SKILL_CONTEXT_BUDGET_EXCEEDED")
                return
            for n, raw, identity in pending:
                contents[n] = raw
                used += len(raw)
                selected.append({"id": n, "required": n in required, "source": identity,
                                 "host_mode": self._entries[n]["hosts"][host], "status": "RETRIEVED"})
        add_group(required, True)
        for n in optional:
            add_group(self._closure([n]), False)
        plan = {"schema_version": 1, "registry": self.identity, "host": host, "stage": stage, "task": task,
                "required": required, "selected": selected, "omitted": omitted, "max_files": max_files,
                "max_context_bytes": max_bytes, "prior_context_bytes": context_used_bytes,
                "skill_bytes": used - context_used_bytes, "total_context_bytes": used,
                "status": "RETRIEVED_NOT_LOADED", "promotion_authorized": False}
        return plan, contents
