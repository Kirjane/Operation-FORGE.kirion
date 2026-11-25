// T-C01: fixed safety oracles, runnable independently and from test/run.js.
const test=require('node:test');
const assert=require('node:assert/strict');
const {normalizeTask}=require('../lib/io');
const {inferSignals}=require('../lib/classify');
const {scoreRisk}=require('../lib/risk');
const cfg=require('../../../harness/config/risk-model.json');
const task=(extra={})=>({version:1,id:'tc01',intent:'Fix production security bug',type:'BUG_FIX',...extra});
function score(extra={}){const t=normalizeTask(task(extra));return scoreRisk(t,t.type,inferSignals(t),cfg);}
test('T-C01 production security remains critical under blast-radius calibration',()=>{
  assert.equal(score().mode,'CRITICAL');
  const r=score({risk_overrides:{blast_radius:0}});
  assert.equal(r.mode,'CRITICAL');assert.equal(r.dimensions.blast_radius,3);
});
test('T-C01 explicit false cannot suppress inferred safety signals',()=>{
  const t=normalizeTask(task({signals:{production:false,security:false,deployment:false}}));
  const s=inferSignals(t);
  assert.equal(s.production,true);assert.equal(s.security,true);assert.equal(s.deployment,true);
  assert.equal(scoreRisk(t,t.type,s,cfg).mode,'CRITICAL');
});
test('T-C01 every configured safety signal is protected against explicit false',()=>{
  const {SIGNAL_KEYWORDS}=require('../lib/classify');
  const protectedNames=new Set([...Object.keys(cfg.signal_minimums),...cfg.critical_triggers.flatMap(t=>t.all_signals||[])]);
  for(const name of protectedNames){
    const t=normalizeTask(task({intent:`Fix ${SIGNAL_KEYWORDS[name][0]} bug`,signals:{[name]:false}}));
    assert.equal(inferSignals(t)[name],true,`mandatory signal ${name} was suppressed`);
  }
});
test('T-C01 safety minima are protected independently of critical triggers',()=>{
  const r=score({intent:'Fix payment database permission vulnerability backup migration',risk_overrides:Object.fromEntries(cfg.dimensions.map(d=>[d,0]))});
  assert.equal(r.dimensions.financial_impact,3);assert.equal(r.dimensions.data_sensitivity,2);
  assert.equal(r.dimensions.authentication_impact,3);assert.equal(r.dimensions.availability_impact,3);
  assert.equal(r.dimensions.migration_risk,3);
});
for(const value of ['0','bad',null,true,{},[],NaN,Infinity,-1,5,1.5]){
  test(`T-C01 reject malformed dimension ${String(value)} (${typeof value})`,()=>{
    const input=task({risk_overrides:{blast_radius:value}});
    assert.throws(()=>normalizeTask(input),/risk_overrides/);
    assert.throws(()=>scoreRisk(input,input.type,{production:true,security:true},cfg),/risk_overrides/);
  });
}
for(const value of [null,[],0,'bad',true]){
  test(`T-C01 reject malformed override container ${JSON.stringify(value)}`,()=>{
    assert.throws(()=>normalizeTask(task({risk_overrides:value})),/risk_overrides/);
  });
}
test('T-C01 reject nonboolean signal rather than coerce it',()=>{
  for(const value of ['false',0,null]) assert.throws(()=>normalizeTask(task({signals:{security:value}})),/signals/);
});
test('T-C01 production recovery and task floors survive downward calibration',()=>{
  assert.equal(score({intent:'Fix production recovery bug',risk_overrides:{blast_radius:0,operational_impact:0}}).mode,'CRITICAL');
  assert.equal(score({intent:'Correct defect',type:'PRODUCTION_RECOVERY',risk_overrides:Object.fromEntries(cfg.dimensions.map(d=>[d,0]))}).mode,'CRITICAL');
  assert.equal(score({intent:'Correct defect',type:'SECURITY_HARDENING',risk_overrides:Object.fromEntries(cfg.dimensions.map(d=>[d,0]))}).mode,'HIGH');
});
test('T-C01 valid upward and ordinary downward calibration still work',()=>{
  const down=score({intent:'Fix rendering bug',risk_overrides:{blast_radius:0}});
  assert.equal(down.dimensions.blast_radius,0);assert.equal(down.mode,'LOW');
  assert.equal(score({risk_overrides:{blast_radius:4}}).dimensions.blast_radius,4);
  const t=normalizeTask(task({intent:'Fix UI bug',signals:{ui:false,security:true}}));
  const s=inferSignals(t);assert.equal(s.ui,false);assert.equal(s.security,true);
});

