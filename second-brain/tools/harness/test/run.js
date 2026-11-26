// Harness unit tests.
//
// These tests exercise harness logic in isolation and must not depend on an
// operator's Notion credentials or on a snapshot that exists only on one machine.
// The suite therefore pins the GIT semantic provider before any harness module is
// loaded. Previously the suite inherited whatever provider the environment
// implied and failed on a clean checkout with a snapshot-missing error that looked
// like a logic failure. Provider selection itself is covered separately in
// test/semantic-provider.js, which sets its own provider explicitly.
process.env.PSB_SEMANTIC_PROVIDER = 'GIT';

const assert=require('assert');
const fs=require('fs');
const os=require('os');
const path=require('path');
const {spawnSync}=require('child_process');
const {normalizeTask}=require('../lib/io');
const {classifyTask,inferSignals}=require('../lib/classify');
const {scoreRisk}=require('../lib/risk');
const {routeTask}=require('../lib/route');
const {compileContext}=require('../lib/context');
const {evaluateGates}=require('../lib/gates');
const {buildTask,computeRun,intake,learningCandidate}=require('../lib/runtime');
const {createSession,advanceSession,refreshTarget,verifySessionIntegrity}=require('../lib/lifecycle');
const {handleRequest}=require('../lib/agent-protocol');

const repo=path.resolve(__dirname,'..','..','..');
const cfg={
  manifest:require(path.join(repo,'harness/HARNESS_MANIFEST.json')),
  lanes:require(path.join(repo,'harness/config/lane-registry.json')),
  taskTypes:require(path.join(repo,'harness/config/task-types.json')),
  risk:require(path.join(repo,'harness/config/risk-model.json')),
  routing:require(path.join(repo,'harness/config/routing-rules.json')),
  gates:require(path.join(repo,'harness/config/gates.json'))
};
let count=0;
function test(name,fn){fn();count++;console.log(`PASS ${name}`);}
function emptyEvidence(){return {version:1,claims:{}};}
function git(cwd,args){const r=spawnSync('git',['-C',cwd,...args],{encoding:'utf8',windowsHide:true});if(r.status!==0) throw new Error(`git ${args.join(' ')} failed: ${(r.stderr||r.stdout||'').trim()}`);return (r.stdout||'').trim();}
function makeTargetRepo(){
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'harness-target-'));
  git(tmp,['init']);git(tmp,['config','user.email','harness@example.test']);git(tmp,['config','user.name','Harness Test']);
  fs.writeFileSync(path.join(tmp,'fixture.txt'),'v1\n');git(tmp,['add','fixture.txt']);git(tmp,['commit','-m','initial']);
  return tmp;
}
function bugTask(extra={}){return {version:1,id:'bug-lifecycle',intent:'Fix a broken rendering bug',type:'BUG_FIX',...extra};}

test('explicit classification is authoritative',()=>{
  const t=normalizeTask({version:1,id:'x',intent:'do work',type:'BUG_FIX'});
  assert.equal(classifyTask(t,cfg.taskTypes).type,'BUG_FIX');
});

test('deterministic keyword classification resolves obvious server bug',()=>{
  const t=normalizeTask({version:1,id:'x',intent:'Fix a broken asset route returning server error undefined method'});
  assert.equal(classifyTask(t,cfg.taskTypes).type,'BUG_FIX');
});

test('ambiguous or vague intake fails closed',()=>{
  const result=intake({intent:'Make it better'});
  assert.equal(result.classification.status,'BLOCKED');
  assert.equal(result.stop,true);
});

test('signals derive offline/data/auth concerns from raw intent',()=>{
  const s=inferSignals(normalizeTask({version:1,id:'x',intent:'Build a secure offline database app with login'}));
  assert(s.offline&&s.data&&s.auth&&s.security);
});

test('production recovery is forced CRITICAL',()=>{
  const t=normalizeTask({version:1,id:'x',intent:'restore production',type:'PRODUCTION_RECOVERY',signals:{production:true,recovery:true}});
  const s=inferSignals(t),r=scoreRisk(t,'PRODUCTION_RECOVERY',s,cfg.risk);
  assert.equal(r.mode,'CRITICAL');
});

