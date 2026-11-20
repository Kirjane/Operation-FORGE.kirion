"""R4 isolated model execution protocol. Defaults OFF; no fabricated model context.

This is a callable contract for host-verified model execution, not a model
launcher provided by ChatGPT. Provider callbacks and signer keys MUST be
outside the model's control and backed by a deployed trustworthy service.
"""
import hashlib
import hmac
import json
import re
import sqlite3
from contextlib import contextmanager
import time
import urllib.request
from pathlib import Path

from integrations.antigravity.factory.authority import verify_mission_packet, is_valid_git_sha
from integrations.antigravity.factory.scheduler import FactoryJournal
from integrations.antigravity.factory.quality import SelfHealingController
from integrations.chatgpt.scoped_broker import encoded, fingerprint, Denied

class HostUnavailable(Denied):
    pass

class OpenAIResponsesTransport:
    """Concrete HTTPS transport; paid API calls disabled unless separately authorized."""
    endpoint="https://api.openai.com/v1/responses"
    def __init__(self,api_key=None,model=None,paid_authorized=False,request=None):
        self.api_key=api_key
        self.model=model
        self.paid_authorized=paid_authorized
        self.request=request or urllib.request.urlopen
    def launch(self,request):
        if not self.paid_authorized or not self.api_key or not self.model:
            raise HostUnavailable("OPENAI_API_AUTHORIZATION_OR_CREDENTIAL_REQUIRED")
        if request.get("tools"):
            raise HostUnavailable("DIRECT_MODEL_TOOL_BINDING_NOT_AUTHORIZED")
        body={"model":self.model,"store":False,"input":[{"role":"user","content":json.dumps(request,sort_keys=True)}],
              "max_output_tokens":800}
        q=urllib.request.Request(self.endpoint,data=encoded(body),headers={
            "Authorization":"Bearer "+self.api_key,"Content-Type":"application/json"},method="POST")
        with self.request(q,timeout=45) as response:
            data=json.loads(response.read())
        if data.get("status")!="completed" or not re.fullmatch(r"resp_[A-Za-z0-9_-]{8,}",data.get("id","")):
            raise HostUnavailable("PROVIDER_RESPONSE_NOT_COMPLETED")
        return {"provider":"openai-responses","provider_context_id":data["id"],
                "provider_response_id":data["id"],"response":data}

class NotionCustomAgentTransport:
    """Actual MCP action wiring once Notion Business/Custom Agents is accessible."""
    def __init__(self,spawn_session=None,wait_session=None,agent_urls=None,entitled=False):
        self.spawn=spawn_session
        self.wait=wait_session
        self.agents=agent_urls or {}
        self.entitled=entitled
    def launch(self,request):
        persona=request["persona"]
        if not self.entitled or not self.spawn or not self.wait:
            raise HostUnavailable("NOTION_CUSTOM_AGENT_ENTITLEMENT_OR_BINDING_REQUIRED")
        url=self.agents.get(persona)
        if not isinstance(url,str) or not re.fullmatch(r"agent://[A-Za-z0-9_-]+/[A-Za-z0-9_-]+",url):
            raise HostUnavailable("APPROVED_PUBLISHED_AGENT_REQUIRED")
        started=self.spawn(agent_url=url,initial_message=json.dumps(request,sort_keys=True))
        session=started.get("session_url")
        if not isinstance(session,str) or not re.fullmatch(r"session://[A-Za-z0-9_-]+/[A-Za-z0-9_-]+",session):
            raise HostUnavailable("NO_PROVIDER_SESSION_ID")
        result=self.wait(session_url=session,seconds=60)
        if result.get("status")!="completed" or result.get("session_url")!=session:
            raise HostUnavailable("SESSION_NOT_COMPLETED")
        return {"provider":"notion-custom-agent","provider_context_id":session,
                "provider_response_id":result.get("turn_id"),"response":result}

