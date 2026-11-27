"""Shared exact Git candidate observation (no mutation)."""
import os
import subprocess
from pathlib import Path
from .authority import is_valid_git_sha
from .ownership import parse_git_raw_z_diff
from .policy import assert_paths_within_ownership, normalize_rel_path


class CandidateDenied(PermissionError):
    pass


def observe_git_candidate(repo, packet, expected, target, tree, declared_paths):
    """Host-owned local Git object readback; not a remote ref/lease fence."""
    if packet.get("base_sha") != expected:
        raise CandidateDenied("PACKET_BASE_DRIFT")
    if not all(is_valid_git_sha(v) for v in (expected,target,tree)):
        raise CandidateDenied("BAD_EXACT_SHA")
    root=Path(repo).resolve(strict=True)
    from .ownership import sanitize_worker_env
    env={k:v for k,v in sanitize_worker_env().items() if not k.upper().startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    def read(*args):
        try:
            return subprocess.run(["git","--no-replace-objects",*args],cwd=root,
                                  env=env,check=True,capture_output=True,timeout=20).stdout
        except (OSError,subprocess.SubprocessError) as exc:
            raise CandidateDenied("CANDIDATE_GIT_READ_FAILED") from exc
    if read("cat-file","-t",expected).strip()!=b"commit" or read("cat-file","-t",target).strip()!=b"commit":
        raise CandidateDenied("CANDIDATE_OBJECT_NOT_COMMIT")
    commit=read("cat-file","commit",target)
    header=commit.split(b"\n\n",1)[0].split(b"\n")
    if [x for x in header if x.startswith(b"tree ")] != [b"tree "+tree.encode()]:
        raise CandidateDenied("CANDIDATE_TREE_DRIFT")
    if [x for x in header if x.startswith(b"parent ")] != [b"parent "+expected.encode()]:
        raise CandidateDenied("CANDIDATE_PARENT_DRIFT")
    raw=read("diff","--no-renames","--raw","-z","--no-ext-diff","--no-textconv",
             "--ignore-submodules=none",expected,target,"--")
    try:
        observed,forbidden=parse_git_raw_z_diff(raw.decode("utf-8","strict"))
    except (UnicodeError,ValueError) as exc:
        raise CandidateDenied("CANDIDATE_DIFF_INVALID") from exc
    if forbidden or not observed:
        raise CandidateDenied("CANDIDATE_DIFF_EMPTY_OR_FORBIDDEN_MODE")
    if any(p!=normalize_rel_path(p) or any(ord(c)<32 or ord(c)==127 for c in p)
           for p in observed):
        raise CandidateDenied("CANDIDATE_PATH_NONCANONICAL")
    if len(set(observed))!=len(observed) or len(set(p.lower() for p in observed))!=len(observed):
        raise CandidateDenied("CANDIDATE_PATH_COLLISION")
    # Verify actual scope before comparing against the proposal's path list.
    assert_paths_within_ownership(packet,observed)
    if sorted(observed)!=sorted(declared_paths):
        raise CandidateDenied("CANDIDATE_DIFF_SCOPE_DRIFT")
    return {"parent":expected,"commit":target,"tree":tree,"paths":sorted(observed)}

