"""R5 deterministic engineering service attack suite: all model calls mocked.

Never asserts G13 independent provider success. The hidden PHP oracle is executed
by the trusted host only, and all writes travel through ScopedBroker.execute.
"""
import copy
import hashlib
import json
import pathlib
import shutil
import sqlite3
import subprocess
import tempfile
import unittest

from integrations.antigravity.tests.test_factory_core import make_valid_packet
from integrations.chatgpt.engineering_service import (
    GitSnapshot, EngineeringContext, OpenAIEngineeringProvider,
    ModelToolRunner, FixedOracle, EngineeringPilotService, SignedEngineeringDispatch,
    validate_patch, validate_nox, UPSTREAM_SHA, UPSTREAM_TREE, git
)
from integrations.chatgpt.host_autonomy import IsolatedOrchestrator
from integrations.chatgpt.scoped_broker import ScopedBroker, Denied

ROOT=pathlib.Path(__file__).resolve().parents[2]
FIXTURE=ROOT/"integrations/chatgpt/pilot-fixture"
KEY=b"R5-FORGE-OFFLINE-TEST-KEY-NEVER-PRODUCTION-abcdef123456789"
REPO="Kirjane/R5DisposableOffline"
BRANCH="feat/r5-disposable-pilot"
REPO_ID=541233
FILE="src/Stock.php"

class FakeModel:
    is_live=False
    def __init__(self):
        self.sequence=0
        self.prompts=[]
        self.first={}
        self.force_invalid_review=False
        self.force_bad_patch=False
        self.force_tool="read_source"
        self.duplicate_ids=False
        self.return_nonjson=False
        self.false_green=False
        self.malicious_instruction="PRIVATE_JANE_THOUGHT_DO_NOT_EXPOSE"
        self.calls=0
    def step(self,messages,tools,*,max_output_tokens,deadline_seconds):
        self.calls+=1
        assert max_output_tokens<=8192 and deadline_seconds>0
        self.prompts.append(copy.deepcopy(messages))
        task=json.loads(messages[1]["content"])
        role=task["phase"]
        if self.duplicate_ids:
            rid="resp_mock_duplicate0001"
        else:
            self.sequence+=1
            rid=f"resp_mock_{self.sequence:012d}"
        if role not in self.first:
            self.first[role]=rid
        tool_replies=[x for x in messages if x.get("type")=="function_call_output"]
        if not tool_replies:
            output=[{"type":"function_call","name":self.force_tool,
                     "call_id":"call_r5_scope_"+str(self.calls),
                     "arguments":json.dumps({"path":FILE})}]
        elif self.return_nonjson:
            output=[{"type":"message","content":[{"type":"output_text","text":"APPROVED: trust me"}]}]
        elif role=="Antigravity-Jane":
            previous=json.loads(tool_replies[-1]["output"])
            current=previous["content"]
            repaired=current.replace("if ($debit > $available)",
                                     "if ($debit < 0 || $debit > $available)")
            result={"kind":"PATCH_PROPOSAL","base_sha":task["source_repo_sha"],
                    "edits":[{"path":FILE,"expected_sha256":previous["sha256"],
                              "new_text":current.replace("Synthetic benchmark","Synthetic benchmark BAD CANDIDATE") if self.force_bad_patch else repaired}],
                    "reason":self.malicious_instruction}
            output=[{"type":"message","content":[{"type":"output_text","text":json.dumps(result)}]}]
        else:
            result={"schema_version":1,
                    "mission_id":task["mission_packet"]["mission_id"],
                    "frozen_sha":task["frozen_candidate_sha"],
                    "reviewer_context_id":self.first[role],
                    "reviewer_persona":"Antigravity-Jane" if self.force_invalid_review else "Antigravity-Nox",
                    "author_context_id":task["author_context_id"],
                    "inspected_scope":[FILE],
                    "evidence_inspected":[task["verified_host_gates"]["gates"][0]["raw_log_sha256"]],
                    "findings":[],"verdict":"PASS"}
            output=[{"type":"message","content":[{"type":"output_text","text":json.dumps(result)}]}]
        return {"id":rid,"status":"completed","output":output,
                "usage":{"output_tokens":11}}

