import {createConnectorAdapter} from "./connector_adapter.mjs";
async function runConnectorTests(create) {
 const A="a".repeat(40), B="b".repeat(40), R="owner/repo", N="feat/candidate";
 const good={identity:async()=>({login:"Kirch-Nairu",id:291564617}),repository:async()=>({repository_full_name:R,permissions:{pull:true,push:true}}),branch:async()=>({name:N,commit:{sha:A,commit:{tree:{sha:B}}}})};
 const cases=[];
 async function test(name,fn,expected=null){try{let v=await fn();cases.push({name,expected:expected??"ALLOW",observed:"ALLOW",pass:expected===null&&v!==false});}catch(e){cases.push({name,expected:expected??"ALLOW",observed:String(e.message),pass:e.message===expected});}}
 const mk=(over={},links={"Kirch-Nairu":"test-link"})=>create({...good,...over},links);
 await test("identity_match",()=>mk().authenticate("Kirch-Nairu"));
 await test("wrong_id",()=>mk({identity:async()=>({login:"Kirch-Nairu",id:0})}).authenticate("Kirch-Nairu"),"ACTOR_MISMATCH");
 await test("wrong_login",()=>mk({identity:async()=>({login:"Kirion-Nox",id:291564617})}).authenticate("Kirch-Nairu"),"ACTOR_MISMATCH");
 await test("unknown_actor",()=>mk().authenticate("Somebody"),"ACCOUNT_UNBOUND");
 await test("unbound_actor",()=>mk().authenticate("Kirion-Nox"),"ACCOUNT_UNBOUND");
 await test("suspended",()=>mk({identity:async()=>{throw Error("403");}}).authenticate("Kirch-Nairu"),"403");
 await test("repo_denied",()=>mk({repository:async()=>({repository_full_name:R,permissions:{pull:false,push:false}})}).repository("Kirch-Nairu",R),"REPOSITORY_READ_DENIED");
 await test("wrong_repo",()=>mk({repository:async()=>({repository_full_name:"other/repo",permissions:{pull:true,push:true}})}).repository("Kirch-Nairu",R),"REPOSITORY_READ_DENIED");
 await test("write_denied",()=>mk({repository:async()=>({repository_full_name:R,permissions:{pull:true,push:false}})}).repository("Kirch-Nairu",R,true),"REPOSITORY_WRITE_DENIED");
 await test("write_string",()=>mk({repository:async()=>({repository_full_name:R,permissions:{pull:true,push:"true"}})}).repository("Kirch-Nairu",R,true),"REPOSITORY_WRITE_DENIED");
 await test("bad_permission_argument",()=>mk().repository("Kirch-Nairu",R,"false"),"INVALID_PERMISSION_REQUEST");
 await test("invalid_repo",()=>mk().repository("Kirch-Nairu","../repo"),"INVALID_REPOSITORY");
 await test("exact_pin",()=>mk().pin("Kirch-Nairu",R,N,A,B));
 await test("head_drift",()=>mk().pin("Kirch-Nairu",R,N,B,B),"EXACT_HEAD_OR_TREE_DRIFT");
 await test("tree_drift",()=>mk().pin("Kirch-Nairu",R,N,A,A),"EXACT_HEAD_OR_TREE_DRIFT");
 await test("zero_sha",()=>mk().pin("Kirch-Nairu",R,N,"0".repeat(40),B),"INVALID_OBJECT_ID");
 await test("ref_alias",()=>mk().pin("Kirch-Nairu",R,"refs//heads/main",A,B),"INVALID_BRANCH");
 await test("branch_mismatch",()=>mk().pin("Kirch-Nairu",R,"feat/other",A,B),"EXACT_HEAD_OR_TREE_DRIFT");
 await test("no_fake_context",()=>{const x=mk().dispatch();return x.nativeLaunch===false&&x.contextId===null&&x.independentReview===false;});
 await test("delivery_unbound",()=>mk().delivery(),"CORE_BROKER_AND_DURABLE_HOST_BRIDGE_REQUIRED");
 return cases;
}
const cases=await runConnectorTests(createConnectorAdapter);console.log(JSON.stringify(cases,null,2));if(cases.some(x=>!x.pass))process.exitCode=1;