test('greenfield routing traverses multiple cognition families',()=>{
  const t=normalizeTask({version:1,id:'x',intent:'Build a secure offline app',type:'GREENFIELD_SYSTEM',signals:{offline:true,auth:true,data:true}});
  const s=inferSignals(t),r=scoreRisk(t,t.type,s,cfg.risk),route=routeTask(t.type,s,r.mode,cfg.routing,cfg.lanes,cfg.manifest.control_roots);
  assert(route.routed_lane_count>=12);assert(route.routed_families.length>=6);
});

test('stage scoping narrows active lanes without dropping routed lanes',()=>{
  const t=normalizeTask({version:1,id:'x',intent:'Build a secure offline app',type:'GREENFIELD_SYSTEM',signals:{offline:true,auth:true,data:true,deployment:true}});
  const s=inferSignals(t),r=scoreRisk(t,t.type,s,cfg.risk);
  const early=routeTask(t.type,s,r.mode,cfg.routing,cfg.lanes,cfg.manifest.control_roots,{stage:'PRE_DESIGN'});
  const late=routeTask(t.type,s,r.mode,cfg.routing,cfg.lanes,cfg.manifest.control_roots,{stage:'PRE_DELIVERY'});
  // deferral narrows the seeded context
  assert(early.active_lane_count<early.routed_lane_count);
  assert(early.active_lane_count<late.active_lane_count);
  // but never loses a lane: active + deferred always reconstructs the full route
  for(const route of [early,late]) assert.equal(route.lanes.length+route.deferred_lanes.length,route.routed_lane_count);
  // and the routed set itself is stage-independent
  assert.equal(early.routed_lane_count,late.routed_lane_count);
});

test('every registered lane has a declared stage scope',()=>{
  const ids=Object.values(cfg.lanes.families).flat().map(x=>x.id);
  for(const id of ids) assert(cfg.routing.stage_scope[id],`lane ${id} has no stage_scope`);
  assert.equal(Object.keys(cfg.routing.stage_scope).length,ids.length);
});

test('incident response is floored at POST_DEPLOY regardless of requested stage',()=>{
  const t=normalizeTask({version:1,id:'x',intent:'active incident, service down',type:'INCIDENT_RESPONSE',signals:{incident:true,production:true}});
  const s=inferSignals(t),r=scoreRisk(t,t.type,s,cfg.risk);
  const route=routeTask(t.type,s,r.mode,cfg.routing,cfg.lanes,cfg.manifest.control_roots,{stage:'PRE_DESIGN'});
  assert.equal(route.evaluated_stage,'POST_DEPLOY');
  assert.equal(route.deferred_lanes.length,0);
});

test('context compiler blocks missing required sources',()=>{
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'harness-')),route={rigor_mode:'LOW',control_roots:['missing.md'],lanes:[]};
  assert.equal(compileContext(tmp,route,cfg.manifest).status,'BLOCKED');
});

test('context compiler follows resolvable graph links and hashes content',()=>{
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'harness-'));fs.mkdirSync(path.join(tmp,'cognitive-os'),{recursive:true});fs.writeFileSync(path.join(tmp,'cognitive-os','root.md'),'root [[Concept]]');fs.mkdirSync(path.join(tmp,'mesh'),{recursive:true});fs.writeFileSync(path.join(tmp,'mesh','Concept.md'),'concept');
  const c=compileContext(tmp,{rigor_mode:'LOW',control_roots:['cognitive-os/root.md'],lanes:[]},{context:{...cfg.manifest.context,ignored_directories:[]}});
  assert.equal(c.status,'RESOLVED');assert.equal(c.documents.length,2);assert.equal(c.documents[0].sha256.length,64);
});

test('required roots and lane seeds are loaded before optional graph documents',()=>{
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'fci-required-first-'));
  fs.writeFileSync(path.join(tmp,'root.md'),'[[Extra]]');
  fs.writeFileSync(path.join(tmp,'lane.md'),'mandatory lane');
  fs.writeFileSync(path.join(tmp,'Extra.md'),'optional neighbour');
  const route={rigor_mode:'LOW',control_roots:['root.md'],lanes:[{path:'lane.md'}]};
  const c=compileContext(tmp,route,{context:{...cfg.manifest.context,ignored_directories:[],max_documents:2,max_bytes:128}});
  assert.equal(c.status,'RESOLVED');
  assert.deepEqual(c.documents.map(x=>x.path),['root.md','lane.md']);
  assert(c.documents.every(x=>x.source==='REQUIRED_SEED'));
  assert.equal(c.truncated,true);
  assert.deepEqual(c.omitted_optional,[{path:'Extra.md',reason:'DOCUMENT_BUDGET'}]);
  assert.deepEqual(c.required_not_loaded,[]);
});