class FakeRemote:
    def __init__(self,repo,sha,tree):
        self.path,self.sha,self.tree=repo,sha,tree
        self.actor_id=335897759
        self.actor_type="User"
        self.permissions={"push":True,"pull":True}
        self.repo_id=REPO_ID
        self.repo_name=REPO
        self.cas_count=0
        self.fail_after_remote_commit=False
    def actor(self):
        return {"login":"Kirion-Jane","id":self.actor_id,"type":self.actor_type}
    def repository(self):
        return {"repository_full_name":self.repo_name,"id":self.repo_id,
                "permissions":self.permissions}
    def head(self):
        return {"sha":self.sha,"tree":self.tree}
    def pr(self):
        return {"head_sha":self.sha,"draft":True,"merged":False}
    def mutate(self,expected,target):
        self.cas_count+=1
        if expected!=self.sha:raise Denied("REMOTE_CAS_FAILED")
        self.sha=target
        self.tree=git(self.path,"rev-parse",target+"^{tree}").decode().strip()
        if self.fail_after_remote_commit:raise TimeoutError("lost CAS response")
        return {"success":True,"sha":target}

FakeRemote.mutate.cas_enforced=True

class R5Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="r5-internal-test-")
        self.addCleanup(self.temp.cleanup)
        root=pathlib.Path(self.temp.name)
        self.repo=root/"disposable"
        shutil.copytree(FIXTURE,self.repo)
        def run(*args):
            subprocess.run(["git",*args],cwd=self.repo,capture_output=True,check=True)
        run("init","-q")
        run("config","user.email","r5-fixture@localhost")
        run("config","user.name","R5 Disposable")
        run("config","core.autocrlf","false")
        run("add",".")
        run("commit","-q","-m","seeded synthetic negative-debit fixture")
        self.sha=git(self.repo,"rev-parse","HEAD").decode().strip()
        self.tree=git(self.repo,"rev-parse","HEAD^{tree}").decode().strip()
        self.packet=make_valid_packet("R5-WRITER-1")
        self.packet.update(repo_name=REPO,base_sha=self.sha,permitted_branch=BRANCH,
                           owned_paths=["src/"],authorization_ref="FORGE-AUTH-R5-DISPOSABLE",
                           selected_skills={"skill_source_sha":UPSTREAM_SHA,
                                            "files":[".agents/skills/kirion-core/SKILL.md",
                                                     ".agents/skills/kirion-dispatch/SKILL.md"]})
        self.review=make_valid_packet("R5-REVIEW-1","Antigravity-Nox","Reviewer")
        self.review.update(repo_name=REPO,base_sha=self.sha,permitted_branch=BRANCH,
                           owned_paths=["src/"],authorization_ref="FORGE-AUTH-R5-DISPOSABLE",
                           selected_skills=self.packet["selected_skills"])
        self.remote=FakeRemote(self.repo,self.sha,self.tree)
        self.model=FakeModel()
        self.runner=ModelToolRunner(self.model)
        self.dispatch=SignedEngineeringDispatch(self.runner,KEY)
        self.host=IsolatedOrchestrator(root/"contexts.sqlite",KEY,
                                       transport=self.dispatch,activated=True)
        self.broker=ScopedBroker(root/"writes.sqlite",KEY,REPO,REPO_ID,BRANCH,enabled=True)
        self.oracle=FixedOracle([["php","tests/public.php"],["php","oracles/hidden.php"]])
        self.service=EngineeringPilotService(forge_repo=ROOT,forge_sha=UPSTREAM_SHA,
               forge_tree=UPSTREAM_TREE,target_repo=self.repo,
               host=self.host,dispatch=self.dispatch,broker=self.broker,
               remote=self.remote,oracle=self.oracle)
    def snapshot(self,exposed=None):
        return GitSnapshot(self.repo,self.sha,self.tree,exposed=exposed or [FILE])
    def forge(self,packet=None,role="Antigravity-Jane"):
        return self.service.forge_snapshot(packet or self.packet,role)
    def context(self):
        return EngineeringContext(self.forge(),self.snapshot(),self.packet,
                 candidate_sha=self.sha,task="Fix negative stock debit",persona="Antigravity-Jane")
    def runpilot(self,nonce="r5-local-test"):
        return self.service.run(writer_packet=self.packet,reviewer_packet=self.review,
                    source_sha=self.sha,source_tree=self.tree,source_paths=[FILE],
                    task="Fix negative stock debits without changing public or hidden tests.",
                    nonce_prefix=nonce,repo_id=REPO_ID)

