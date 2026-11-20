"""Independent archive verifier: compare byte identity against git object inventory, not builder claims."""
import hashlib,json,pathlib,re,subprocess,sys,zipfile,stat
out,legacy=map(pathlib.Path,sys.argv[1:3])
candidate=sys.argv[3]
SOURCE="0e8765de6e0e87ea9b4503714f08fa650e1a79c6"
V="skills/forge-port/references/upstream/"
P="skills/forge-port/references/port/"
ROOT="kirion-forge-chatgpt/"
checks=[]
def check(name,ok,detail=None): checks.append({"test":name,"pass":bool(ok),"detail":detail})
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output(["git",*args])
def inventory(ref,paths=()):
    result={}
    for line in git("ls-tree","-rz",ref,"--",*paths).split(b"\0"):
        if not line:continue
        h,p=line.split(b"\t",1);mode,typ,blob=h.decode().split()
        if typ!="blob":raise ValueError("unexpected object")
        result[p.decode()]=(mode,blob)
    return result
def blobid(data):return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()
def safe(names):
    return len(names)==len(set(names)) and all(n.startswith(ROOT) and not any(x in ("",".","..") for x in n.split("/")) and not re.search(r'[:\\\x00-\x1f]',n) for n in names)
a,b=(out/"candidate-1.zip"),(out/"candidate-2.zip")
if not a.is_file() or not b.is_file():
    check("archive exists",False)
else:
    check("reproducible",sha(a.read_bytes())==sha(b.read_bytes()),sha(a.read_bytes()))
    with zipfile.ZipFile(a) as z:
        names=z.namelist()
        check("archive safe unique paths",safe(names) and all(stat.S_ISREG(i.external_attr>>16) for i in z.infolist()))
        check("zip CRC",z.testzip() is None)
        rel={n[len(ROOT):] for n in names}
        def rd(n):return z.read(ROOT+n)
        m=json.loads(rd("skills/forge-port/references/SOURCE_MANIFEST.json"))
        source=inventory(SOURCE); port=inventory(candidate,["integrations/chatgpt"])
        expected={p:(V+p,mode,blob) for p,(mode,blob) in source.items()}|{p:(P+p,mode,blob) for p,(mode,blob) in port.items()}
        check("exact inventory and candidate pin",len(source)==1489 and set(expected)==set(m["files"]) and m["candidate"]==candidate and m["upstream"]==SOURCE and m["tree"]=="80eaa7a4f879871e5df533203b8b60b563f8b782",{"canonical":len(source),"port":len(port)})
        failures=[]
        for path,(dest,mode,blob) in expected.items():
            if dest not in rel:failures.append(path);continue
            data=rd(dest);record=m["files"].get(path,{})
            if blobid(data)!=blob or record!={"blob":blob,"sha256":sha(data),"mode":mode,"package_path":dest} or z.getinfo(ROOT+dest).external_attr>>16!=int(mode,8):
                failures.append(path)
        check("all git blobs, modes and manifest hashes match",not failures,failures[:20])
        projection={}
        for path in source:
            if path.startswith(".agents/skills/"):projection["skills/"+path[len(".agents/skills/"):]]=path
            elif path.startswith("integrations/antigravity/plugins/kirion-forge/skills/"):projection[path[len("integrations/antigravity/plugins/kirion-forge/"):]]=path
        bad=[p for p,q in projection.items() if p not in rel or rd(p)!=rd(V+q)]
        check("native projections exactly canonical",not bad and m["projected"]==projection and sum(p.endswith("/SKILL.md") for p in projection)==32,bad)
        route=json.loads(rd(P+"integrations/chatgpt/routing.json"))
        old=set(json.loads(legacy.read_text())["skills"])
        skill_names={p.split("/")[1] for p in rel if re.fullmatch(r"skills/[^/]+/SKILL\.md",p)}
        check("legacy routes",old<=skill_names and old==set(route["legacy_skills"]),sorted(old-skill_names))
        def target_exists(x):return V+x in rel or any(p.startswith(V+x.rstrip("/")+"/") for p in rel)
        missing=[]
        for alias,targets in route["aliases"].items():
            p="skills/"+alias+"/SKILL.md"
            for t in targets:
                if p not in rel or not target_exists(t) or t not in rd(p).decode():missing.append((alias,t))
        for role,t in route["personas"].items():
            for alias in ["forge-persona-"+role]+([] if "kirion-"+role in route["collisions"] else ["kirion-"+role]):
                p="skills/"+alias+"/SKILL.md"
                if p not in rel or not target_exists(t) or t not in rd(p).decode():missing.append((alias,t))
        check("all 10 persona and legacy alias targets resolve",len(route["personas"])==10 and not missing,missing)
        check("collision precedence",route["collisions"]=={"kirion-integrator":"forge-persona-integrator","kirion-qa":"forge-persona-qa"} and all(rd("skills/"+x+"/SKILL.md")==rd(V+".agents/skills/"+x+"/SKILL.md") for x in route["collisions"]))
        bad=[x for x in skill_names if not re.search(r"(?m)^name:\s*"+re.escape(x)+r"\s*$",rd("skills/"+x+"/SKILL.md").decode())]
        check("native skill names",not bad and len(skill_names)==60,{"count":len(skill_names),"mismatch":bad})
        manifests=[json.loads(rd(p)) for p in ["plugin.json",".codex-plugin/plugin.json"]]
        check("manifest version and identity",all(x.get("name")=="kirion-forge-chatgpt" and x.get("version")=="0.3.0-rc.2" for x in manifests) and manifests[0].get("$schema")=="https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        allowed=set(dest for dest,_,_ in expected.values())|set(projection)|{"plugin.json",".codex-plugin/plugin.json","README.md","skills/forge-port/SKILL.md","skills/forge-port/references/SOURCE_MANIFEST.json"}
        allowed|={"skills/"+x+"/SKILL.md" for x in skill_names}
        check("no unmapped archive files",rel==allowed,sorted(rel^allowed)[:20])
        sample=rd(V+"AGENTS.md")
        check("negative control tampering changes git blob",blobid(sample+b"\nBAD")!=source["AGENTS.md"][1])
        check("negative duplicate/traversal controls",not safe([ROOT+"a",ROOT+"a"]) and not safe([ROOT+"../x"]) and not safe(["/bad"]) and not safe([ROOT+"x\\y"]))
    (out/"archive-sha256.txt").write_text(sha(a.read_bytes())+"  "+a.name+"\n"+sha(b.read_bytes())+"  "+b.name+"\n")
(out/"package-audit.json").write_text(json.dumps({"checks":checks,"native_activation":"NOT_RUN","independent_model_context":"BLOCKED"},indent=2))
print(json.dumps(checks,indent=2))
sys.exit(not checks or any(not x["pass"] for x in checks))