test('T-C01 CLI and JSONL validate raw task controls before lossy intake',()=>{
  const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
  const {spawnSync}=require('node:child_process');
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'tc01-transport-'));
  const harness=path.join(root,'tools','harness');
  function write(rel,value){const p=path.join(root,rel);fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,JSON.stringify(value));}
  try{
    fs.mkdirSync(harness,{recursive:true});fs.cpSync(path.resolve(__dirname,'../lib'),path.join(harness,'lib'),{recursive:true});
    for(const file of ['cli.js','agent.js'])fs.copyFileSync(path.resolve(__dirname,'..',file),path.join(harness,file));
    const manifest=require('../../../harness/HARNESS_MANIFEST.json');
    write('harness/HARNESS_MANIFEST.json',{...manifest,control_roots:[]});
    write('harness/config/risk-model.json',cfg);
    write('harness/config/lane-registry.json',{families:{}});
    write('harness/config/task-types.json',{types:[{id:'BUG_FIX',keywords:['fix','bug']}],minimum_score:1,ambiguity_margin:1});
    write('harness/config/routing-rules.json',{always:[],by_task:{BUG_FIX:[]},by_signal:{},by_mode:{}});
    write('harness/config/gates.json',{gates:[]});write('harness/config/evidence-levels.json',{});
    write('harness/notion/control-plane.json',{default_provider:'GIT'});write('harness/notion/route-pack.json',{});
    const options={cwd:root,encoding:'utf8',env:{...process.env,PSB_SEMANTIC_PROVIDER:'GIT'},timeout:15000};
    const request=(input)=>({operation:'intake',input:{intent:'Fix production security bug',type:'BUG_FIX',...input}});
    const inputs=[request({}),request({risk_overrides:{blast_radius:0}}),request({signals:{security:false}}),request({risk_overrides:0}),request({risk_overrides:{blast_radius:'0'}}),request({signals:'false'})];
    const agent=spawnSync(process.execPath,[path.join(harness,'agent.js')],{...options,input:inputs.map(x=>JSON.stringify(x)).join('\n')+'\n'});
    assert.equal(agent.status,0,agent.stderr);const lines=agent.stdout.trim().split('\n').map(JSON.parse);assert.equal(lines.length,inputs.length);
    assert.equal(lines[0].ok,true);assert.equal(lines[0].result.risk.mode,'CRITICAL');
    for(const i of [1,2]){assert.equal(lines[i].ok,true);assert.equal(lines[i].result.risk.mode,'CRITICAL');}
    for(const i of [3,4,5]){assert.equal(lines[i].ok,false);assert.match(lines[i].error.message,/risk_overrides|signals/);}
    write('task.json',task({risk_overrides:{blast_radius:'0'}}));
    const cli=spawnSync(process.execPath,[path.join(harness,'cli.js'),'route','--task','task.json'],options);
    assert.equal(cli.status,1,cli.stdout);assert.match(cli.stderr,/risk_overrides/);
    write('task.json',task({risk_overrides:{blast_radius:0}}));
    const good=spawnSync(process.execPath,[path.join(harness,'cli.js'),'route','--task','task.json'],options);
    assert.equal(good.status,0,good.stderr);assert.equal(JSON.parse(good.stdout).risk.mode,'CRITICAL');
  }finally{fs.rmSync(root,{recursive:true,force:true});}
});