test('required seeds fail closed when document count exceeds budget even at LOW rigor',()=>{
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'fci-required-count-'));
  fs.writeFileSync(path.join(tmp,'root.md'),'authority');
  fs.writeFileSync(path.join(tmp,'lane.md'),'writer');
  const route={rigor_mode:'LOW',control_roots:['root.md'],lanes:[{path:'lane.md'}]};
  const c=compileContext(tmp,route,{context:{...cfg.manifest.context,ignored_directories:[],max_documents:1,max_bytes:128}});
  assert.equal(c.status,'BLOCKED');
  assert.match(c.reason,/Required context sources exceed document budget/);
  assert.deepEqual(c.required_not_loaded,['root.md','lane.md']);
  assert.equal(c.documents.length,0);
});

test('required seed byte overflow blocks instead of reporting RESOLVED',()=>{
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'fci-required-bytes-'));
  fs.writeFileSync(path.join(tmp,'root.md'),'authority-required');
  fs.writeFileSync(path.join(tmp,'lane.md'),'writer-required');
  const route={rigor_mode:'MEDIUM',control_roots:['root.md'],lanes:[{path:'lane.md'}]};
  const c=compileContext(tmp,route,{context:{...cfg.manifest.context,ignored_directories:[],max_documents:4,max_bytes:12}});
  assert.equal(c.status,'BLOCKED');
  assert.match(c.reason,/Required context sources exceed byte budget/);
  assert.deepEqual(c.required_not_loaded,['root.md','lane.md']);
  assert.deepEqual(c.missing_required,[]);
});

test('optional byte omission is visible instead of falsely complete',()=>{
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'fci-optional-bytes-'));
  fs.writeFileSync(path.join(tmp,'root.md'),'[[Extra]]');
  fs.writeFileSync(path.join(tmp,'Extra.md'),'x'.repeat(100));
  const route={rigor_mode:'MEDIUM',control_roots:['root.md'],lanes:[]};
  const c=compileContext(tmp,route,{context:{...cfg.manifest.context,ignored_directories:[],max_documents:4,max_bytes:20}});
  assert.equal(c.status,'RESOLVED');
  assert.equal(c.truncated,true);
  assert.deepEqual(c.omitted_optional,[{path:'Extra.md',reason:'BYTE_BUDGET'}]);
  assert.deepEqual(c.documents.map(x=>x.path),['root.md']);
  const rendered=require('../lib/render').renderContext(c,{harnessVersion:'test',taskId:'fci-omission',type:'BUG_FIX',mode:'MEDIUM'});
  assert(rendered.includes('## Omitted optional context (budget)'));
  assert(rendered.includes('Extra.md'));
  assert(rendered.includes('NOT LOADED'));
});

test('MCP bootstrap text and structured output disclose optional byte omissions even with PASS gate',()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'fci-mcp-optional-'));
  fs.writeFileSync(path.join(root,'control.md'),'[[Optional]]');
  fs.writeFileSync(path.join(root,'Optional.md'),'x'.repeat(100));
  const route={rigor_mode:'LOW',control_roots:['control.md'],lanes:[]};
  const c=compileContext(root,route,{context:{...cfg.manifest.context,ignored_directories:[],max_documents:5,max_bytes:24}});
  assert.strictEqual(c.status,'RESOLVED');
  assert.strictEqual(c.truncated,true);
  const {buildBootstrapToolResponse}=require('../lib/mcp-bootstrap');
  const run={run_id:'fci-mcp-fixture',manifest:{},task:{},
    classification:{status:'RESOLVED',type:'BUG_FIX'},signals:{},
    risk:{mode:'LOW'},route,gates:{verdict:'PASS'},
    context:c,context_manifest:require('../lib/runtime').contextManifest(c)};
  const response=buildBootstrapToolResponse(run,false);
  assert(response.content[0].text.includes('context=RESOLVED, gate=PASS, truncated=YES, omitted_optional=1'));
  assert(response.content[0].text.includes('WARNING: NOT LOADED optional context'));
  assert(response.content[0].text.includes('Optional.md'));
  assert.deepStrictEqual(response.structuredContent.context_manifest.omitted_optional,c.omitted_optional);
  assert(!Object.hasOwn(response.structuredContent,'context_documents'));
  const withDocuments=buildBootstrapToolResponse(run,true);
  assert.strictEqual(withDocuments.structuredContent.context_documents.length,1);
  assert(withDocuments.content[0].text.includes('NOT LOADED'));
  // The server must use the same tested response builder, not a divergent summary.
  const server=fs.readFileSync(path.join(__dirname,'../mcp/server.mjs'),'utf8');
  assert(server.includes('return buildBootstrapToolResponse(r,include_context);'));
});

