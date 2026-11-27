"""R4 scoped mutation broker. Not installed as a host-global GitHub interceptor.

All writes must pass a trusted remote atomic-CAS adapter. Direct ChatGPT GitHub
tool calls still bypass this module, so HOST_ENFORCEMENT remains BLOCKED.
"""
import hashlib
import hmac
import json
import re
import sqlite3
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from integrations.antigravity.factory.authority import verify_mission_packet, is_valid_git_sha
from integrations.antigravity.factory.ownership import LeaseManager, parse_git_raw_z_diff
from integrations.antigravity.factory.scheduler import FactoryJournal
from integrations.antigravity.factory.policy import assert_operation_allowed, assert_paths_within_ownership, normalize_rel_path

class Denied(PermissionError):
    pass

def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()

def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()

def observe_git_candidate(repo, packet, expected, target, tree, declared_paths):
    """Host-owned local Git object readback; not a remote ref/lease fence."""
    if packet.get("base_sha") != expected:
        raise Denied("PACKET_BASE_DRIFT")
    if not all(is_valid_git_sha(v) for v in (expected,target,tree)):
        raise Denied("BAD_EXACT_SHA")
    root=Path(repo).resolve(strict=True)
    env={k:v for k,v in os.environ.items() if not k.upper().startswith("GIT_")}
    env["GIT_TERMINAL_PROMPT"]="0"
    def read(*args):
        try:
            return subprocess.run(["git","--no-replace-objects",*args],cwd=root,
                                  env=env,check=True,capture_output=True,timeout=20).stdout
        except (OSError,subprocess.SubprocessError) as exc:
            raise Denied("CANDIDATE_GIT_READ_FAILED") from exc
    if read("cat-file","-t",expected).strip()!=b"commit" or read("cat-file","-t",target).strip()!=b"commit":
        raise Denied("CANDIDATE_OBJECT_NOT_COMMIT")
    commit=read("cat-file","commit",target)
    header=commit.split(b"\n\n",1)[0].split(b"\n")
    if [x for x in header if x.startswith(b"tree ")] != [b"tree "+tree.encode()]:
        raise Denied("CANDIDATE_TREE_DRIFT")
    if [x for x in header if x.startswith(b"parent ")] != [b"parent "+expected.encode()]:
        raise Denied("CANDIDATE_PARENT_DRIFT")
    raw=read("diff","--no-renames","--raw","-z","--no-ext-diff","--no-textconv",
             "--ignore-submodules=none",expected,target,"--")
    try:
        observed,forbidden=parse_git_raw_z_diff(raw.decode("utf-8","strict"))
    except (UnicodeError,ValueError) as exc:
        raise Denied("CANDIDATE_DIFF_INVALID") from exc
    if forbidden or not observed:
        raise Denied("CANDIDATE_DIFF_EMPTY_OR_FORBIDDEN_MODE")
    if any(p!=normalize_rel_path(p) or any(ord(c)<32 or ord(c)==127 for c in p)
           for p in observed):
        raise Denied("CANDIDATE_PATH_NONCANONICAL")
    if len(set(observed))!=len(observed) or len(set(p.lower() for p in observed))!=len(observed):
        raise Denied("CANDIDATE_PATH_COLLISION")
    # Verify actual scope before comparing against the proposal's path list.
    assert_paths_within_ownership(packet,observed)
    if sorted(observed)!=sorted(declared_paths):
        raise Denied("CANDIDATE_DIFF_SCOPE_DRIFT")
    return {"parent":expected,"commit":target,"tree":tree,"paths":sorted(observed)}


