"""Build an uninstalled package from exact Git blobs; no account mutations."""
import argparse, hashlib, json, pathlib, subprocess, zipfile
SOURCE="0e8765de6e0e87ea9b4503714f08fa650e1a79c6"
TREE="80eaa7a4f879871e5df533203b8b60b563f8b782"
PREFIX="integrations/antigravity/plugins/kirion-forge/"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",type=pathlib.Path,required=True)
    p.add_argument("--release-root",type=pathlib.Path,required=True)
    p.add_argument("--out",type=pathlib.Path,required=True)
    p.add_argument("--candidate",required=True)
    a=p.parse_args()
    root=a.repo.resolve()
    def git(*args): return subprocess.check_output(["git",*args],cwd=root)
    if git("rev-parse",SOURCE+"^{tree}").decode().strip()!=TREE: raise SystemExit("wrong upstream tree")
    if git("rev-parse",a.candidate).decode().strip()!=a.candidate: raise SystemExit("exact candidate SHA required")
    subprocess.run(["git","merge-base","--is-ancestor",SOURCE,a.candidate],cwd=root,check=True)
    if any(not path.startswith("integrations/chatgpt/") for path in git("diff","--name-only",SOURCE,a.candidate).decode().splitlines()): raise SystemExit("inherited source modified")
    files={}; custody={}; counts=[0,0,0]
    def add(name,data):
        if name in files: raise SystemExit("duplicate package path "+name)
        files[name]=data
    def read_tree(commit,paths):
        for record in git("ls-tree","-rz",commit,"--",*paths).split(b"\0"):
            if not record: continue
            header,raw=record.split(b"\t",1); mode,typ,blob=header.decode().split()
            path=raw.decode("utf-8")
            if typ!="blob" or mode not in ("100644","100755"): raise SystemExit("unsupported Git object "+path)
            data=git("cat-file","blob",blob)
            if hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()!=blob: raise SystemExit("blob mismatch")
            yield path,blob,data
    vend="skills/forge-port/references/upstream/"
    for path,blob,data in read_tree(SOURCE,[".agents/skills","integrations/antigravity","integrations/__init__.py"]):
        add(vend+path,data)
        custody[path]={"blob":blob,"sha256":hashlib.sha256(data).hexdigest()}
        if path.startswith(".agents/skills/") and path.endswith("/SKILL.md"):
            add("skills/"+path.split("/")[2]+"/SKILL.md",data); counts[0]+=1
        elif path.startswith(PREFIX+"skills/") and path.endswith("/SKILL.md"):
            add(path[len(PREFIX):],data); counts[1]+=1
        elif path.startswith(PREFIX+"agents/") and path.endswith(".md"): counts[2]+=1
    if counts!=[16,16,10]: raise SystemExit("incomplete skill/persona inventory: "+str(counts))
    for path,blob,data in read_tree(a.candidate,["integrations/chatgpt"]):
        add("skills/forge-port/references/port/"+path,data)
        custody[path]={"blob":blob,"sha256":hashlib.sha256(data).hexdigest()}
    for name in ("plugin.json",".codex-plugin/plugin.json"):
        original=json.loads((a.release_root/name).read_text(encoding="utf-8"))
        if original.get("name")!="kirion-forge-chatgpt" or original.get("version")!="0.2.0": raise SystemExit("wrong account baseline")
        original["version"]="0.3.0-rc.1"
        add(name,(json.dumps(original,ensure_ascii=False,indent=2)+"\n").encode())
    add("skills/forge-port/SKILL.md",b"""---\nname: forge-port\ndescription: Activate the inherited Forge engineering factory on ChatGPT, with verified GitHub actor custody and fail-closed session and runtime gates.\n---\nRead references/port/integrations/chatgpt/README.md. Use the original persona and skill contracts under references/upstream, the original authority/scheduler/evidence/QA/recovery modules and exact mission packet. Do not invent native launches, hooks or independent reviews. If canonical execution or an actual separate session is unavailable, block the affected gate; do not replace it with a prompt. Never merge or promote without acceptance.\n""")
    add("skills/forge-port/references/SOURCE_MANIFEST.json",json.dumps({"upstream":SOURCE,"tree":TREE,"candidate":a.candidate,"files":custody},sort_keys=True,indent=2).encode())
    # Preserve all source contents; native skill names are byte-identical copies.
    # No host plugin write, install, or release occurs here.
    with zipfile.ZipFile(a.out,"x",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo("kirion-forge-chatgpt/"+name,(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o100644<<16
            z.writestr(info,data)
    print(hashlib.sha256(a.out.read_bytes()).hexdigest(),a.out)

if __name__=="__main__": main()