test('MCP bootstrap reports blocked mandatory context and complete-context control',()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'fci-mcp-blocked-'));
  const route={rigor_mode:'LOW',control_roots:['missing.md'],lanes:[]};
  const c=compileContext(root,route,{context:{...cfg.manifest.context,ignored_directories:[],max_documents:5,max_bytes:100}});
  const {buildBootstrapToolResponse}=require('../lib/mcp-bootstrap');
  const base={run_id:'fci-mcp-blocked-fixture',manifest:{},task:{},
    classification:{status:'RESOLVED',type:'BUG_FIX'},signals:{},risk:{mode:'LOW'},
    route,gates:{verdict:'BLOCK'},context:c,context_manifest:require('../lib/runtime').contextManifest(c)};
  const blocked=buildBootstrapToolResponse(base,false);
  assert(blocked.content[0].text.includes('BLOCKED: REQUIRED CONTEXT NOT LOADED'));
  assert(blocked.content[0].text.includes('missing.md'));
  fs.writeFileSync(path.join(root,'missing.md'),'required and complete');
  const complete=compileContext(root,route,{context:{...cfg.manifest.context,ignored_directories:[],max_documents:5,max_bytes:100}});
  const green=buildBootstrapToolResponse({...base,context:complete,context_manifest:require('../lib/runtime').contextManifest(complete),gates:{verdict:'PASS'}},false);
  assert(green.content[0].text.includes('truncated=NO, omitted_optional=0'));
  assert(!green.content[0].text.includes('NOT LOADED'));
});

test('complete context preserves required and graph provenance without truncation',()=>{
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'fci-complete-'));
  fs.writeFileSync(path.join(tmp,'root.md'),'[[Extra]]');
  fs.writeFileSync(path.join(tmp,'Extra.md'),'additional context');
  const route={rigor_mode:'MEDIUM',control_roots:['root.md'],lanes:[]};
  const c=compileContext(tmp,route,{context:{...cfg.manifest.context,ignored_directories:[],max_documents:4,max_bytes:128}});
  assert.equal(c.status,'RESOLVED');
  assert.equal(c.truncated,false);
  assert.deepEqual(c.omitted_optional,[]);
  assert.deepEqual(c.documents.map(x=>x.source),['REQUIRED_SEED','GRAPH_EXPANSION']);
  assert(c.documents.every(x=>x.sha256.length===64));
});

test('duplicate control and lane seed is compiled once with control-root authority',()=>{
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'fci-dedup-'));
  fs.writeFileSync(path.join(tmp,'root.md'),'authority');
  const route={rigor_mode:'LOW',control_roots:['root.md'],lanes:[{path:'root.md'}]};
  const c=compileContext(tmp,route,{context:{...cfg.manifest.context,ignored_directories:[],max_documents:1,max_bytes:128}});
  assert.equal(c.status,'RESOLVED');
  assert.equal(c.documents.length,1);
  assert.equal(c.documents[0].source,'REQUIRED_SEED');
  assert.equal(c.truncated,false);
});

test('run id is deterministic for unchanged cognition state',()=>{
  const task=bugTask(),a=computeRun(buildTask(task)),b=computeRun(buildTask(task));
  assert.equal(a.run_id,b.run_id);assert.equal(a.task_sha256,b.task_sha256);assert.equal(a.context_sha256,b.context_sha256);
});

test('agent protocol classification matches reusable runtime core',()=>{
  const task=bugTask(),core=buildTask(task),agent=handleRequest({operation:'classify',task});
  assert.deepEqual(agent.classification,core.classification);assert.deepEqual(agent.signals,core.signals);
});

