"""R4 scoped mutation broker. Not installed as a host-global GitHub interceptor.

All writes must pass a trusted remote atomic-CAS adapter. Direct ChatGPT GitHub
tool calls still bypass this module, so HOST_ENFORCEMENT remains BLOCKED.
"""
import hashlib
import hmac
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from integrations.antigravity.factory.authority import verify_mission_packet, is_valid_git_sha
from integrations.antigravity.factory.ownership import LeaseManager
from integrations.antigravity.factory.scheduler import FactoryJournal
from integrations.antigravity.factory.policy import assert_operation_allowed, assert_paths_within_ownership

class Denied(PermissionError):
    pass

def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()

def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()

class ScopedBroker:
    """Local executable broker proof. Remote actor/read/write methods are trusted inputs."""
    def __init__(self,path,key,repo,repo_id,branch,enabled=False):
        if not isinstance(key,bytes) or len(key)<32: raise Denied("AUDIT_KEY_REQUIRED")
        if type(repo_id)!=int or repo_id<1: raise Denied("REPO_ID_REQUIRED")
        if not isinstance(repo,str) or repo.count("/")!=1: raise Denied("REPO_REQUIRED")
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?:[./][A-Za-z0-9_-]+)*",branch) or branch in ("main","master"):
            raise Denied("BRANCH_NOT_ALLOWLISTED")
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
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
        prev="0"*64
        with self.connect() as db:
            for row in db.execute("SELECT * FROM audit ORDER BY seq"):
                if row["prev"]!=prev:return False
                msg=encoded({"prev":prev,"event":row["event"],"payload":json.loads(row["payload"])})
                mac=hmac.new(self.key,msg,"sha256").hexdigest()
                if not hmac.compare_digest(mac,row["mac"]):return False
                prev=mac
        return self.journal.verify_hash_chain()
    def check_remote(self,packet,expected,actor,repository,head,pr):
        # Explicit role->actor, no generic write capability or legacy Lucien substitution.
        if packet["assigned_persona"]!="Antigravity-Jane" or packet["formal_role"]!="Code Writer":
            raise Denied("OFF_ROLE_DENIED")
        who=actor()
        if who.get("login")!="Kirion-Jane" or type(who.get("id"))!=int or who["id"]!=335897759:
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
                actor,repository,head,pr,mutate):
        if not self.enabled:raise Denied("HOST_MEDIATION_NOT_ACTIVE")
        if not self.valid():raise Denied("AUDIT_OR_JOURNAL_TAMPERED")
        if not isinstance(nonce,str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}",nonce):
            raise Denied("INVALID_NONCE")
        if not all(is_valid_git_sha(v) for v in (expected,target,tree)) or expected==target:
            raise Denied("BAD_EXACT_SHA")
        verify_mission_packet(packet,expected_repo=self.repo,trusted_verifiers={
            "Engineer:Kirch-Ivan-Balite","Maintainer:Kirch-Nairu"})
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
        self.journal.register_mission(packet)
        self.leases.acquire_leases(packet,worker,ttl_seconds=300)
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT 1 FROM ops WHERE branch=? AND status IN ('IN_FLIGHT','UNKNOWN')",(self.branch,)).fetchone():
                    raise Denied("WRITE_COLLISION")
                db.execute("INSERT INTO ops(nonce,fingerprint,mission,worker,branch,expected,target,tree,status) VALUES(?,?,?,?,?,?,?,?,'IN_FLIGHT')",
                           (nonce,key,packet["mission_id"],worker,self.branch,expected,target,tree))
                self.log(db,"RESERVED",{"nonce":nonce,"digest":key})
                db.execute("COMMIT")
        except BaseException:
            self.leases.release_worker_leases(packet["mission_id"],worker)
            raise
        try:
            self.check_remote(packet,expected,actor,repository,head,pr)
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
            if row is None or row["status"]!="UNKNOWN":raise Denied("NO_UNCERTAIN_WRITE")
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
