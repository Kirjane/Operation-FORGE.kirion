#!/usr/bin/env python3
"""Codex source qualification receipt runner; run only inside approved isolation.

This command neither creates isolation nor establishes authority or acceptance.
It deliberately excludes detached public R4 and all private qualification.
Dependencies must already be installed by the qualified executor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

if __package__:
    from .verify_source_imports import APPROVED_IMPORT, full_sha
else:
    from verify_source_imports import APPROVED_IMPORT, full_sha

ROOT = Path(__file__).resolve().parents[1]
# Fixed suite inventory is independent of mutable candidate discovery.
SUITES = (
    ("qualification-runner", ("{python}", "-m", "tools.qualification_unittest", "tools.test_qualify_completion", "-v"), "unittest"),
    ("source-import", ("{python}", "tools/verify_source_imports.py", APPROVED_IMPORT), "import"),
    ("entity", ("{python}", "tools/entity_check.py"), "entity"),
    ("arsenal", ("{python}", "-m", "tools.qualification_unittest", "discover", "-s", "arsenal/tests", "-v"), "unittest"),
    ("antigravity", ("{python}", "-m", "tools.qualification_unittest", "discover", "-s", "integrations/antigravity/tests", "-v"), "unittest"),
    ("chatgpt", ("{python}", "-m", "tools.qualification_unittest", "discover", "-s", "integrations/chatgpt", "-p", "test_*.py", "-v"), "unittest"),
    ("connector", ("node", "--test", "integrations/chatgpt/connector_adapter.test.mjs"), "tap"),
    ("assurance-r2b", ("{python}", "-m", "tools.qualification_unittest", "discover", "-s", "experiments/assurance_r2b/tests", "-v"), "unittest"),
    ("obsidian", ("{python}", "-m", "tools.qualification_unittest", "discover", "-s", "obsidian/tests", "-v"), "unittest"),
)


def environment(home):
    allow = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL",
             "PYTHONUTF8", "PYTHONIOENCODING"}
    env = {k:v for k,v in os.environ.items() if k.upper() in allow}
    env.update(HOME=str(home), USERPROFILE=str(home), GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
               PYTHONDONTWRITEBYTECODE="1", CI="true")
    return env


def git(env,*args):
    return subprocess.check_output(["git","--no-replace-objects",*args], cwd=ROOT,env=env,
                                   stderr=subprocess.PIPE,timeout=30)


def pinned(env,candidate,tree):
    return (git(env,"rev-parse","HEAD").decode().strip()==candidate
            and git(env,"rev-parse","HEAD^{tree}").decode().strip()==tree
            and not git(env,"status","--porcelain","--untracked-files=all","--ignored=matching"))


def counts(raw,style):
    if style in (None,"import","entity"):
        return None, 0
    text=raw.decode("utf-8","replace")
    if style=="unittest":
        found=re.findall(r"(?m)^Ran (\d+) tests? in ",text)
        skips=re.findall(r"(?:skipped|expected failures|unexpected successes)=(\d+)", "\n".join(re.findall(r"(?m)^(?:OK|FAILED) \([^\n]*",text)))
    elif style=="tap":
        found=re.findall(r"(?m)^# tests (\d+)\s*$",text)
        skips=re.findall(r"(?m)^# (?:skipped|todo) (\d+)\s*$",text)
    else:
        raise ValueError("UNKNOWN_SUITE_STYLE")
    return (int(found[-1]) if len(found)==1 else None), sum(map(int,skips))


def actual_cases(raw,style):
    text=raw.decode("utf-8","strict")
    if style=="unittest":
        lines=re.findall(r"(?m)^FORGE_CASE_RESULTS (.+)$",text)
        if len(lines)!=1: return []
        rows=json.loads(lines[0])
        if not isinstance(rows,list) or any(not isinstance(row,dict) or set(row)!={"id","status"} or row["status"]!="PASS" for row in rows):
            return []
        return [row["id"] for row in rows]
    if style=="tap":
        if re.search(r"(?im)^\s*(?:not ok\b|ok\b.*#\s*(?:skip|todo)\b)",text): return []
        return re.findall(r"(?m)^ok \d+ - (.+)$",text)
    if style=="entity":
        lines=re.findall(r"(?m)^FORGE_ENTITY_RESULTS (.+)$",text)
        if len(lines)!=1: return []
        return json.loads(lines[0])
    if style=="import":
        row=json.loads(text)
        if (row.get("status")=="SOURCE_IMPORT_VERIFIED" and row.get("candidate")==APPROVED_IMPORT
                and row.get("imported_leaves")==71 and row.get("donor_commits")==6):
            return ["source-import:71:6"]
    return []


def approved_inventory(path,pin,candidate,tree):
    if not re.fullmatch(r"[0-9a-f]{64}",pin or ""):
        raise ValueError("EXPECTED_INVENTORY_DIGEST_REQUIRED")
    if path.resolve()==ROOT or ROOT in path.resolve().parents:
        raise ValueError("INVENTORY_MUST_BE_EXTERNAL")
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin:
        raise ValueError("EXPECTED_INVENTORY_DIGEST_MISMATCH")
    obj=json.loads(raw)
    if (not isinstance(obj,dict) or set(obj)!={"schema","candidate","tree","suites"} or
            obj["schema"]!="forge.qualification-inventory.v1" or obj["candidate"]!=candidate or obj["tree"]!=tree or
            not isinstance(obj["suites"],dict) or set(obj["suites"])!={row[0] for row in SUITES}):
        raise ValueError("EXPECTED_INVENTORY_SCOPE_MISMATCH")
    for cases in obj["suites"].values():
        if (not isinstance(cases,list) or not cases or any(type(x) is not str or not x for x in cases)
                or len(cases)!=len(set(cases))):
            raise ValueError("EXPECTED_CASE_IDS_INVALID")
    return obj["suites"]


def run_suite(name,argv,style,env,out,expected=None):
    path=out/(name+".log")
    exit_code=None
    status="BLOCKED"
    try:
        with path.open("xb") as log:
            proc=subprocess.run(argv,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
            exit_code=proc.returncode
        status="PASS" if exit_code==0 else "FAIL"
    except (OSError,subprocess.TimeoutExpired):
        if not path.exists():
            path.write_bytes(b"")
    raw=path.read_bytes()
    total,skipped=counts(raw,style)
    try:
        cases=actual_cases(raw,style)
        valid=isinstance(cases,list) and all(type(x) is str and x for x in cases) and len(set(cases))==len(cases)
    except (ValueError,TypeError,KeyError):
        cases=[]; valid=False
    if status=="PASS" and (not valid or not cases or expected is None or sorted(cases)!=sorted(expected)
                            or skipped or (style in ("unittest","tap") and total!=len(cases))):
        status="INCOMPLETE"
    return {"suite":name,"argv":argv,"exit_code":exit_code,"status":status,
            "tests":total,"skipped":skipped,"case_ids":cases,"expected_case_ids":expected,"log":path.name,
            "log_bytes":len(raw),"log_sha256":hashlib.sha256(raw).hexdigest()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate",required=True)
    p.add_argument("--tree",required=True)
    p.add_argument("--receipt-dir",type=Path,required=True)
    p.add_argument("--expected-inventory",type=Path,required=True)
    p.add_argument("--inventory-sha256",required=True)
    args=p.parse_args()
    candidate,tree=full_sha(args.candidate),full_sha(args.tree)
    out=args.receipt_dir.resolve()
    if out==ROOT or ROOT in out.parents:
        p.error("receipt directory must be outside candidate checkout")
    out.mkdir(parents=True,exist_ok=False)
    home=out/"isolated-home"
    home.mkdir()
    env=environment(home)
    report={"candidate":candidate,"tree":tree,"suite_inventory":[x[0] for x in SUITES],
            "suites":[],"private_qualification":"NOT_RUN","detached_public_r4":"SEPARATE_ISOLATION_REQUIRED",
            "runtime_isolation":"EXTERNAL_PREREQUISITE_NOT_ATTESTED_BY_RUNNER",
            "acceptance":"NOT_GRANTED","promotion_authorized":False}
    try:
        inventory=approved_inventory(args.expected_inventory,args.inventory_sha256,candidate,tree)
        report["inventory_sha256"]=args.inventory_sha256
        if not pinned(env,candidate,tree):
            raise ValueError("EXACT_CLEAN_CHECKOUT_REQUIRED")
        report["parents"]=[row[7:] for row in git(env,"cat-file","commit",candidate).split(b"\n\n",1)[0].decode().splitlines() if row.startswith("parent ")]
        report["versions"]={}
        for name,argv in (("python",[sys.executable,"--version"]),("node",["node","--version"]),
                          ("git",["git","--version"]),("php",["php","--version"])):
            report["versions"][name]=subprocess.check_output(argv,cwd=ROOT,env=env,stderr=subprocess.STDOUT,timeout=30).decode().strip()
        for name,argv,style in SUITES:
            if not pinned(env,candidate,tree):
                raise ValueError("CHECKOUT_DRIFT_BEFORE_SUITE")
            result=run_suite(name,[sys.executable if x=="{python}" else x for x in argv],style,env,out,inventory[name])
            report["suites"].append(result)
            if not pinned(env,candidate,tree):
                raise ValueError("CHECKOUT_DRIFT_AFTER_SUITE")
        report["status"]="SOURCE_SUITE_PASS" if all(x["status"]=="PASS" for x in report["suites"]) else "INCOMPLETE"
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        report["status"]="BLOCKED"
        report["reason"]=str(exc) if type(exc) is ValueError else type(exc).__name__
    ran={x["suite"] for x in report["suites"]}
    report["not_run"]=[x[0] for x in SUITES if x[0] not in ran]
    (out/"receipt.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if report["status"]=="SOURCE_SUITE_PASS" and not report["not_run"] else 1


if __name__=="__main__":
    raise SystemExit(main())