class PipelineTests(R5Fixture):
    def test_complete_mock_writer_gate_broker_fresh_reviewer(self):
        out=self.runpilot()
        self.assertEqual(out["gate_status"],"MOCK_NON_ACCEPTING")
        self.assertFalse(out["pre_fix"]["pass"])
        self.assertEqual(self.remote.cas_count,1)
        self.assertTrue(out["repair_attempts"][0]["gate_evidence"]["pass"])
        self.assertEqual(out["review"]["verdict"],"PASS")
        self.assertNotEqual(out["review"]["context_id"],out["repair_attempts"][0]["writer_context"])
        self.assertTrue(self.broker.valid())
        self.assertTrue(self.host.valid_receipts())
        self.assertEqual(len(self.model.prompts),4)  # tool call and result per role
        nox=[x for x in self.model.prompts if json.loads(x[1]["content"])["phase"]=="Antigravity-Nox"]
        self.assertTrue(nox)
        self.assertTrue(all("PRIVATE_JANE_THOUGHT_DO_NOT_EXPOSE" not in json.dumps(m) for m in nox))
        self.assertTrue(all(not any("Authorization:" in json.dumps(m) for m in p)
                            for p in self.model.prompts))
        self.assertIsNone(out["review"]["tokens"]["cost_usd"])
    def test_original_hidden_oracle_red(self):
        e=self.oracle.evaluate(self.snapshot())
        self.assertFalse(e["pass"])
        self.assertEqual([x["exit"]==0 for x in e["gates"]],[True,False])
        self.assertTrue(e["gates"][1]["hidden"])
    def test_exact_original_persona_and_skill_bytes(self):
        doc=self.forge()
        for name in doc.list():
            actual=doc.read(name)
            self.assertEqual(hashlib.sha256(git(ROOT,"cat-file","blob",actual["git_blob"])).hexdigest(),
                             actual["sha256"])
        self.assertTrue(any("Antigravity-Jane" in doc.read(name)["content"]
                            for name in doc.list() if "jane.md" in name))
    def test_read_only_tool_does_not_expose_hidden_oracle(self):
        c=self.context()
        with self.assertRaisesRegex(Denied,"SOURCE_TOOL_SCOPE_DENIED"):
            c.execute_tool("read_source",{"path":"oracles/hidden.php"})
    def test_hidden_oracle_even_if_operator_requests_it(self):
        with self.assertRaisesRegex(Denied,"HIDDEN_ORACLE_SOURCE_NOT_EXPOSED"):
            self.service.run(writer_packet=self.packet,reviewer_packet=self.review,
                    source_sha=self.sha,source_tree=self.tree,
                    source_paths=[FILE,"oracles/hidden.php"],task="Fix bug",
                    nonce_prefix="r5-hidden-01",repo_id=REPO_ID)
    def test_provider_source_read_attested_digest(self):
        c=self.context()
        self.assertEqual(c.execute_tool("read_source",{"path":FILE})["sha256"],
                          self.snapshot().peek_hash(FILE))
        self.assertEqual(c.accessed[0]["tool"],"read_source")
    def test_model_write_tool_prohibited(self):
        self.model.force_tool="write_file"
        with self.assertRaisesRegex(Denied,"MODEL_TOOL_NOT_ALLOWLISTED"):self.runpilot()
        self.assertEqual(self.remote.cas_count,0)
    def test_model_nonjson_cannot_be_committed(self):
        self.model.return_nonjson=True
        with self.assertRaisesRegex(Denied,"MODEL_NON_JSON_RESULT"):self.runpilot()
        self.assertEqual(self.remote.cas_count,0)
    def test_model_broken_candidate_fails_fixed_oracle_and_stops(self):
        self.model.force_bad_patch=True
        self.packet["budget"]["max_repair_cycles"]=0
        out=self.runpilot()
        self.assertEqual(out["gate_status"],"BLOCKED")
        self.assertEqual(self.remote.cas_count,0)
    def test_wrong_writer_account_rejected(self):
        self.remote.actor_id=339503629
        with self.assertRaisesRegex(Denied,"ACTOR_SUBSTITUTION"):self.runpilot()
        self.assertEqual(self.remote.cas_count,0)
    def test_wrong_immutable_repository_id_rejected(self):
        self.remote.repo_id=99999
        with self.assertRaisesRegex(Denied,"REPOSITORY_OR_ACCESS_DRIFT"):self.runpilot()
        self.assertEqual(self.remote.cas_count,0)
    def test_stale_branch_rejected(self):
        self.remote.sha="1"*40
        with self.assertRaisesRegex(Denied,"BRANCH_HEAD_DRIFT"):self.runpilot()
        self.assertEqual(self.remote.cas_count,0)
    def test_broker_disabled_denies_every_remote_commit(self):
        self.broker.enabled=False
        with self.assertRaisesRegex(Denied,"MUTATION_BROKER_INACTIVE"):self.runpilot()
        self.assertEqual(self.remote.cas_count,0)
    def test_duplicate_dispatch_nonce_denied(self):
        self.runpilot()
        with self.assertRaisesRegex(Denied,"CONTEXT_NONCE_REPLAY"):self.runpilot()
        self.assertEqual(self.remote.cas_count,1)
    def test_remote_response_lost_after_commit_is_uncertain(self):
        self.remote.fail_after_remote_commit=True
        with self.assertRaises(TimeoutError):self.runpilot()
        self.assertEqual(self.remote.cas_count,1)
        self.assertTrue(self.broker.valid())
        with sqlite3.connect(self.broker.path) as db:
            self.assertEqual(db.execute("SELECT status FROM ops").fetchone()[0],"UNKNOWN")
    def test_fake_independent_context_is_never_live_qualification(self):
        self.assertEqual(self.runpilot()["gate_status"],"MOCK_NON_ACCEPTING")
        self.assertFalse(self.model.is_live)
    def test_live_requires_exclusive_service_and_actual_model(self):
        self.service.live=True
        with self.assertRaisesRegex(Denied,"EXCLUSIVE_CREDENTIAL_OR_MODEL_AUTHORIZATION_REQUIRED"):
            self.runpilot()
        self.assertEqual(self.remote.cas_count,0)
    def test_reviewer_cannot_receive_writer_authoring_history(self):
        self.runpilot()
        reviewer_inputs=[json.loads(x[1]["content"]) for x in self.model.prompts
                         if json.loads(x[1]["content"])["phase"]=="Antigravity-Nox"]
        self.assertEqual(len(reviewer_inputs),2)
        self.assertTrue(all("author_context_id" in m for m in reviewer_inputs))
        self.assertTrue(all("PRIVATE_JANE_THOUGHT_DO_NOT_EXPOSE" not in json.dumps(m)
                            for m in reviewer_inputs))
    def test_reviewer_false_persona_cannot_pass(self):
        self.model.force_invalid_review=True
        with self.assertRaises(Exception):self.runpilot()
        self.assertEqual(self.remote.cas_count,1)
    def test_hidden_oracle_never_written_by_model(self):
        self.runpilot()
        after=git(self.repo,"show",self.remote.sha+":oracles/hidden.php")
        before=git(self.repo,"show",self.sha+":oracles/hidden.php")
        self.assertEqual(after,before)
    def test_model_result_bad_base_sha_denied(self):
        c=self.context()
        p={"kind":"PATCH_PROPOSAL","base_sha":"0"*40,"edits":[],"reason":"wrong"}
        with self.assertRaisesRegex(Denied,"MODEL_PATCH_STALE_BASE"):validate_patch(p,c)
    def test_model_result_modifies_hidden_test_denied(self):
        c=self.context()
        obj=c.target.read(FILE)
        p={"kind":"PATCH_PROPOSAL","base_sha":self.sha,
           "edits":[{"path":"oracles/hidden.php","expected_sha256":obj["sha256"],
                     "new_text":"<?php echo 'fake pass';"}],"reason":"bad"}
        with self.assertRaisesRegex(Denied,"MODEL_EDIT_SCOPE_DENIED"):validate_patch(p,c)
    def test_model_result_path_traversal_denied(self):
        c=self.context()
        p={"kind":"PATCH_PROPOSAL","base_sha":self.sha,
           "edits":[{"path":"../secrets.env","expected_sha256":"1"*64,"new_text":"pwn"}],"reason":"bad"}
        with self.assertRaisesRegex(Denied,"UNSAFE_SOURCE_PATH"):validate_patch(p,c)
    def test_scope_no_shell_tools(self):
        c=self.context()
        with self.assertRaisesRegex(Denied,"MODEL_TOOL_NOT_ALLOWLISTED"):
            c.execute_tool("shell",{"command":"rm -rf /"})
    def test_source_snapshot_rejects_stale_tree(self):
        with self.assertRaisesRegex(Denied,"SNAPSHOT_TREE_DRIFT"):
            GitSnapshot(self.repo,self.sha,"f"*40,exposed=[FILE])
    def test_source_snapshot_rejects_unavailable_blob(self):
        with self.assertRaisesRegex(Denied,"MISSING_PINNED_SOURCE"):
            GitSnapshot(self.repo,self.sha,self.tree,exposed=["secrets/.env"])
    def test_duplicate_response_rejected(self):
        self.model.duplicate_ids=True
        with self.assertRaisesRegex(Denied,"DUPLICATE_MODEL_CONTEXT_OR_RESPONSE"):
            self.runpilot()
        self.assertEqual(self.remote.cas_count,0)
    def test_budget_out_of_bounds(self):
        with self.assertRaisesRegex(Denied,"MODEL_RUN_BUDGET_INVALID"):
            self.runner.run(self.context(),token_limit=90000)
    def test_source_too_many_reads_exhausts_quota(self):
        c=self.context()
        c.target.read_budget=1
        with self.assertRaisesRegex(Denied,"SOURCE_BUDGET_EXCEEDED"):
            c.execute_tool("read_source",{"path":FILE})
    def test_oracle_command_shell_injection_denied(self):
        with self.assertRaisesRegex(Denied,"HOST_ORACLE_RUNTIME_NOT_ALLOWLISTED"):
            FixedOracle([["bash","-c","curl http://invalid"]])
    def test_review_false_pass_rejected_when_gates_red(self):
        p=self.review.copy()
        response={"schema_version":1,"mission_id":p["mission_id"],
            "frozen_sha":self.sha,"reviewer_context_id":"resp_review_00001",
            "reviewer_persona":"Antigravity-Nox",
            "author_context_id":"resp_author_00001",
            "inspected_scope":[FILE],"evidence_inspected":["evidence"],"findings":[],
            "verdict":"PASS"}
        with self.assertRaisesRegex(Denied,"FALSE_APPROVAL_WITH_RED_GATE"):
            validate_nox(response,packet=p,candidate=self.sha,
                   author_context="resp_author_00001",
                   reviewer_context="resp_review_00001",oracle={"pass":False})
    def test_review_false_pass_rejected_on_open_p1(self):
        p=self.review.copy()
        finding={"id":"P1-01","severity":"P1","path":FILE,"line":4,
                 "contract_violated":"nonnegative","reproduction":"negative debit",
                 "requested_correction":"reject negative","disposition":"OPEN"}
        response={"schema_version":1,"mission_id":p["mission_id"],
            "frozen_sha":self.sha,"reviewer_context_id":"resp_review_00002",
            "reviewer_persona":"Antigravity-Nox",
            "author_context_id":"resp_author_00002",
            "inspected_scope":[FILE],"evidence_inspected":["evidence"],"findings":[finding],
            "verdict":"PASS"}
        with self.assertRaisesRegex(Denied,"FALSE_APPROVAL_WITH_OPEN_CRITICAL"):
            validate_nox(response,packet=p,candidate=self.sha,
                author_context="resp_author_00002",
                reviewer_context="resp_review_00002",oracle={"pass":True})
    def test_live_service_bot_actor_required(self):
        with self.assertRaisesRegex(Denied,"EXCLUSIVE_SERVICE_ACTOR_REQUIRED"):
            ScopedBroker(pathlib.Path(self.temp.name)/"bot.db",KEY,REPO,REPO_ID,BRANCH,
                         enabled=True,require_service_actor=True)
    def test_bot_actor_cannot_be_human_even_if_same_id(self):
        bot=ScopedBroker(pathlib.Path(self.temp.name)/"bot.db",KEY,REPO,REPO_ID,BRANCH,
                     enabled=True,service_actor=("Kirion-Jane",335897759),
                     require_service_actor=True)
        self.broker=bot;self.service.broker=bot
        with self.assertRaisesRegex(Denied,"ACTOR_SUBSTITUTION"):self.runpilot()
        self.assertEqual(self.remote.cas_count,0)
    def test_data_source_prompt_injection_not_command(self):
        # Source-supplied instruction remains bytes in the read tool result.
        c=self.context()
        data=c.execute_tool("read_source",{"path":FILE})
        self.assertEqual(data["content"].count("Synthetic benchmark"),1)
        self.assertNotIn("approve",data["content"].lower())
    def test_canonical_test_mutation_is_forbidden(self):
        c=self.context()
        with self.assertRaisesRegex(Denied,"SOURCE_TOOL_SCOPE_DENIED"):
            c.execute_tool("read_source",{"path":"tests/public.php"})

