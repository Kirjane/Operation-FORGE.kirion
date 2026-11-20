"""Reproducible, uninstalled exact-source ChatGPT candidate; no host mutation."""
import argparse, hashlib, json, pathlib, subprocess, zipfile
SOURCE="0e8765de6e0e87ea9b4503714f08fa650e1a79c6"
TREE="80eaa7a4f879871e5df533203b8b60b563f8b782"
PREFIX="integrations/antigravity/plugins/kirion-forge/"
BASE="integrations/chatgpt/"
VEND="skills/forge-port/references/upstream/"
PORT="skills/forge-port/references/port/"
VERSION="0.3.0-rc.2"

def main():
    p=argparse.ArgumentParser()
    for key in ("repo","release-root","out"): p.add_argument("--"+key,type=pathlib.Path,required=True)
    p.add_argument("--candidate",required=True)
    a=p.parse_args()
    root=a.repo.resolve()
    def git(*args): return subprocess.check_output(["git",*args],cwd=root)
    if git("rev-parse",SOURCE+"^{tree}").decode().strip()!=TREE: raise SystemExit("wrong upstream tree")
    if git("rev-parse","HEAD").decode().strip()!=a.candidate or git("status","--porcelain"): raise SystemExit("clean exact candidate checkout required")
    subprocess.run(["git","merge-base","--is-ancestor",SOURCE,a.candidate],cwd=root,check=True)
    if any(not path.startswith(BASE) for path in git("diff","--name-only",SOURCE,a.candidate).decode().splitlines()): raise SystemExit("inherited source modified")
    if a.out.resolve()==root or root in a.out.resolve().parents: raise SystemExit("archive must be outside checkout")
    files={}; custody={}; projected={}; counts=[0,0,0]
    def add(name,data,mode="100644"):
        parts=name.split("/")
        if not name or any(x in ("",".","..") for x in parts) or "\\" in name or ":" in name or any(ord(x)<32 for x in name): raise SystemExit("unsafe package path "+name)
        if name in files: raise SystemExit("duplicate package path "+name)
        files[name]=(data,mode)
    def read_tree(commit,paths=()):
        for record in git("ls-tree","-rz",commit,"--",*paths).split(b"\0"):
            if not record: continue
            header,raw=record.split(b"\t",1); mode,typ,blob=header.decode().split()
            path=raw.decode("utf-8")
            if typ!="blob" or mode not in ("100644","100755"): raise SystemExit("unsupported Git object "+path)
            data=git("cat-file","blob",blob)
            if hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()!=blob: raise SystemExit("blob mismatch")
            yield path,blob,data,mode
    def record(path,blob,data,mode,dest):
        add(dest,data,mode)
        custody[path]={"blob":blob,"sha256":hashlib.sha256(data).hexdigest(),"mode":mode,"package_path":dest}
    for path,blob,data,mode in read_tree(SOURCE):
        record(path,blob,data,mode,VEND+path)
        native=None
        if path.startswith(".agents/skills/"):
            native="skills/"+path[len(".agents/skills/"):]
            if path.endswith("/SKILL.md"): counts[0]+=1
        elif path.startswith(PREFIX+"skills/"):
            native=path[len(PREFIX):]
            if path.endswith("/SKILL.md"): counts[1]+=1
        elif path.startswith(PREFIX+"agents/") and path.endswith(".md"): counts[2]+=1
        if native:
            add(native,data,mode); projected[native]=path
    if counts!=[16,16,10]: raise SystemExit("incomplete skill/persona inventory: "+str(counts))
    for path,blob,data,mode in read_tree(a.candidate,[BASE]):
        record(path,blob,data,mode,PORT+path)
    route=json.loads(files[PORT+BASE+"routing.json"][0])
    def alias(name,targets,description):
        for target in targets:
            if not any(k==VEND+target or k.startswith(VEND+target.rstrip("/")+"/") for k in files): raise SystemExit("route target absent: "+target)
        body="---\nname: "+name+"\ndescription: "+description+"\n---\n\nLoad ../forge-port/SKILL.md and its authority rules first. Resolve these exact canonical paths under ../forge-port/references/upstream/:\n"
        body+="".join("- "+target+"\n" for target in targets)
        body+="\nUse the existing canonical contract; role selection does not create a model context or authorize a GitHub mutation. Authenticate expected login and immutable ID for each authorized operation. Same-context review is non-accepting; no merge, release or production activation without independent acceptance.\n"
        add("skills/"+name+"/SKILL.md",body.encode())
    for name,targets in route["aliases"].items(): alias(name,targets,"Route the legacy "+name+" entry point to the exact inherited Forge doctrine.")
    for role,target in route["personas"].items():
        explicit="forge-persona-"+role
        alias(explicit,[target],"Select the canonical "+role+" persona for an authorized Forge mission.")
        legacy="kirion-"+role
        if legacy not in route["collisions"]: alias(legacy,[target],"Route the legacy "+role+" persona invocation to the canonical contract.")
    for name in route["legacy_skills"]:
        if "skills/"+name+"/SKILL.md" not in files: raise SystemExit("legacy entry absent "+name)
    for name in ("plugin.json",".codex-plugin/plugin.json"):
        original=json.loads((a.release_root/name).read_text(encoding="utf-8"))
        if original.get("name")!="kirion-forge-chatgpt" or original.get("version")!=route["baseline_version"]: raise SystemExit("wrong account baseline")
        original["version"]=VERSION
        interface=original.get("extensions",{}).get("com.openai",{}).get("interface",{})
        if interface:
            interface["shortDescription"]="Evidence-gated software factory"
            interface["longDescription"]="Exact inherited Forge doctrine and engineering engine, authenticated bounded persona routing, comparative CI and same-context adversarial review. Native independent context and production activation remain unqualified."
            interface["defaultPrompt"]=["Activate Forge for my repository. Verify authority and execute bounded work.","Continue a Forge mission from its GitHub issue or pull request.","Run non-accepting adversarial review of an exact candidate."]
        add(name,(json.dumps(original,ensure_ascii=False,indent=2)+"\n").encode())
    add("skills/forge-port/SKILL.md",b"""---\nname: forge-port\ndescription: Activate the exact inherited Forge engineering factory with bounded authenticated persona routing and evidence gates.\n---\nRead references/upstream/AGENTS.md, references/upstream/BOOTSTRAP_CHATGPT.md, references/upstream/arsenal/CHATGPT_BOOTSTRAP.md, references/port/integrations/chatgpt/README.md and references/port/integrations/chatgpt/routing.json. Resolve relative canonical paths in references/upstream. Canonical skills remain byte identical; explicit persona selection uses forge-persona-* (including integrator and qa), not the colliding engineering skill names. Automatically perform bounded same-context Nox review, repair and retest as authorized, and label it non-accepting. Use only actual authenticated GitHub connections; no credential substitution, invented hooks or context IDs. G13 independent model context, generic delivery and production promotion remain blocked until proven. Do not stop feasible candidate work merely because independent acceptance is pending. Never merge, release or self-accept.\n""")
    add("skills/forge-port/references/SOURCE_MANIFEST.json",json.dumps({"upstream":SOURCE,"tree":TREE,"candidate":a.candidate,"files":custody,"projected":projected,"version":VERSION},sort_keys=True,indent=2).encode())
    add("README.md",b"# KIRION Forge ChatGPT qualification candidate\nUninstalled; no independent acceptance. Begin with skills/forge-port/SKILL.md. The complete upstream tree is vendored as inert exact-source reference material; Antigravity hooks are not native ChatGPT hooks.\n")
    with zipfile.ZipFile(a.out,"x",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,(data,mode) in sorted(files.items()):
            info=zipfile.ZipInfo("kirion-forge-chatgpt/"+name,(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=int(mode,8)<<16
            z.writestr(info,data)
    print(hashlib.sha256(a.out.read_bytes()).hexdigest(),a.out)
if __name__=="__main__": main()