test('unresolved declared target repository blocks bootstrap',()=>{
  const missing=path.join(os.tmpdir(),`does-not-exist-${process.pid}-${Date.now()}`),run=buildTask(bugTask({repository:{path:missing}}));
  assert.equal(run.gates.verdict,'BLOCK');assert(run.gates.results.some(x=>x.id==='GATE-BOOT-TARGET-REALITY'&&x.status==='FAIL'));
});

test('missing primary route observation blocks delivery',()=>{
  const task=normalizeTask({version:1,id:'sentinel',intent:'build app',type:'GREENFIELD_SYSTEM',signals:{auth:true,data:true},primary_journeys:[{id:'asset-detail',description:'open asset'}]});
  const classification={status:'RESOLVED',type:'GREENFIELD_SYSTEM'},signals=inferSignals(task),risk=scoreRisk(task,'GREENFIELD_SYSTEM',signals,cfg.risk),ctx={task,type:'GREENFIELD_SYSTEM',classification,signals,risk,context:{status:'RESOLVED'},target_repository:{status:'NOT_REQUESTED'}};
  const ev={version:1,claims:{'design.authority_boundaries':{status:'PASS',levels:['INTENDED']},'decision.architecture':{status:'PASS',levels:['INTENDED']},'verification.automated':{status:'PASS',levels:['TESTED']},'verification.authorization_negative':{status:'PASS',levels:['TESTED']},'delivery.source_state':{status:'PASS',levels:['DURABLE']}}};
  const result=evaluateGates(cfg.gates,ctx,ev,{throughStage:'PRE_DELIVERY'});
  assert.equal(result.verdict,'BLOCK');assert(result.results.some(x=>x.id==='GATE-VERIFY-PRIMARY-RUNTIME'&&x.status==='FAIL'));
});

test('explicit observed runtime failure blocks even when automated verification passed',()=>{
  const task=normalizeTask({version:1,id:'sentinel',intent:'build app',type:'GREENFIELD_SYSTEM',primary_journeys:[{id:'asset-detail',description:'open asset'}]});
  const classification={status:'RESOLVED',type:'GREENFIELD_SYSTEM'},signals=inferSignals(task),risk=scoreRisk(task,'GREENFIELD_SYSTEM',signals,cfg.risk),ctx={task,type:'GREENFIELD_SYSTEM',classification,signals,risk,context:{status:'RESOLVED'},target_repository:{status:'NOT_REQUESTED'}};
  const ev={version:1,claims:{'verification.automated':{status:'PASS',levels:['TESTED']},'journey.asset-detail.runtime':{status:'FAIL',levels:['OBSERVED'],detail:'GET /assets/{asset} returned HTTP 500'},'delivery.source_state':{status:'PASS',levels:['DURABLE']},'decision.architecture':{status:'PASS',levels:['INTENDED']}}};
  const result=evaluateGates(cfg.gates,ctx,ev,{throughStage:'PRE_DELIVERY'}),gate=result.results.find(x=>x.id==='GATE-VERIFY-PRIMARY-RUNTIME');
  assert.equal(result.verdict,'BLOCK');assert(gate.reason.includes('HTTP 500'));
});

test('observed primary route closes the specific runtime gate',()=>{
  const task=normalizeTask({version:1,id:'sentinel',intent:'build app',type:'GREENFIELD_SYSTEM',primary_journeys:[{id:'asset-detail',description:'open asset'}]});
  const classification={status:'RESOLVED',type:'GREENFIELD_SYSTEM'},signals=inferSignals(task),risk=scoreRisk(task,'GREENFIELD_SYSTEM',signals,cfg.risk),ctx={task,type:'GREENFIELD_SYSTEM',classification,signals,risk,context:{status:'RESOLVED'},target_repository:{status:'NOT_REQUESTED'}},ev={version:1,claims:{'journey.asset-detail.runtime':{status:'PASS',levels:['OBSERVED']}}};
  const gate=evaluateGates(cfg.gates,ctx,ev,{throughStage:'PRE_DELIVERY'}).results.find(x=>x.id==='GATE-VERIFY-PRIMARY-RUNTIME');assert(gate&&gate.status==='PASS');
});