class IsolatedOrchestrator:
    """Trusts only host-signed envelopes from an external execution boundary.

    Even distinct signed context IDs cannot alone prove a genuinely isolated
    reasoning environment; host owner must attest runtime isolation policy.
    """
    def __init__(self,path,verify_key,transport=None,activated=False,offline_test_mode=False):
        if not isinstance(verify_key,bytes) or len(verify_key)<32:raise Denied("HOST_VERIFY_KEY_REQUIRED")
        self.key=verify_key
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.transport=transport
        self.activated=activated
        self.offline_test_mode=offline_test_mode
        self.journal=FactoryJournal(self.path.with_suffix(".canonical.db"))
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS contexts(
              nonce TEXT PRIMARY KEY,request_hash TEXT NOT NULL,
              mission TEXT NOT NULL,persona TEXT NOT NULL,repo_id INTEGER NOT NULL,
              sha TEXT NOT NULL,state TEXT NOT NULL,
              provider_id TEXT,receipt TEXT NOT NULL DEFAULT '{}')""")
        with self.connect() as db:
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS unique_host_context ON contexts(provider_id) WHERE provider_id IS NOT NULL")
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
    def valid_receipts(self):
        """Verify signed service claims against materialized rows and canonical dispatch events."""
        if not self.journal.verify_hash_chain():return False
        try:
            with self.connect() as db:
                rows=list(db.execute("SELECT * FROM contexts"))
            completed={}
            for row in rows:
                if row["state"]=="COMPLETED":
                    receipt=json.loads(row["receipt"])
                    claims=receipt["claims"]; signature=receipt["signature"]
                    if not isinstance(signature,str) or not hmac.compare_digest(
                            hmac.new(self.key,encoded(claims),"sha256").hexdigest(),signature):
                        return False
                    if claims.get("context_id")!=row["provider_id"] or claims.get("request_sha256")!=row["request_hash"]:
                        return False
                    if claims.get("sha")!=row["sha"] or claims.get("persona")!=row["persona"] or claims.get("repo_id")!=row["repo_id"]:
                        return False
                    completed[(row["request_hash"],row["provider_id"])]=True
                elif row["state"] not in ("IN_FLIGHT","UNKNOWN") or row["provider_id"] is not None:
                    return False
            canonical={(e["payload"]["dispatch_key"],e["payload"]["context_id"]) for e in self.journal.list_events()
                       if e["event_type"]=="WORKER_DISPATCHED"}
            return set(completed)==canonical
        except (KeyError,TypeError,ValueError,sqlite3.DatabaseError):
            return False

    def launch(self,packet,*,repo_id,sha,nonce,expected_actor,previous_context=None,now=None):
        if not self.activated or self.transport is None:
            raise HostUnavailable("NO_AUTHORIZED_ISOLATED_MODEL_SERVICE")
        if not self.valid_receipts():
            raise Denied("SIGNED_CONTEXT_OR_CANONICAL_JOURNAL_INVALID")
        verify_mission_packet(packet,trusted_verifiers={
            "Engineer:Kirch-Ivan-Balite","Maintainer:Kirch-Nairu"})
        if type(repo_id)!=int or repo_id<1 or not is_valid_git_sha(sha):
            raise Denied("BAD_REPO_OR_SHA")
        role=packet["formal_role"]; persona=packet["assigned_persona"]
        expected={"Antigravity-Jane":("Code Writer","Kirion-Jane",335897759),
                  "Antigravity-Nox":("Reviewer","Kirion-Nox",339503629)}
        if persona not in expected or role!=expected[persona][0] or tuple(expected_actor)!=expected[persona][1:]:
            raise Denied("ACTOR_PERSONA_SUBSTITUTION")
        if not isinstance(nonce,str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}",nonce):
            raise Denied("NONCE_INVALID")
        if role=="Reviewer" and not previous_context:
            raise Denied("REVIEW_REQUIRES_FROZEN_AUTHOR_CONTEXT")
        if role=="Reviewer" and "REVIEW_READONLY" not in packet["allowed_operations"]:
            raise Denied("REVIEW_NOT_READONLY")
        req={"mission":packet["mission_id"],"packet_sha256":fingerprint(packet),
             "repo":packet["repo_name"],"repo_id":repo_id,"sha":sha,
             "persona":persona,"formal_role":role,"nonce":nonce,
             "previous_context":previous_context or None,"max_simultaneous":3,
             "no_promote":True,"model_tool_writes":False}
        h=fingerprint(req)
        current=int(now if now is not None else time.time())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old=db.execute("SELECT 1 FROM contexts WHERE nonce=?",(nonce,)).fetchone()
            if old:raise Denied("CONTEXT_NONCE_REPLAY")
            active=db.execute("SELECT COUNT(*) FROM contexts WHERE state='IN_FLIGHT'").fetchone()[0]
            if active>=2:raise Denied("MAX_THREE_INCLUDING_PRIMARY")
            db.execute("""INSERT INTO contexts(nonce,request_hash,mission,persona,repo_id,sha,state)
                          VALUES(?,?,?,?,?,?,'IN_FLIGHT')""",(nonce,h,packet["mission_id"],persona,repo_id,sha))
            db.execute("COMMIT")
        try:
            # Transport callable MUST be a trusted host bridge; never a model-generated JSON tool result.
            received=self.transport(req) if callable(self.transport) else self.transport.launch(req)
            claims=received["host_claims"]
            signature=received["host_signature"]
            if not isinstance(claims,dict) or not isinstance(signature,str):
                raise Denied("NO_HOST_ATTESTATION")
            computed=hmac.new(self.key,encoded(claims),"sha256").hexdigest()
            if not hmac.compare_digest(computed,signature):
                raise Denied("HOST_ATTESTATION_INVALID")
            ctx=claims.get("context_id","")
            if not isinstance(ctx,str) or not re.fullmatch(r"[A-Za-z0-9_:./-]{10,256}",ctx):
                raise Denied("NO_PROVIDER_CONTEXT_ID")
            if claims.get("request_sha256")!=h or claims.get("repo_id")!=repo_id or claims.get("sha")!=sha or claims.get("persona")!=persona:
                raise Denied("ATTESTED_SCOPE_MISMATCH")
            simulated=claims.get("mock_only") is True
            if simulated:
                if not self.offline_test_mode or claims.get("runtime_isolated") is not False:
                    raise Denied("MOCK_MODEL_MUST_NOT_ATTEST_ISOLATION")
            elif claims.get("runtime_isolated") is not True:
                raise Denied("ISOLATION_NOT_ATTESTED")
            if claims.get("provider") not in ("notion-custom-agent","openai-responses"):
                raise Denied("PROVIDER_NOT_ALLOWLISTED")
            if type(claims.get("expires_at")) is not int or claims["expires_at"]<=current or claims["expires_at"]>current+3600:
                raise Denied("ATTESTATION_EXPIRED_OR_UNBOUNDED")
            if role=="Reviewer" and ctx==previous_context:
                raise Denied("REVIEW_SAME_CONTEXT")
            if not claims.get("provider_request_id") or not claims.get("output_sha256"):
                raise Denied("MISSING_PROVENANCE")
            if not re.fullmatch(r"[0-9a-f]{64}",claims["output_sha256"]):
                raise Denied("UNHASHED_OUTPUT")
            # Model-authored output is an untrusted artifact; not a gate verdict.
            summary={"status":"MOCK_CONTEXT_NON_ACCEPTING" if simulated else "ISOLATED_CONTEXT_ATTESTED","context_id":ctx,
                     "provider":claims["provider"],"request_digest":h,
                     "output_sha256":claims["output_sha256"],"non_accepting":True}
            self.journal.register_mission(packet)
            was_cached,_=self.journal.record_idempotent_dispatch(
                h,packet["mission_id"],persona,ctx,summary)
            if was_cached:raise Denied("CANONICAL_DISPATCH_REPLAY")
            with self.connect() as db:
                db.execute("UPDATE contexts SET state='COMPLETED',provider_id=?,receipt=? WHERE nonce=?",
                           (ctx,encoded({"claims":claims,"signature":signature}).decode(),nonce))
            return summary
        except BaseException:
            with self.connect() as db:
                db.execute("UPDATE contexts SET state='UNKNOWN' WHERE nonce=? AND state='IN_FLIGHT'",(nonce,))
            raise
    def reconcile_launch(self,packet,*,nonce,verified_receipt,previous_context=None,now=None):
        """Recover a timed-out launch from a trusted service receipt; never re-invoke model."""
        if not self.activated or not self.journal.verify_hash_chain():
            raise Denied("RECOVERY_HOST_NOT_AUTHORIZED")
        verify_mission_packet(packet,trusted_verifiers={
            "Engineer:Kirch-Ivan-Balite","Maintainer:Kirch-Nairu"})
        with self.connect() as db:
            row=db.execute("SELECT * FROM contexts WHERE nonce=?",(nonce,)).fetchone()
        if row is None or row["state"] not in ("UNKNOWN","IN_FLIGHT") or row["mission"]!=packet["mission_id"]:
            raise Denied("NO_RECOVERABLE_CONTEXT")
        if not isinstance(verified_receipt,dict):
            raise Denied("INVALID_RECOVERY_PACKET")
        # Reconstruct the exact original launch request. A valid host signature
        # alone cannot authorize substituting a mission packet on recovery.
        if packet["formal_role"]=="Reviewer" and not previous_context:
            raise Denied("RECOVERY_REVIEWER_AUTHOR_CONTEXT_REQUIRED")
        original_request={
            "mission":packet["mission_id"],"packet_sha256":fingerprint(packet),
            "repo":packet["repo_name"],"repo_id":row["repo_id"],
            "sha":row["sha"],"persona":row["persona"],
            "formal_role":packet["formal_role"],"nonce":nonce,
            "previous_context":previous_context or None,"max_simultaneous":3,
            "no_promote":True,"model_tool_writes":False,
        }
        if fingerprint(original_request)!=row["request_hash"]:
            raise Denied("RECOVERY_PACKET_OR_CONTEXT_DRIFT")
        claims=verified_receipt.get("host_claims")
        sig=verified_receipt.get("host_signature")
        if not isinstance(claims,dict) or not isinstance(sig,str) or not hmac.compare_digest(
                hmac.new(self.key,encoded(claims),"sha256").hexdigest(),sig):
            raise Denied("RECOVERY_SIGNATURE_INVALID")
        ctx=claims.get("context_id")
        current=int(now if now is not None else time.time())
        if not isinstance(ctx,str) or not re.fullmatch(r"[A-Za-z0-9_:./-]{10,256}",ctx):
            raise Denied("RECOVERY_CONTEXT_INVALID")
        if (claims.get("request_sha256")!=row["request_hash"] or
            claims.get("sha")!=row["sha"] or claims.get("repo_id")!=row["repo_id"] or
            claims.get("persona")!=row["persona"] or claims.get("runtime_isolated") is not True or
            claims.get("provider") not in ("openai-responses","notion-custom-agent") or
            claims.get("expires_at",0)<=current or claims.get("expires_at",0)>current+3600 or
            (previous_context is not None and ctx==previous_context)):
            raise Denied("RECOVERY_CLAIMS_DRIFT_OR_EXPIRED")
        summary={"status":"ISOLATED_CONTEXT_ATTESTED","context_id":ctx,
                 "provider":claims["provider"],"request_digest":row["request_hash"],
                 "output_sha256":claims["output_sha256"],"non_accepting":True}
        self.journal.register_mission(packet)
        cached,prior=self.journal.record_idempotent_dispatch(
            row["request_hash"],packet["mission_id"],row["persona"],ctx,summary)
        if cached and prior!=summary:
            raise Denied("RECOVERY_DISPATCH_CONFLICT")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE contexts SET state='COMPLETED',provider_id=?,receipt=? WHERE nonce=? AND state IN ('UNKNOWN','IN_FLIGHT')",
                       (ctx,encoded({"claims":claims,"signature":sig}).decode(),nonce))
            db.execute("COMMIT")
        if not self.valid_receipts():raise Denied("RECOVERY_LEDGER_INVALID")
        return summary
    def repair_controller(self):
        return SelfHealingController(max_repair_cycles=5,max_identical_retries=2)
