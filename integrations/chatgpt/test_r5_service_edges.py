"""R5 single-operation ASGI, durable recovery and bounded rework regression tests.

All tests use synthetic local Git, mocked model and zero paid/provider calls.
"""
import asyncio
import json
import pathlib
import sqlite3
import unittest

from integrations.chatgpt.test_engineering_service import R5Fixture, KEY, REPO, REPO_ID, FILE
from integrations.chatgpt.operator_asgi import ForgeOperatorASGI
from integrations.chatgpt.scoped_broker import fingerprint, Denied
from integrations.chatgpt.engineering_service import SignedEngineeringDispatch

class R5ServiceEdges(R5Fixture):
    def call_http(self, *, enabled, nonce="r5-asgi-single-call", auth=None,
                  operation=None, extra_bytes=0,method="POST"):
        payload={"writer_packet":self.packet,"reviewer_packet":self.review,
                 "source_sha":self.sha,"source_tree":self.tree,
                 "source_paths":[FILE],"task":"Fix synthetic stock debit",
                 "nonce_prefix":nonce,"repo_id":REPO_ID}
        if operation:payload.update(operation)
        data=json.dumps(payload).encode()+b" "*extra_bytes
        app=ForgeOperatorASGI(self.service,bearer_secret=KEY,enabled=enabled)
        events=[]
        async def receive():
            return {"type":"http.request","body":data,"more_body":False}
        async def send(event):
            events.append(event)
        asyncio.run(app({"type":"http","method":method,"path":"/v1/forge/execute",
                        "headers":[(b"content-type",b"application/json"),
                                   (b"authorization",auth if auth is not None else b"Bearer "+KEY)]},
                       receive,send))
        return events[0]["status"],json.loads(events[1]["body"])
    def test_single_request_runs_both_personas_and_broker(self):
        status,result=self.call_http(enabled=True)
        self.assertEqual(status,200)
        self.assertEqual(result["acceptance"],"NOT_ACCEPTED")
        self.assertEqual(result["result"]["gate_status"],"MOCK_NON_ACCEPTING")
        self.assertEqual(self.remote.cas_count,1)
        self.assertGreaterEqual(self.model.calls,4)
    def test_default_host_disabled(self):
        status,data=self.call_http(enabled=False)
        self.assertEqual(status,503)
        self.assertEqual(data["error"],"R5_HOST_ACTIVATION_REQUIRED")
        self.assertEqual(self.model.calls,0)
    def test_unauthorized_bearer_cannot_dispatch(self):
        status,data=self.call_http(enabled=True,auth=b"Bearer wrong")
        self.assertEqual(status,401)
        self.assertEqual(self.model.calls,0)
    def test_arbitrary_remote_write_route_denied(self):
        status,data=self.call_http(enabled=True,operation={"github.update_ref":{"sha":"f"*40}})
        self.assertEqual(status,403)
        self.assertEqual(self.model.calls,0)
    def test_overlong_body_denied_before_token_use(self):
        status,data=self.call_http(enabled=True,extra_bytes=70000)
        self.assertEqual(status,413)
        self.assertEqual(self.model.calls,0)
    def test_get_method_denied(self):
        status,_=self.call_http(enabled=True,method="GET")
        self.assertEqual(status,404)
        self.assertEqual(self.model.calls,0)
    def test_vault_survives_new_service_instance(self):
        self.runpilot()
        nonce="r5-local-test-jane-000"
        v=self.dispatch.durable(nonce)
        reused=SignedEngineeringDispatch(self.runner,KEY,
                         vault_path=pathlib.Path(self.temp.name)/"output-vault.db")
        self.assertEqual(reused.durable(nonce),v)
        with self.assertRaisesRegex(Denied,"DURABLE_DISPATCH_NONCE_REPLAY"):
            reused.register(nonce,self.context())
    def test_tampered_persisted_model_receipt_denied(self):
        self.runpilot()
        with sqlite3.connect(self.dispatch.vault_path) as db:
            db.execute("UPDATE signed_results SET record_json=?",
                       ('{"forged":true}',))
        with self.assertRaisesRegex(Denied,"SERVICE_RESULT_VAULT_TAMPERED"):
            self.dispatch.durable("r5-local-test-jane-000")
    def test_recover_signed_output_without_second_inference(self):
        nonce="r5-recovered-writer-0001"
        packet=self.packet
        request={"mission":packet["mission_id"],"packet_sha256":fingerprint(packet),
                 "repo":REPO,"repo_id":REPO_ID,"sha":self.sha,
                 "persona":"Antigravity-Jane","formal_role":"Code Writer",
                 "nonce":nonce,"previous_context":None,"max_simultaneous":3,
                 "no_promote":True,"model_tool_writes":False}
        with self.host.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO contexts
              (nonce,request_hash,mission,persona,repo_id,sha,state)
              VALUES(?,?,?,?,?,?,'UNKNOWN')""",
              (nonce,fingerprint(request),packet["mission_id"],"Antigravity-Jane",
               REPO_ID,self.sha))
            db.execute("COMMIT")
        self.dispatch.register(nonce,self.context())
        self.dispatch(request)
        calls=self.model.calls
        out=self.service.recover_role(packet,nonce=nonce)
        self.assertEqual(self.model.calls,calls)
        self.assertEqual(out["model_output_sha256"],
                         self.dispatch.durable(nonce)["signed"]["host_claims"]["output_sha256"])
        self.assertTrue(self.host.valid_receipts())
        with self.assertRaisesRegex(Denied,"NO_RECOVERABLE_CONTEXT"):
            self.service.recover_role(packet,nonce=nonce)
    def test_nox_rework_triggers_fresh_bounded_cycle(self):
        self.model.return_rework_once=True
        evidence=self.runpilot()
        self.assertEqual(evidence["gate_status"],"MOCK_NON_ACCEPTING")
        self.assertEqual(self.remote.cas_count,2)
        self.assertEqual(len(evidence["repair_attempts"]),2)
        self.assertEqual(self.model.review_count,2)
        self.assertTrue(self.host.valid_receipts())
        self.assertTrue(self.broker.valid())
    def test_mock_claims_explicitly_not_runtime_isolated(self):
        self.runpilot()
        with self.host.connect() as db:
            raw=db.execute("SELECT receipt FROM contexts WHERE persona='Antigravity-Nox'").fetchone()[0]
        claims=json.loads(raw)["claims"]
        self.assertFalse(claims["runtime_isolated"])
        self.assertTrue(claims["mock_only"])
    def test_nox_can_read_public_tests_but_not_hidden_oracle(self):
        self.runpilot()
        payloads=[json.loads(m[1]["content"]) for m in self.model.prompts]
        nox=[p for p in payloads if p["phase"]=="Antigravity-Nox"]
        self.assertTrue(nox)
        self.assertTrue(all("tests/public.php" in p["available_source_files"] for p in nox))
        self.assertTrue(all("oracles/hidden.php" not in p["available_source_files"] for p in nox))

if __name__=="__main__":unittest.main()