test('truncated context is a WARN below CRITICAL rigor and a BLOCK at CRITICAL',()=>{
  const gatesCfg=require('../../../harness/config/gates.json');
  const base=(mode,truncated)=>({task:{},type:'GREENFIELD_SYSTEM',classification:{status:'RESOLVED'},signals:{},risk:{mode},route:{},
    context:{status:'RESOLVED',truncated,document_count:1,document_budget:1,total_bytes:1,byte_budget:1},
    target_repository:{status:'NOT_REQUESTED'}});
  const find=(mode,truncated)=>{
    const r=evaluateGates(gatesCfg,base(mode,truncated),{version:1,claims:{}},{throughStage:'PRE_DESIGN'});
    return r.results.find(x=>x.id.startsWith('GATE-DESIGN-CONTEXT-COMPLETE'));
  };
  assert.equal(find('HIGH',false).status,'PASS');
  const warnHit=find('HIGH',true); assert.equal(warnHit.status,'FAIL'); assert.equal(warnHit.severity,'WARN');
  const blockHit=find('CRITICAL',true); assert.equal(blockHit.status,'FAIL'); assert.equal(blockHit.severity,'BLOCK');
  // a WARN-severity failure must not itself flip the run verdict to BLOCK
  const warnOnly=evaluateGates({gates:gatesCfg.gates.filter(g=>g.id==='GATE-DESIGN-CONTEXT-COMPLETE')},base('HIGH',true),{version:1,claims:{}},{throughStage:'PRE_DESIGN'});
  assert.equal(warnOnly.verdict,'PASS');
  const blockOnly=evaluateGates({gates:gatesCfg.gates.filter(g=>g.id==='GATE-DESIGN-CONTEXT-COMPLETE-CRITICAL')},base('CRITICAL',true),{version:1,claims:{}},{throughStage:'PRE_DESIGN'});
  assert.equal(blockOnly.verdict,'BLOCK');
});

function assertCompleteShippedPack(c,route,root,label){
  // Status must be checked FIRST. BLOCKED context can explicitly report truncated=false,
  // so truncation alone cannot establish completeness.
  assert.strictEqual(c.status,'RESOLVED',label+' status='+c.status+'; reason='+(c.reason||'none'));
  assert.strictEqual(c.truncated,false,label+' truncated at '+c.document_count+'/'+c.document_budget+' docs, '+c.total_bytes+'/'+c.byte_budget+' bytes');
  assert.deepStrictEqual(c.missing_required,[],label+' missing required sources');
  assert.deepStrictEqual(c.required_not_loaded,[],label+' required sources not loaded');
  assert.deepStrictEqual(c.omitted_optional,[],label+' optional sources not loaded');
  const required=[...new Set([...route.control_roots,...route.lanes.map(x=>x.path)])];
  const docs=new Map(c.documents.map(x=>[x.path,x]));
  for(const source of required){
    const doc=docs.get(source);
    assert(doc,label+' missing mandatory document '+source);
    assert.strictEqual(doc.source,'REQUIRED_SEED',label+' unmarked required seed '+source);
    assert.strictEqual(doc.sha256,require('../lib/io').sha256(fs.readFileSync(path.join(root,...source.split('/')),'utf8')),label+' stale content hash '+source);
  }
  assert.strictEqual(c.documents.length,c.document_count,label+' inconsistent document count');
}

test('complete-pack assertion rejects BLOCKED missing-required context',()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'fci-completeness-negative-'));
  try{
    fs.writeFileSync(path.join(root,'available-authority.md'),'# Available authority\n','utf8');
    const route={rigor_mode:'LOW',control_roots:['available-authority.md','mandatory-authority.md'],lanes:[]};
    const c=compileContext(root,route,{context:{...cfg.manifest.context,ignored_directories:[],max_documents:4,max_bytes:128}});
    assert.strictEqual(c.status,'BLOCKED');
    assert.strictEqual(c.reason,'required context sources missing');
    assert.strictEqual(c.truncated,false);
    assert.deepStrictEqual(c.missing_required,['mandatory-authority.md']);
    assert.deepStrictEqual(c.required_not_loaded,['available-authority.md','mandatory-authority.md']);
    assert.deepStrictEqual(c.documents,[]);
    assert.strictEqual(c.document_count,0);
    assert.strictEqual(c.total_bytes,0);
    assert.strictEqual(c.document_budget,4);
    assert.strictEqual(c.byte_budget,128);
    assert.throws(()=>assertCompleteShippedPack(c,route,root,'negative fixture'),err=>
      err instanceof assert.AssertionError && err.actual==='BLOCKED' && err.expected==='RESOLVED' &&
      err.operator==='strictEqual' && err.message.includes('negative fixture status=BLOCKED; reason=required context sources missing'));
  }finally{fs.rmSync(root,{recursive:true,force:true});}
});

