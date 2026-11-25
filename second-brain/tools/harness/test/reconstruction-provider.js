// T-C03: actual compiler contracts on synthetic Git/Notion snapshot sources.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createHash}=require('node:crypto');
const {sha256}=require('../lib/io');
const {documentBudget,byteBudget}=require('../lib/context');
const {compileSemanticContext,snapshotDigest,configDigest}=require('../lib/semantic-provider');
const {contextManifest}=require('../lib/runtime');
const {renderContext,renderRun}=require('../lib/render');
const {buildBootstrapToolResponse}=require('../lib/mcp-bootstrap');
const manifest=require('../../../harness/HARNESS_MANIFEST.json');
const modes=['LOW','MEDIUM','HIGH','CRITICAL'];
function fixture(mode,fn,customManifest=manifest){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'tc03-provider-'));
  const controlPlane={knowledge_data_source_id:'fixture-source',source_repository:'fixture/repo'};
  const routePack={always:[],by_lane:{}};
  const route={rigor_mode:mode,control_roots:['Root.md'],lanes:[],deferred_lanes:[],routed_lane_count:0,active_lane_count:0};
  const snapshotPath=path.join(root,'snapshot.json');
  const write=(name,content)=>fs.writeFileSync(path.join(root,name),content,'utf8');
  function snapshot(names=route.control_roots,mutate){
    const documents=names.map((source_path,i)=>{const content=fs.readFileSync(path.join(root,source_path),'utf8');
      const source_sha=createHash('sha1').update(`blob ${Buffer.byteLength(content,'utf8')}\0`).update(content).digest('hex');
      return {source_path,source_sha,content_sha256:sha256(content),content,page_id:`fixture-${i}`,title:source_path,notion_url:`https://example.invalid/${i}`};});
    const value={version:1,provider:'NOTION_SNAPSHOT',generated_at:'2026-01-01T00:00:00Z',data_source_id:controlPlane.knowledge_data_source_id,source_repository:controlPlane.source_repository,control_plane_sha256:configDigest(controlPlane),route_pack_sha256:configDigest(routePack),documents};
    if(mutate)mutate(value);value.snapshot_sha256=snapshotDigest(value);write('snapshot.json',JSON.stringify(value));return value;
  }
  const compile=provider=>compileSemanticContext(root,route,customManifest,{provider,controlPlane,routePack,snapshotPath});
  const both=()=>['GIT','NOTION_SNAPSHOT'].map(compile);
  try{fn({root,route,routePack,write,snapshot,compile,both,cap:byteBudget(customManifest.context,mode),docs:documentBudget(customManifest.context,mode)});}finally{fs.rmSync(root,{recursive:true,force:true});}
}
function resolved(c,bytes,cap,docs,count=1){
  assert.equal(c.status,'RESOLVED');assert.equal(c.total_bytes,bytes);assert.equal(c.document_count,count);
  assert.equal(c.byte_budget,cap);assert.equal(c.document_budget,docs);
  assert.equal(c.truncated,false);assert.deepEqual(c.required_not_loaded,[]);
  assert(c.documents.every(d=>d.bytes===Buffer.byteLength(d.content,'utf8')&&d.sha256===sha256(d.content)));
}
function blocked(c,paths,cap,docs){
  assert.equal(c.status,'BLOCKED');assert.deepEqual(c.documents,[]);assert.equal(c.document_count,0);assert.equal(c.total_bytes,0);
  assert.deepEqual(c.required_not_loaded,paths);assert.equal(c.byte_budget,cap);assert.equal(c.document_budget,docs);
}
for(const mode of modes){
  test(`T-C03 ${mode} under budget and exact configured UTF-8 boundary`,()=>fixture(mode,({write,snapshot,both,cap,docs})=>{
    for(const content of ['under budget','a'.repeat(cap),'é'.repeat(cap/2)]){write('Root.md',content);snapshot();for(const c of both())resolved(c,Buffer.byteLength(content,'utf8'),cap,docs);}
  }));
  test(`T-C03 ${mode} required boundary plus one byte blocks both providers`,()=>fixture(mode,({write,snapshot,both,cap,docs})=>{
    for(const content of ['a'.repeat(cap+1),'é'.repeat(cap/2)+'a']){write('Root.md',content);snapshot();for(const c of both()){blocked(c,['Root.md'],cap,docs);assert.equal(c.truncated,true);assert.match(c.reason,/byte budget/i);}}
  }));
  test(`T-C03 ${mode} document-count boundary and overflow`,()=>fixture(mode,({route,write,snapshot,both,cap,docs})=>{
    route.control_roots=Array.from({length:docs},(_,i)=>`Seed${i}.md`);for(const p of route.control_roots)write(p,'a');snapshot();for(const c of both())resolved(c,docs,cap,docs,docs);
    route.control_roots.push('Overflow.md');write('Overflow.md','b');snapshot();for(const c of both()){blocked(c,route.control_roots,cap,docs);assert.equal(c.truncated,true);assert.match(c.reason,/document budget/i);}
  }));
}
test('T-C03 legacy explicit caps, deduplication and Notion route-pack mandatory sources',()=>{
  const custom={...manifest,context:{...manifest.context,max_documents:2,max_bytes:8}};
  fixture('CRITICAL',({route,routePack,write,snapshot,compile,cap,docs})=>{
    route.control_roots.push('Root.md');write('Root.md','éé');write('Pack.md','éé');routePack.always=['Pack.md'];
    snapshot(['Root.md','Pack.md']);resolved(compile('NOTION_SNAPSHOT'),8,cap,docs,2);
    write('Pack.md','ééa');snapshot(['Root.md','Pack.md']);blocked(compile('NOTION_SNAPSHOT'),['Root.md','Pack.md'],cap,docs);
  },custom);
});
test('T-C03 missing and stale mandatory sources never appear loaded',()=>fixture('LOW',({route,write,snapshot,compile,cap,docs})=>{
  route.control_roots.push('Second.md');write('Root.md','root');snapshot(['Root.md']);
  for(const provider of ['GIT','NOTION_SNAPSHOT']){const c=compile(provider);blocked(c,route.control_roots,cap,docs);assert.deepEqual(c.missing_required,['Second.md']);}
  write('Second.md','second');snapshot();write('Root.md','changed after snapshot');const stale=compile('NOTION_SNAPSHOT');blocked(stale,route.control_roots,cap,docs);assert.match(stale.reason,/source drift/);
}));
test('T-C03 tampered snapshot digest and stale route pack remain blocked',()=>fixture('LOW',({root,write,snapshot,compile})=>{
  write('Root.md','root');const snap=snapshot();snap.documents[0].content='tampered';write('snapshot.json',JSON.stringify(snap));assert.equal(compile('NOTION_SNAPSHOT').status,'BLOCKED');
  snapshot(undefined,s=>s.route_pack_sha256='0'.repeat(64));assert.equal(compile('NOTION_SNAPSHOT').status,'BLOCKED');
}));
test('T-C03 Git optional omission and Notion route-only coverage are distinguished',()=>fixture('LOW',({write,snapshot,compile,cap,docs})=>{
  write('Root.md','[[Extra]]');write('Extra.md','x'.repeat(cap));snapshot(['Root.md','Extra.md']);
  const git=compile('GIT');assert.equal(git.status,'RESOLVED');assert.equal(git.truncated,true);assert.deepEqual(git.omitted_optional,[{path:'Extra.md',reason:'BYTE_BUDGET'}]);
  const notion=compile('NOTION_SNAPSHOT');resolved(notion,9,cap,docs);assert.equal(notion.optional_graph_expansion,'NOT_PERFORMED');assert.equal(notion.coverage,'REQUIRED_ROUTE_PACK_ONLY');
  assert.deepEqual(notion.omitted_optional,[]);assert.equal(notion.documents[0].source,'NOTION_SNAPSHOT');assert.match(notion.documents[0].source_sha,/^[a-f0-9]{40}$/);
}));
test('T-C03 rendered and machine-readable context report actual budgets and coverage',()=>fixture('LOW',({route,write,snapshot,compile,cap,docs})=>{
  write('Root.md','root');snapshot();let c=compile('NOTION_SNAPSHOT');
  const mkRun=(context)=>({run_id:'tc03',manifest:{semantic_snapshot_sha256:context.snapshot_sha256},task:{id:'tc03'},classification:{status:'RESOLVED',type:'BUG_FIX'},risk:{mode:'LOW'},signals:{},route,gates:{verdict:context.status==='RESOLVED'?'PASS':'BLOCK',results:[],through_stage:'PRE_DESIGN'},context,context_manifest:contextManifest(context)});
  let run=mkRun(c);const rendered=renderContext(c,{harnessVersion:'test',taskId:'tc03',type:'BUG_FIX',mode:'LOW'});
  for(const text of [rendered,renderRun(run)]){assert(text.includes(String(cap)));assert(text.includes(String(docs)));assert(text.includes('REQUIRED_ROUTE_PACK_ONLY'));assert(text.includes('NOT_PERFORMED'));}
  let response=buildBootstrapToolResponse(run,true);assert(response.content[0].text.includes('REQUIRED_ROUTE_PACK_ONLY'));assert(response.content[0].text.includes('NOT_PERFORMED'));
  assert.equal(response.structuredContent.context_manifest.byte_budget,cap);assert.equal(response.structuredContent.context_manifest.optional_graph_expansion,'NOT_PERFORMED');assert(!Object.hasOwn(response.structuredContent.context_manifest.documents[0],'content'));
  write('Root.md','x'.repeat(cap+1));snapshot();c=compile('NOTION_SNAPSHOT');run=mkRun(c);response=buildBootstrapToolResponse(run,true);
  assert(renderRun(run).includes('Root.md'));assert(response.content[0].text.includes('BLOCKED: REQUIRED CONTEXT NOT LOADED'));assert(response.content[0].text.includes('Root.md'));
  assert(!response.content[0].text.includes('WARNING: NOT LOADED optional context sources'));assert(!Object.hasOwn(response.structuredContent,'context_documents'));
}));

