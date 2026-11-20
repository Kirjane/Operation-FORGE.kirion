"""Audit built ZIP without installing; record all checks."""
import hashlib,json,pathlib,re,sys,zipfile
out,legacy=map(pathlib.Path,sys.argv[1:])
a,b=(out/"candidate-1.zip"),(out/"candidate-2.zip")
findings=[]
def check(test,ok,detail):findings.append({"test":test,"pass":bool(ok),"detail":detail})
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
if not a.is_file() or not b.is_file():
    check("archive build",False,"one or both ZIPs absent")
else:
    check("byte reproducibility",digest(a)==digest(b),digest(a)+" "+digest(b))
    pref="kirion-forge-chatgpt/"
    with zipfile.ZipFile(a) as z:
        members=z.namelist(); names={n.removeprefix(pref) for n in members}
        check("archive paths",len(names)==len(members) and all(n.startswith(pref) and ".." not in pathlib.PurePosixPath(n).parts for n in members),"unique root and safe names")
        check("CRC",z.testzip() is None,"zip integrity")
        def rd(n):return z.read(pref+n)
        native=json.loads(rd("plugin.json"))
        check("native manifest",native.get("name")=="kirion-forge-chatgpt" and native.get("version")=="0.3.0-rc.1" and native.get("$schema")=="https://agent-plugins.org/schemas/1.0.0/plugin.schema.json","structural smoke only")
        vend="skills/forge-port/references/upstream/"
        manifest=json.loads(rd("skills/forge-port/references/SOURCE_MANIFEST.json"))
        failures=[]
        for p,record in manifest["files"].items():
            name=(vend if p.startswith(".agents/skills/") or p.startswith("integrations/antigravity/") or p=="integrations/__init__.py" else "skills/forge-port/references/port/")+p
            data=rd(name)
            if hashlib.sha256(data).hexdigest()!=record["sha256"] or hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()!=record["blob"]:failures.append(p)
        check("source custody",not failures,failures)
        personas=[n for n in names if re.fullmatch(re.escape(vend)+r"integrations/antigravity/plugins/kirion-forge/agents/[^/]+\.md",n)]
        check("persona contract count",len(personas)==10,len(personas))
        skills={n.split("/")[1] for n in names if re.fullmatch(r"skills/[^/]+/SKILL\.md",n)}
        check("native skill count",len(skills)==33,len(skills))
        bad=[n for n in names if re.fullmatch(r"skills/[^/]+/SKILL\.md",n) and not re.search(r"(?m)^name:\s*"+re.escape(n.split("/")[1])+r"\s*$",rd(n).decode())]
        check("native skill directory/frontmatter agreement",not bad,bad)
        missing=[p for p in ["AGENTS.md","BOOTSTRAP.md","BOOTSTRAP_CHATGPT.md","SYSTEM_BOUNDARY.md","EVIDENCE_CROSSWALK.md",".forge/"] if not any(n==vend+p or n.startswith(vend+p) for n in names)]
        check("root doctrine dependencies",not missing,missing)
        old=set(json.loads(legacy.read_text())["skills"])
        check("legacy activation coverage / explicit precedence",not(old-skills),sorted(old-skills))
    (out/"archive-sha256.txt").write_text(digest(a)+"  "+a.name+"\n"+digest(b)+"  "+b.name+"\n")
(out/"package-audit.json").write_text(json.dumps({"checks":findings,"native_activation":"NOT_RUN"},indent=2))
print(json.dumps(findings,indent=2))
sys.exit(0 if findings and all(x["pass"] for x in findings) else 1)