test('no rigor mode or lifecycle stage truncates the compiled context for the shipped mesh',()=>{
  const routing=cfg.routing,registry=cfg.lanes,manifest=cfg.manifest;
  const allSignals=Object.fromEntries(Object.keys(routing.by_signal).map(key=>[key,true]));
  const allLaneIds=Object.values(registry.families).flat().map(lane=>lane.id).sort();
  assert.strictEqual(Object.keys(allSignals).length,19,'CRITICAL fixture must cover the 19 configured signal keys');
  assert(allSignals.performance&&allSignals.commercial,'critical capacity test must exercise performance and commercial signals');
  const sigSets={
    LOW:{ui:true}, MEDIUM:{ui:true,data:true},
    HIGH:{ui:true,data:true,auth:true,security:true,offline:true,recovery:true,deployment:true,production:true},
    CRITICAL:allSignals
  };
  const typesByMode={LOW:'BUG_FIX',MEDIUM:'EXISTING_SYSTEM_FEATURE',HIGH:'GREENFIELD_SYSTEM',CRITICAL:'GREENFIELD_SYSTEM'};
  const root=path.join(__dirname,'..','..','..');
  for(const mode of ['LOW','MEDIUM','HIGH','CRITICAL']){
    for(const stage of ['PRE_DESIGN','PRE_IMPLEMENTATION','PRE_DELIVERY','POST_DEPLOY']){
      const route=routeTask(typesByMode[mode],sigSets[mode],mode,routing,registry,manifest.control_roots,{stage});
      if(mode==='CRITICAL'){
        const routed=[...route.lanes,...route.deferred_lanes].map(lane=>lane.id).sort();
        assert.deepStrictEqual(routed,allLaneIds,'CRITICAL all-signals route must include every registered lane at '+stage);
      }
      const c=compileContext(root,route,manifest);
      // Print measured headroom; budget calibration cannot rely on a silent PASS.
      console.log('FCI-CAPACITY '+mode+'/'+stage+' routed='+route.routed_lane_count+
        ' active='+route.active_lane_count+' docs='+c.document_count+'/'+c.document_budget+
        ' bytes='+c.total_bytes+'/'+c.byte_budget+' status='+c.status+' truncated='+c.truncated);
      assertCompleteShippedPack(c,route,root,mode+'/'+stage);
    }
  }
});

test('lifecycle advances sequentially and rejects stage skipping',()=>{
  const task=bugTask();let session=createSession(task,emptyEvidence(),{throughStage:'BOOTSTRAP'});assert.equal(session.current_stage,'BOOTSTRAP');
  let result=advanceSession(session,task,emptyEvidence(),'PRE_DESIGN');assert.equal(result.status,'ADVANCED');session=result.session;
  result=advanceSession(session,task,emptyEvidence(),'PRE_DELIVERY');assert.equal(result.verdict,'BLOCK');assert.equal(result.status,'INVALID_TRANSITION');
});

test('changed task makes an existing lifecycle session stale',()=>{
  const task=bugTask(),session=createSession(task,emptyEvidence(),{throughStage:'BOOTSTRAP'}),changed={...task,intent:'Fix a different rendering bug'};
  const result=advanceSession(session,changed,emptyEvidence(),'PRE_DESIGN');assert.equal(result.verdict,'BLOCK');assert.equal(result.status,'STALE');assert(result.changed.includes('task_sha256'));
});

test('session history and envelope are tamper-evident',()=>{
  const task=bugTask(),session=createSession(task,emptyEvidence(),{throughStage:'BOOTSTRAP'}),tampered={...session,current_stage:'POST_VERIFY'};
  const result=advanceSession(tampered,task,emptyEvidence(),'PRE_DESIGN');assert.equal(result.status,'TAMPERED');
});

