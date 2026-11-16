#!/usr/bin/env python3
"""Verify and package the pinned KIRION Obsidian vault. Python 3 stdlib only."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ACCEPTED = "ac7285d7cd866b4728c28d64a7c145a6bc43f812"
CANDIDATE = "eabbfbabdbb22d8684fb2c3d80767b8547852b83"
REPOSITORY = "Kirch-Nairu/Operation-FORGE.kirion"
SHA = re.compile(r"^[0-9a-f]{40}$")
WIKI = re.compile(r"(?<!!)\[\[([^\]]+)\]\]")
VAULT = Path("obsidian/KIRION-FORGE-VAULT")

def git(root, *args):
    result = subprocess.run(
        ["git", "-C", str(root), *args], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=20)
    if result.returncode:
        raise ValueError("Pinned source inaccessible: " +
                         result.stderr.decode(errors="replace")[:250])
    return result.stdout

def blob_id(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def fields(content):
    match = re.match(r"\A---\n(.*?)\n---\n", content, flags=re.S)
    if match is None:
        raise ValueError("Missing YAML frontmatter")
    data = {}
    for key in ("id", "source_repo", "source_ref", "source_path",
                "source_status", "source_blob_sha"):
        found = re.search(r"^" + key + r': "([^"]*)"$',
                          match.group(1), re.M)
        if found:
            data[key] = found.group(1)
    for key in ("id", "source_repo", "source_ref", "source_path",
                "source_status"):
        if not data.get(key):
            raise ValueError("Missing source metadata: " + key)
    return data

def verify(root, accepted, candidate):
    if not SHA.fullmatch(accepted) or not SHA.fullmatch(candidate):
        raise ValueError("Only full immutable 40-character SHA pins allowed")
    for ref in (accepted, candidate):
        if git(root, "cat-file", "-t", ref).strip() != b"commit":
            raise ValueError("Source pin is not a Git commit")
    path = root / VAULT
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Vault directory absent or linked")
    notes = {}
    for note in sorted(path.rglob("*.md")):
        if note.is_symlink():
            raise ValueError("Symlinked vault content")
        if re.search(r'[<>:"\\|?*]', note.name) or note.name.rstrip(" .") != note.name:
            raise ValueError("Nonportable vault filename")
        if note.stem in notes:
            raise ValueError("Duplicate Obsidian note basename " + note.stem)
        body = note.read_text(encoding="utf-8")
        info = fields(body)
        ref = accepted if info["source_status"] == "ACCEPTED" else candidate
        if info["source_status"] not in ("ACCEPTED", "CANDIDATE"):
            raise ValueError("Unknown source authority status")
        if info["source_ref"] != ref or info["source_repo"] != REPOSITORY:
            raise ValueError("Incorrect source status or ref " + note.stem)
        original = git(root, "show", ref + ":" + info["source_path"])
        if info.get("source_blob_sha") and blob_id(original) != info["source_blob_sha"]:
            raise ValueError("Original Git blob differs " + note.stem)
        if info["id"].startswith("forge.skill."):
            stripped = re.sub(r"\A---\n.*?\n---\n", "", original.decode(),
                              flags=re.S).strip()
            if "## Canonical contract" not in body:
                raise ValueError("Canonical skill text missing")
            embedded = body.split("## Canonical contract", 1)[1].strip()
            if embedded != stripped:
                raise ValueError("Canonical skill content drift " + note.stem)
        notes[note.stem] = (note, body, info)
    if len([1 for _, _, p in notes.values()
            if p["id"].startswith("forge.skill.")]) != 16:
        raise ValueError("Exactly sixteen full-source skill notes required")
    if len({p["id"] for _, _, p in notes.values()}) != len(notes):
        raise ValueError("Duplicate note IDs")
    count = 0
    for title, (_, body, _) in notes.items():
        # Treat template code blocks as literal sample text, not graph edges.
        no_code = re.sub(r"(?ms)^\x60{3}.*?^\x60{3}[ \t]*$", "", body)
        no_code = re.sub(r"(?ms)^~~~.*?^~~~[ \t]*$", "", no_code)
        for raw in WIKI.findall(no_code):
            key = raw.split("|", 1)[0].split("#", 1)[0].strip()
            if key not in notes:
                raise ValueError("Broken wiki link: " + title + " -> " + key)
            count += 1
    if "00 HOME" not in notes or count < 100:
        raise ValueError("Home missing or disconnected vault")
    mapping = []
    for note, body, props in notes.values():
        mapping.append(dict(
            note=note.relative_to(path).as_posix(),
            **props,
            source_url="https://github.com/" + REPOSITORY +
                       "/blob/" + props["source_ref"] + "/" + props["source_path"]))
    payload = json.dumps(dict(
        schema_version=1,
        accepted_source_ref=accepted,
        candidate_source_ref=candidate,
        source_mode="git-verified",
        notes=sorted(mapping, key=lambda x: x["note"])),
        indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return notes, count, payload

def make_zip(notes, mapping, filename):
    filename.parent.mkdir(parents=True, exist_ok=True)
    content = {note.relative_to(VAULT_ROOT(notes)).as_posix(): body.encode()
               for note, body, _ in notes.values()}
    content["source-index.json"] = mapping.encode()
    with zipfile.ZipFile(filename, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for name in sorted(content):
            row = zipfile.ZipInfo("KIRION-FORGE-VAULT/" + name,
                                  (1980, 1, 1, 0, 0, 0))
            row.external_attr = 0o644 << 16
            archive.writestr(row, content[name], compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)
        folder = zipfile.ZipInfo("KIRION-FORGE-VAULT/_personal/",
                                 (1980, 1, 1, 0, 0, 0))
        folder.external_attr = (0o755 << 16) | 0x10
        archive.writestr(folder, b"")
    with zipfile.ZipFile(filename) as archive:
        if archive.testzip():
            raise ValueError("ZIP CRC failure")

def VAULT_ROOT(notes):
    sample = next(iter(notes.values()))[0]
    return next(parent for parent in sample.parents
                if parent.name == "KIRION-FORGE-VAULT")

def main():
    arg = argparse.ArgumentParser()
    arg.add_argument("--repo-root", type=Path, required=True)
    arg.add_argument("--accepted-ref", default=ACCEPTED)
    arg.add_argument("--candidate-ref", default=CANDIDATE)
    arg.add_argument("--check", action="store_true")
    arg.add_argument("--zip", type=Path)
    a = arg.parse_args()
    root = a.repo_root.resolve()
    notes, edges, index = verify(root, a.accepted_ref, a.candidate_ref)
    index_path = root / VAULT / "source-index.json"
    if index_path.is_symlink():
        raise ValueError("Refusing source index symlink")
    if a.check and index_path.exists() and index_path.read_text() != index:
        raise ValueError("Source index is out of date")
    if not a.check:
        index_path.write_text(index, encoding="utf-8", newline="\n")
    if a.zip:
        make_zip(notes, index, a.zip)
    print(json.dumps({"result": "PASS", "notes": len(notes),
                      "skills": 16, "wiki_links": edges, "mode": "git-verified"}))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print("FORGE OBSIDIAN: FAIL " + str(error), file=sys.stderr)
        sys.exit(1)
