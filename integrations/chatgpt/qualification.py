"""Run original test suites, preserve raw evidence, never rewrite assertions."""
import argparse, hashlib, json, os, pathlib, subprocess, sys, tempfile

SOURCE = "0e8765de6e0e87ea9b4503714f08fa650e1a79c6"
TREE = "80eaa7a4f879871e5df533203b8b60b563f8b782"
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--commit", required=True)
    args = ap.parse_args()
    root, out = args.repo.resolve(), args.out.resolve()
    def git(*argv):
        return subprocess.check_output(["git", *argv], cwd=root, text=True).strip()
    if root == out or root in out.parents:
        raise SystemExit("Evidence directory must be outside checkout")
    if git("rev-parse", "HEAD") != args.commit or git("status", "--porcelain"):
        raise SystemExit("Requires clean exact checkout")
    if git("rev-parse", SOURCE+"^{tree}") != TREE:
        raise SystemExit("Upstream tree mismatch")
    subprocess.run(["git","merge-base","--is-ancestor",SOURCE,args.commit],cwd=root,check=True)
    if any(not p.startswith("integrations/chatgpt/") for p in git("diff","--name-only",SOURCE,args.commit).splitlines()):
        raise SystemExit("Inherited source changed")
    out.mkdir(parents=True, exist_ok=False)
    cmds = [
        [sys.executable,"-m","unittest","integrations.antigravity.tests.test_factory_core","-v"],
        [sys.executable,"-m","unittest","integrations.antigravity.tests.test_qualification_benchmarks","-v"],
        *[[sys.executable,"tools/forge_check.py",x] for x in ("repo","schemas","links","nest")],
        [sys.executable,"-m","unittest","discover","-s","arsenal/tests","-v"],
        [sys.executable,"tools/entity_check.py"],
    ]
    results=[]
    # Deliberately no GitHub/OpenAI/cloud credentials in the test environment.
    with tempfile.TemporaryDirectory() as home:
        env={k:os.environ[k] for k in ("PATH","SystemRoot","WINDIR","COMSPEC","PATHEXT","LANG") if k in os.environ}
        env.update(HOME=home,USERPROFILE=home,TMPDIR=home,TEMP=home,TMP=home,PYTHONDONTWRITEBYTECODE="1")
        for i,cmd in enumerate(cmds):
            try:
                p=subprocess.run(cmd,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
                raw=p.stdout; code=p.returncode
            except subprocess.TimeoutExpired as e:
                raw=(e.stdout or b"")+b"\nTIMEOUT"; code=124
            except OSError as e:
                raw=str(e).encode(); code=127
            file=out/f"{i:02d}.log"; file.write_bytes(raw)
            results.append({"argv":cmd,"exit":code,"log":file.name,"sha256":hashlib.sha256(raw).hexdigest()})
    (out/"results.json").write_text(json.dumps({"commit":args.commit,"tree":git("rev-parse","HEAD^{tree}"),"results":results},indent=2))
    return 0 if all(r["exit"]==0 for r in results) else 1

if __name__=="__main__":
    raise SystemExit(main())