test('HMAC lifecycle sessions require the server-held signing key',()=>{
  const task=bugTask(),session=createSession(task,emptyEvidence(),{throughStage:'BOOTSTRAP',sessionKey:'test-secret'});assert.equal(session.integrity_mode,'HMAC_SHA256');assert.equal(verifySessionIntegrity(session,{sessionKey:'test-secret'}).valid,true);assert.equal(verifySessionIntegrity(session).valid,false);
  const result=advanceSession(session,task,emptyEvidence(),'PRE_DESIGN',{sessionKey:'test-secret'});assert.equal(result.verdict,'PASS');
});

test('target repository drift requires an explicit clean checkpoint refresh',()=>{
  const target=makeTargetRepo(),task=bugTask({repository:{path:target}});let session=createSession(task,emptyEvidence(),{throughStage:'BOOTSTRAP'});
  let result=advanceSession(session,task,emptyEvidence(),'PRE_DESIGN');assert.equal(result.verdict,'PASS');session=result.session;
  result=advanceSession(session,task,emptyEvidence(),'PRE_IMPLEMENTATION');assert.equal(result.verdict,'PASS');session=result.session;
  fs.writeFileSync(path.join(target,'fixture.txt'),'v2\n');git(target,['add','fixture.txt']);git(target,['commit','-m','implementation']);
  const delivery={version:1,claims:{'verification.automated':{status:'PASS',levels:['TESTED']},'delivery.source_state':{status:'PASS',levels:['DURABLE']}}};
  result=advanceSession(session,task,delivery,'PRE_DELIVERY');assert.equal(result.status,'TARGET_DRIFT');
  result=refreshTarget(session,task,'implementation committed and clean');assert.equal(result.status,'TARGET_REFRESHED');session=result.session;
  result=advanceSession(session,task,delivery,'PRE_DELIVERY');assert.equal(result.verdict,'PASS');assert.equal(result.session.current_stage,'PRE_DELIVERY');
});

test('dirty target repositories cannot be adopted as lifecycle checkpoints',()=>{
  const target=makeTargetRepo(),task=bugTask({repository:{path:target}});let session=createSession(task,emptyEvidence(),{throughStage:'BOOTSTRAP'});
  session=advanceSession(session,task,emptyEvidence(),'PRE_DESIGN').session;session=advanceSession(session,task,emptyEvidence(),'PRE_IMPLEMENTATION').session;fs.writeFileSync(path.join(target,'fixture.txt'),'dirty\n');
  const result=refreshTarget(session,task,'try to adopt dirty state');assert.equal(result.verdict,'BLOCK');assert.equal(result.status,'TARGET_DIRTY');
});

test('observed runtime failure produces review-only learning candidate',()=>{
  const task=bugTask(),ev={version:1,claims:{'runtime.failure_discovered':{status:'FAIL',levels:['OBSERVED'],detail:'primary route returned HTTP 500',source:'independent runtime execution'}}},candidate=learningCandidate(task,ev,{failureClaim:'runtime.failure_discovered',proposal:'require route-level runtime evidence'});
  assert.equal(candidate.review_status,'PENDING_HUMAN_REVIEW');assert.equal(candidate.doctrine_mutated,false);assert.equal(candidate.observed_behavior,'primary route returned HTTP 500');
});

console.log(`\n${count} harness tests passed.`);

// W3A regression: preserve all existing tests and execute the focused suite.
require('./reconstruction-risk');

// W3B: stage checkpoints are separate from the stable session identity.
test('W3B stage transitions compile and seal distinct context checkpoints',()=>{
  const task=bugTask();const options={sessionKey:'w3b-test'};
  let session=createSession(task,emptyEvidence(),{...options,throughStage:'BOOTSTRAP'});
  const {session_id,run_id}=session;const initial=session.checkpoint.checkpoint_sha256;
  const result=advanceSession(session,task,emptyEvidence(),'PRE_DESIGN',options);
  assert.equal(result.status,'ADVANCED');session=result.session;
  assert.equal(session.session_id,session_id);assert.equal(session.run_id,run_id);
  assert.equal(session.checkpoint.stage,'PRE_DESIGN');assert.notEqual(session.checkpoint.checkpoint_sha256,initial);
  assert.equal(session.context_sha256,session.checkpoint.context_sha256);
  assert.equal(result.stage_context.checkpoint.checkpoint_sha256,session.checkpoint.checkpoint_sha256);
  assert.equal(verifySessionIntegrity(session,options).valid,true);
});