class ScopedBroker:
    """Local executable broker proof. Remote actor/read/write methods are trusted inputs."""
    def __init__(self,path,key,repo,repo_id,branch,enabled=False,*,
                 service_actor=None,require_service_actor=False,legacy_fixture_mode=False):
        if not isinstance(key,bytes) or len(key)<32: raise Denied("AUDIT_KEY_REQUIRED")
        if type(repo_id)!=int or repo_id<1: raise Denied("REPO_ID_REQUIRED")
        if not isinstance(repo,str) or repo.count("/")!=1: raise Denied("REPO_REQUIRED")
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?:[./][A-Za-z0-9_-]+)*",branch) or branch in ("main","master"):
            raise Denied("BRANCH_NOT_ALLOWLISTED")
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        if require_service_actor and (not isinstance(service_actor,tuple) or len(service_actor)!=2
                or not isinstance(service_actor[0],str) or type(service_actor[1])!=int):
            raise Denied("EXCLUSIVE_SERVICE_ACTOR_REQUIRED")
        self.service_actor=service_actor or ("Kirion-Jane",335897759)
        self.require_service_actor=require_service_actor
        self.legacy_fixture_mode=legacy_fixture_mode is True
        self.key,self.repo,self.repo_id,self.branch,self.enabled=key,repo,repo_id,branch,enabled
        self.leases=LeaseManager(self.path.with_suffix(".lease.db"))
        self.journal=FactoryJournal(self.path.with_suffix(".forge.db"))
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS ops(
              nonce TEXT PRIMARY KEY,fingerprint TEXT NOT NULL, mission TEXT NOT NULL,
              worker TEXT NOT NULL,branch TEXT NOT NULL,expected TEXT NOT NULL,
              target TEXT NOT NULL,tree TEXT NOT NULL,status TEXT NOT NULL,
              receipt TEXT NOT NULL DEFAULT '{}')""")
            db.execute("""CREATE TABLE IF NOT EXISTS audit(
              seq INTEGER PRIMARY KEY AUTOINCREMENT,event TEXT NOT NULL,
              payload TEXT NOT NULL,prev TEXT NOT NULL,mac TEXT NOT NULL)""")
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,isolation_level=None,timeout=15)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()
    def log(self,db,event,payload):
        row=db.execute("SELECT mac FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev=row["mac"] if row else "0"*64
        msg=encoded({"prev":prev,"event":event,"payload":payload})
        mac=hmac.new(self.key,msg,"sha256").hexdigest()
        db.execute("INSERT INTO audit(event,payload,prev,mac) VALUES(?,?,?,?)",
                   (event,encoded(payload).decode(),prev,mac))
    def valid(self):
        """Reconstruct materialized write state from HMAC-chained events."""
        prev="0"*64
        state={}
        try:
            with self.connect() as db:
                events=list(db.execute("SELECT * FROM audit ORDER BY seq"))
                rows=list(db.execute("SELECT * FROM ops"))
            for row in events:
                if row["prev"]!=prev:return False
                payload=json.loads(row["payload"])
                msg=encoded({"prev":prev,"event":row["event"],"payload":payload})
                mac=hmac.new(self.key,msg,"sha256").hexdigest()
                if not hmac.compare_digest(mac,row["mac"]):return False
                prev=mac
                nonce=payload["nonce"]
                if row["event"]=="RESERVED":
                    req=payload["request"]
                    if nonce in state or fingerprint(req)!=payload["digest"] or req["nonce"]!=nonce:
                        return False
                    state[nonce]={"status":"IN_FLIGHT","digest":payload["digest"],
                                  "request":req,"receipt_digest":None}
                elif row["event"] in ("UNCERTAIN","CONFIRMED","RECONCILED"):
                    if nonce not in state:return False
                    cur=state[nonce]
                    required={"UNCERTAIN":"IN_FLIGHT","CONFIRMED":"IN_FLIGHT",
                              "RECONCILED":"UNKNOWN"}[row["event"]]
                    if row["event"]=="RECONCILED" and cur["status"]=="IN_FLIGHT":
                        required="IN_FLIGHT"  # crash before status update; positive proof still needed
                    if cur["status"]!=required:return False
                    cur["status"]={"UNCERTAIN":"UNKNOWN","CONFIRMED":"DONE",
                                   "RECONCILED":"DONE"}[row["event"]]
                    if row["event"]!="UNCERTAIN":cur["receipt_digest"]=payload["digest"]
                else:return False
            if len(state)!=len(rows):return False
            for row in rows:
                x=state.get(row["nonce"])
                if x is None or x["status"]!=row["status"] or x["digest"]!=row["fingerprint"]:
                    return False
                req=x["request"]
                for col,field in (("mission","mission"),("worker","worker"),
                                  ("branch","branch"),("expected","expected"),
                                  ("target","target"),("tree","tree")):
                    if row[col]!=req[field]:return False
                if req["repo_id"]!=self.repo_id or req["branch"]!=self.branch:
                    return False
                if row["status"]=="DONE":
                    if fingerprint(json.loads(row["receipt"]))!=x["receipt_digest"]:return False
            return self.journal.verify_hash_chain()
        except (KeyError,TypeError,ValueError,sqlite3.DatabaseError):
            return False
    def check_remote(self,packet,expected,actor,repository,head,pr):
        # Explicit role->actor, no generic write capability or legacy Lucien substitution.
        if packet["assigned_persona"]!="Antigravity-Jane" or packet["formal_role"]!="Code Writer":
            raise Denied("OFF_ROLE_DENIED")
        who=actor()
        if (who.get("login"),who.get("id"))!=self.service_actor or type(who.get("id"))!=int:
            raise Denied("ACTOR_SUBSTITUTION")
        if self.require_service_actor and who.get("type")!="Bot":
            raise Denied("ACTOR_SUBSTITUTION")
        rep=repository()
        if rep.get("repository_full_name")!=self.repo or type(rep.get("id"))!=int or rep["id"]!=self.repo_id or rep.get("permissions",{}).get("push") is not True:
            raise Denied("REPOSITORY_OR_ACCESS_DRIFT")
        b=head()
        if b.get("sha")!=expected or not is_valid_git_sha(b.get("tree")):
            raise Denied("BRANCH_HEAD_DRIFT")
        p=pr()
        if p.get("head_sha")!=expected or p.get("draft") is not True or p.get("merged") is not False:
            raise Denied("STALE_OR_UNSAFE_PR")
    def execute(self,*,packet,nonce,worker,paths,expected,target,tree,
                actor,repository,head,pr,mutate,candidate_repo=None):
        if not self.enabled:raise Denied("HOST_MEDIATION_NOT_ACTIVE")
        if not self.valid():raise Denied("AUDIT_OR_JOURNAL_TAMPERED")
        if not isinstance(nonce,str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}",nonce):
            raise Denied("INVALID_NONCE")
        if not all(is_valid_git_sha(v) for v in (expected,target,tree)) or expected==target:
            raise Denied("BAD_EXACT_SHA")
        verify_mission_packet(packet,expected_repo=self.repo,trusted_verifiers={
            "Engineer:Kirch-Ivan-Balite","Maintainer:Kirch-Nairu"})
        if packet.get("base_sha")!=expected:raise Denied("PACKET_BASE_DRIFT")
        assert_operation_allowed(packet,"WRITE_OWNED")
        assert_paths_within_ownership(packet,paths)
        if packet["permitted_branch"]!=self.branch:raise Denied("BRANCH_NOT_ALLOWLISTED")
        if not worker or not isinstance(worker,str):raise Denied("WORKER_REQUIRED")
        payload={"mission":packet["mission_id"],"nonce":nonce,"worker":worker,"repo_id":self.repo_id,
                 "branch":self.branch,"paths":sorted(paths),"expected":expected,"target":target,"tree":tree}
        key=fingerprint(payload)
        with self.connect() as db:
            old=db.execute("SELECT * FROM ops WHERE nonce=?",(nonce,)).fetchone()
            if old:
                if old["fingerprint"]!=key:raise Denied("NONCE_PAYLOAD_REPLAY")
                if old["status"]=="DONE":
                    return {"status":"IDEMPOTENT","receipt":json.loads(old["receipt"])}
                raise Denied("UNCERTAIN_WRITE_REQUIRES_RECONCILIATION")
        self.check_remote(packet,expected,actor,repository,head,pr)
        if self.require_service_actor:
            # No qualified canonical external fence exists in this historical
            # broker. A Bot identity and a callable attribute are insufficient.
            raise Denied("CANONICAL_OPERATIONAL_FENCE_REQUIRED")
        if candidate_repo is None:
            if not self.legacy_fixture_mode:
                raise Denied("OBSERVED_CANDIDATE_REQUIRED")
        else:
            observe_git_candidate(candidate_repo,packet,expected,target,tree,paths)
        self.journal.register_mission(packet)
        self.leases.acquire_leases(packet,worker,ttl_seconds=300)
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT 1 FROM ops WHERE branch=? AND status IN ('IN_FLIGHT','UNKNOWN')",(self.branch,)).fetchone():
                    raise Denied("WRITE_COLLISION")
                db.execute("INSERT INTO ops(nonce,fingerprint,mission,worker,branch,expected,target,tree,status) VALUES(?,?,?,?,?,?,?,?,'IN_FLIGHT')",
                           (nonce,key,packet["mission_id"],worker,self.branch,expected,target,tree))
                self.log(db,"RESERVED",{"nonce":nonce,"digest":key,"request":payload})
                db.execute("COMMIT")
        except BaseException:
            self.leases.release_worker_leases(packet["mission_id"],worker)
            raise
        try:
            self.check_remote(packet,expected,actor,repository,head,pr)
            if candidate_repo is not None:
                observe_git_candidate(candidate_repo,packet,expected,target,tree,paths)
            if getattr(mutate,"cas_enforced",False) is not True:
                raise Denied("REMOTE_CAS_REQUIRED")
            receipt=mutate(expected,target)
            if receipt.get("success") is not True or receipt.get("sha")!=target:
                raise Denied("WRITE_RECEIPT_INVALID")
            observed=head()
            if observed.get("sha")!=target or observed.get("tree")!=tree:
                raise Denied("READBACK_MISMATCH")
        except BaseException:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE ops SET status='UNKNOWN' WHERE nonce=? AND status='IN_FLIGHT'",(nonce,))
                self.log(db,"UNCERTAIN",{"nonce":nonce})
                db.execute("COMMIT")
            # Lease held; never silently retry a possibly completed write.
            raise
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE ops SET status='DONE',receipt=? WHERE nonce=?",(encoded(receipt).decode(),nonce))
            self.log(db,"CONFIRMED",{"nonce":nonce,"digest":fingerprint(receipt)})
            db.execute("COMMIT")
        self.leases.release_worker_leases(packet["mission_id"],worker)
        return {"status":"DONE","receipt":receipt}
    def reconcile(self,nonce,head):
        if not self.enabled or not self.valid():raise Denied("RECONCILE_DISABLED")
        with self.connect() as db:
            row=db.execute("SELECT * FROM ops WHERE nonce=?",(nonce,)).fetchone()
            if row is None or row["status"] not in ("UNKNOWN","IN_FLIGHT"):raise Denied("NO_UNCERTAIN_WRITE")
            observed=head()
            if observed.get("sha")!=row["target"] or observed.get("tree")!=row["tree"]:
                raise Denied("NO_POSITIVE_REMOTE_PROOF")
            receipt={"success":True,"sha":row["target"],"reconciled":True}
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE ops SET status='DONE',receipt=? WHERE nonce=?",(encoded(receipt).decode(),nonce))
            self.log(db,"RECONCILED",{"nonce":nonce,"digest":fingerprint(receipt)})
            db.execute("COMMIT")
        self.leases.release_worker_leases(row["mission"],row["worker"])
        return receipt