class ResponseTransportTests(unittest.TestCase):
    def test_paid_calls_default_disabled(self):
        p=OpenAIEngineeringProvider(model="some-model",api_key="fake")
        with self.assertRaisesRegex(Denied,"PAID_MODEL_API_NOT_AUTHORIZED"):
            p.step([],[],max_output_tokens=800,deadline_seconds=30)
    def test_real_request_builder_strict_isolated_input(self):
        captured=[]
        class Http:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return json.dumps({"id":"resp_example_12345678","status":"completed","output":[]}).encode()
        def callback(req,timeout):
            captured.append((req.full_url,json.loads(req.data),timeout,req.get_method()))
            return Http()
        provider=OpenAIEngineeringProvider(model="test-no-paid",api_key="fake-test",
                         authorized=True,request=callback)
        provider.step([{"role":"user","content":"disposable synthetic"}],[],
                      max_output_tokens=4096,deadline_seconds=15)
        url,body,timeout,method=captured[0]
        self.assertEqual(url,"https://api.openai.com/v1/responses")
        self.assertFalse(body["store"])
        self.assertFalse(body["parallel_tool_calls"])
        self.assertNotIn("previous_response_id",body)
        self.assertNotIn("conversation",body)
        self.assertEqual(method,"POST")
    def test_no_budget_overspend(self):
        with self.assertRaisesRegex(Denied,"TOKEN_BUDGET_OUT_OF_BOUNDS"):
            OpenAIEngineeringProvider(model="test",api_key="fake",authorized=True).step([],[],max_output_tokens=900000,deadline_seconds=10)

if __name__=="__main__":unittest.main()