test('T-C03 CLI bootstrap and JSONL expose real compiled budget status',()=>fixture('LOW',({root,route,routePack,write,snapshot,cap,docs})=>{
  const {spawnSync}=require('node:child_process');
  const harness=path.join(root,'tools','harness');fs.mkdirSync(harness,{recursive:true});
  fs.cpSync(path.resolve(__dirname,'../lib'),path.join(harness,'lib'),{recursive:true});
  for(const file of ['cli.js','agent.js'])fs.copyFileSync(path.resolve(__dirname,'..',file),path.join(harness,file));
  function config(rel,value){const p=path.join(root,'harness',rel);fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,JSON.stringify(value));}
  config('HARNESS_MANIFEST.json',{...manifest,control_roots:route.control_roots});
  config('config/risk-model.json',require('../../../harness/config/risk-model.json'));
  config('config/lane-registry.json',{families:{}});config('config/task-types.json',{types:[{id:'BUG_FIX',keywords:['fix','bug']}],minimum_score:1,ambiguity_margin:1});
  config('config/routing-rules.json',{always:[],by_task:{BUG_FIX:[]},by_signal:{},by_mode:{}});
  config('config/gates.json',{gates:[{id:'required',stage:'BOOTSTRAP',severity:'BLOCK',applies:{},requirement:{kind:'internal',check:'required_sources_resolved'}}]});
  config('config/evidence-levels.json',{});
  config('notion/control-plane.json',{knowledge_data_source_id:'fixture-source',source_repository:'fixture/repo'});config('notion/route-pack.json',routePack);
  const task={version:1,id:'tc03-cli',intent:'Fix rendering bug',type:'BUG_FIX'};
  write('task.json',JSON.stringify(task));
  const opts={cwd:root,encoding:'utf8',timeout:15000,env:{...process.env,PSB_SEMANTIC_PROVIDER:'NOTION_SNAPSHOT',PSB_NOTION_SNAPSHOT:path.join(root,'snapshot.json')}};
  for(const content of ['é'.repeat(cap/2),'a'.repeat(cap+1)]){
    write('Root.md',content);snapshot();const good=Buffer.byteLength(content,'utf8')<=cap;
    const cli=spawnSync(process.execPath,[path.join(harness,'cli.js'),'bootstrap','--task','task.json','--out','.harness'],opts);
    assert.equal(cli.status,good?0:2,cli.stderr);const report=JSON.parse(cli.stdout),cm=JSON.parse(fs.readFileSync(path.join(report.output,'context.manifest.json'),'utf8'));
    assert.equal(cm.status,good?'RESOLVED':'BLOCKED');assert.equal(cm.byte_budget,cap);assert.equal(cm.document_budget,docs);assert.equal(cm.optional_graph_expansion,'NOT_PERFORMED');
    const rendered=fs.readFileSync(path.join(report.output,'RUN.md'),'utf8');assert(rendered.includes('REQUIRED_ROUTE_PACK_ONLY'));assert(rendered.includes(String(cap)));
    assert.equal(fs.existsSync(path.join(report.output,'CONTEXT.md')),good);
    const agent=spawnSync(process.execPath,[path.join(harness,'agent.js')],{...opts,input:JSON.stringify({operation:'bootstrap',task,include_context:false})+'\n'});
    assert.equal(agent.status,0,agent.stderr);const message=JSON.parse(agent.stdout);assert.equal(message.ok,true);assert.equal(message.result.context_manifest.status,cm.status);assert.equal(message.result.context_manifest.byte_budget,cap);
  }
}));
