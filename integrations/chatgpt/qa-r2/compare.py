"""Qualification scaffolding only; run original assertions on exact commits."""
import hashlib,json,os,pathlib,subprocess,sys,tempfile,time,shutil,shlex,re
ROOT=pathlib.Path(__file__).resolve().parents[3]
QA=pathlib.Path(__file__).resolve().parent
SUITE=sys.argv[1]
OUT=pathlib.Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True,exist_ok=False)
BASE="0e8765de6e0e87ea9b4503714f08fa650e1a79c6"
BT="80eaa7a4f879871e5df533203b8b60b563f8b782"
HEAD="03ae31e98ec72765cf60ca71ffff381507595dec"
HT="98d9c500c964437aee2498411a4f892aba1dd47a"
ENV={k:os.environ[k] for k in ("PATH","HOME","LANG","LC_ALL","DOTNET_ROOT","DOTNET_ROOT_X64","DOTNET_MULTILEVEL_LOOKUP","PHP_INI_SCAN_DIR","COMPOSER_HOME","LD_LIBRARY_PATH","TMPDIR","TMP","TEMP","NUGET_PACKAGES") if k in os.environ}
ENV.update(PYTHONDONTWRITEBYTECODE="1",DOTNET_CLI_TELEMETRY_OPTOUT="1",DOTNET_NOLOGO="1",GIT_TERMINAL_PROMPT="0",CI="true")
records=[]
def run(label,cmd,cwd,timeout=600):
    started=time.monotonic()
    try:
        p=subprocess.run(cmd,cwd=cwd,env=ENV,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
        data=p.stdout; rc=p.returncode
    except subprocess.TimeoutExpired as ex:
        data=(ex.stdout or b"")+b"\nTIMEOUT\n"; rc=124
    except OSError as ex:
        data=str(ex).encode(); rc=127
    file=OUT/(label+".log"); file.write_bytes(data)
    print(label,"exit",rc,"sha256",hashlib.sha256(data).hexdigest(),flush=True)
    print(data.decode(errors="replace"),flush=True)
    records.append(dict(label=label,argv=cmd,exit=rc,seconds=round(time.monotonic()-started,3),log=file.name,sha256=hashlib.sha256(data).hexdigest()))
    return rc
def git(cwd,*args):
    return subprocess.check_output(["git",*args],cwd=cwd,env=ENV,text=True).strip()
def checkout(parent,name,sha,tree):
    dest=parent/name
    subprocess.run(["git","worktree","add","--detach",str(dest),sha],cwd=ROOT,env=ENV,check=True)
    if git(dest,"rev-parse","HEAD")!=sha or git(dest,"rev-parse","HEAD^{tree}")!=tree or git(dest,"status","--porcelain"):
        raise RuntimeError("Unclean or mismatched checkout: "+name)
    (OUT/(name+"-before.json")).write_text(json.dumps({"sha":sha,"tree":tree,"dirty":False}))
    return dest
def after(dest,name):
    head=git(dest,"rev-parse","HEAD"); tree=git(dest,"rev-parse","HEAD^{tree}")
    status=git(dest,"status","--porcelain")
    dirty=git(dest,"status","--porcelain","--untracked-files=no")
    (OUT/(name+"-after.json")).write_text(json.dumps({"sha":head,"tree":tree,"status":status,"tracked_dirty":bool(dirty)},indent=2))
    if dirty or head!={"baseline":BASE,"candidate":HEAD}[name] or tree!={"baseline":BT,"candidate":HT}[name]:
        raise RuntimeError("Tracked checkout drift")
def main():
    run("python-version",[sys.executable,"--version"],ROOT)
    if SUITE=="A":
        run("php-version",["php","--version"],ROOT)
        run("php-modules",["php","-m"],ROOT)
        run("composer-version",["composer","--version"],ROOT)
    if SUITE=="B": run("dotnet-info",["dotnet","--info"],ROOT)
    if SUITE=="adapter": run("node-version",["node","--version"],ROOT)
    methods={"A":"test_benchmark_a_php_laravel_procurement_and_inventory","B":"test_benchmark_b_csharp_aspnet_transaction_engine","C":"test_benchmark_c_blind_seeded_deceptive_defects","D":"test_benchmark_d_factory_reliability_and_recovery","E":"test_benchmark_e_adversarial_authority_and_supply_chain"}
    status=[]
    with tempfile.TemporaryDirectory(prefix="forge-r2-") as temp:
        parent=pathlib.Path(temp)
        if SUITE=="B":
            sdks=subprocess.check_output(["dotnet","--list-sdks"],env=ENV,text=True)
            versions=re.findall(r"(?m)^(10\.0\.\d+) ",sdks)
            if not versions: raise RuntimeError("Required .NET 10 SDK unavailable")
            selected=max(versions,key=lambda v:tuple(map(int,v.split("."))))
            (parent/"global.json").write_text(json.dumps({"sdk":{"version":selected,"rollForward":"disable"}}))
            status.append(run("dotnet-sdk-list",["dotnet","--list-sdks"],parent))
            status.append(run("dotnet-selected",["dotnet","--version"],parent))
            if subprocess.check_output(["dotnet","--version"],cwd=parent,env=ENV,text=True).strip()!=selected:
                raise RuntimeError("Wrong .NET SDK selected")
        for name,sha,tree in ([("candidate",HEAD,HT)] if SUITE=="adapter" else [("baseline",BASE,BT),("candidate",HEAD,HT)]):
            dest=checkout(parent,name,sha,tree)
            if SUITE=="adapter":
                status.append(run("node-adapter",["node","integrations/chatgpt/connector_adapter.test.mjs"],dest))
                status.append(run("python-bridge",[sys.executable,str(QA/"test_bridge.py")],dest))
                status.append(run("r4-host-adversarial",[sys.executable,"-m","unittest","integrations.chatgpt.test_host_autonomy","-v"],dest))
                for i in (1,2):
                    status.append(run(f"package-build-{i}",[sys.executable,"integrations/chatgpt/package.py","--repo",str(dest),"--candidate",HEAD,"--release-root",str(QA/"release-root"),"--out",str(OUT/f"candidate-{i}.zip")],dest))
                status.append(run("package-audit",[sys.executable,str(QA/"audit_package.py"),str(OUT),str(QA/"legacy-inventory.json"),HEAD],dest))
            else:
                if SUITE=="A":
                    bench=dest/"integrations/antigravity/benchmarks/php_procurement_inventory"
                    status.append(run(name+"-composer",["composer","install","--no-interaction","--prefer-dist","--no-plugins","--no-scripts"],bench))
                    # Preserve original Windows-style ext layout failure and adapt only runner filesystem.
                    original_path=ENV["PATH"]
                    php=pathlib.Path(shutil.which("php",path=original_path)).resolve()
                    ext=pathlib.Path(subprocess.check_output([str(php),"-r",'echo ini_get("extension_dir");'],env=ENV,text=True).strip()).resolve(strict=True)
                    run(name+"-original-php-layout",[str(php),"-d",f"extension_dir={php.parent/'ext'}","-d","extension=pdo_sqlite","-d","extension=sqlite3",str(bench/"tests/run_tests.php")],bench)
                    bin_dir=parent/(name+"-php"); bin_dir.mkdir()
                    (bin_dir/"ext").symlink_to(ext,target_is_directory=True)
                    wrapper=bin_dir/"php"
                    wrapper.write_text("#!/bin/sh\nexec "+shlex.quote(str(php))+' "$@"\n')
                    wrapper.chmod(0o755)
                    ENV["PATH"]=str(bin_dir)+os.pathsep+original_path
                    args=[str(wrapper),"-d",f"extension_dir={bin_dir/'ext'}","-d","extension=pdo_sqlite","-d","extension=sqlite3","-r",'if (!in_array("sqlite", PDO::getAvailableDrivers(), true) || !class_exists("SQLite3")) exit(42); echo "PDO SQLite and SQLite3 ready";']
                    status.append(run(name+"-php-layout-probe",args,bench))
                if SUITE=="B":
                    status.append(run(name+"-dotnet-selected",["dotnet","--version"],dest))
                target="integrations.antigravity.tests.test_factory_core" if SUITE=="core" else "integrations.antigravity.tests.test_qualification_benchmarks.QualificationBenchmarksTests."+methods[SUITE]
                status.append(run(name+"-"+SUITE,[sys.executable,"-m","unittest",target,"-v"],dest))
                if SUITE=="A": ENV["PATH"]=original_path
            after(dest,name)
            subprocess.run(["git","worktree","remove","--force",str(dest)],cwd=ROOT,env=ENV,check=True)
    return int(any(status))
if __name__=="__main__":
    rc=1
    try: rc=main()
    finally:
        (OUT/"results.json").write_text(json.dumps({"suite":SUITE,"qa_sha":git(ROOT,"rev-parse","HEAD"),"qa_tree":git(ROOT,"rev-parse","HEAD^{tree}"),"baseline":BASE,"candidate":HEAD,"records":records,"exit":rc},indent=2))
    raise SystemExit(rc)
