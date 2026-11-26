const crypto=require('crypto');
const {canonicalJson,sha256}=require('./io');
const {buildTask,computeRun}=require('./runtime');
const {evaluateGates,STAGE_ORDER}=require('./gates');

const SESSION_VERSION=2;
const SESSION_KEY_ENV='PSB_HARNESS_SESSION_KEY';

function stageIndex(stage){const i=STAGE_ORDER.indexOf(stage);if(i<0) throw new Error(`Unknown lifecycle stage: ${stage}`);return i;}
function evidenceHash(evidence){return sha256(canonicalJson(evidence||{version:1,claims:{}}));}
function targetRealityHash(repository){return sha256(canonicalJson(repository||{status:'NOT_REQUESTED'}));}
function fingerprints(run,ids){return {runtime_sha256:run.runtime_fingerprint.sha256,config_sha256:run.config_sha256,task_sha256:ids.task_sha256,context_sha256:ids.context_sha256};}
function sessionKey(options={}){return options.sessionKey||process.env[SESSION_KEY_ENV]||null;}
function digest(value,key){const serialized=canonicalJson(value);return key?crypto.createHmac('sha256',key).update(serialized).digest('hex'):sha256(serialized);}
function makeEvent(history,kind,payload){
  const base={sequence:history.length,kind,previous_event_sha256:history.length?history[history.length-1].event_sha256:null,...payload};
  return {...base,event_sha256:sha256(canonicalJson(base))};
}
function verifyHistory(history){
  if(!Array.isArray(history)) return {valid:false,reason:'history is not an array'};
  let previous=null;
  for(let i=0;i<history.length;i++){
    const event=history[i];
    if(!event||event.sequence!==i) return {valid:false,reason:`history sequence mismatch at ${i}`};
    if(event.previous_event_sha256!==previous) return {valid:false,reason:`history chain mismatch at ${i}`};
    const {event_sha256,...base}=event,expected=sha256(canonicalJson(base));
    if(event_sha256!==expected) return {valid:false,reason:`history event hash mismatch at ${i}`};
    previous=event_sha256;
  }
  return {valid:true,head:previous};
}
function sealSession(session,options={}){
  const key=sessionKey(options),base={...session};delete base.integrity_sha256;
  base.integrity_mode=key?'HMAC_SHA256':'SHA256';
  return {...base,integrity_sha256:digest(base,key)};
}
function verifySessionIntegrity(session,options={}){
  if(!session||![1,SESSION_VERSION].includes(session.version)) return {valid:false,reason:'supported lifecycle session version required'};
  const history=verifyHistory(session.history);if(!history.valid) return history;
  const key=sessionKey(options);
  if(session.integrity_mode==='HMAC_SHA256'&&!key) return {valid:false,reason:`${SESSION_KEY_ENV} is required to verify this signed session`};
  if(!['SHA256','HMAC_SHA256'].includes(session.integrity_mode)) return {valid:false,reason:'unknown or missing integrity mode'};
  if(session.integrity_mode==='SHA256'&&key) return {valid:false,reason:'session was created unsigned but runtime now requires HMAC; create a new session'};
  const base={...session};delete base.integrity_sha256;
  const expected=digest(base,session.integrity_mode==='HMAC_SHA256'?key:null);
  return expected===session.integrity_sha256?{valid:true,history_head:history.head}:{valid:false,reason:'session integrity digest mismatch'};
}
function stageCheckpoint(run,ids,stage){
  const basis={stage,effective_stage:run.route?.evaluated_stage||null,stage_run_id:ids.run_id,task_sha256:ids.task_sha256,runtime_sha256:run.runtime_fingerprint.sha256,config_sha256:run.config_sha256,context_sha256:ids.context_sha256,context_manifest:ids.context_manifest,provider:run.context.provider||null,snapshot_sha256:run.context.snapshot_sha256||null,source_root:run.harness_git.top_level||run.harness_git.requested_path||null,target_repository_sha256:targetRealityHash(run.target_repository)};
  return {...basis,checkpoint_sha256:sha256(canonicalJson(basis))};
}
function gateEvent(history,stage,evaluation,run,evidence,checkpoint){
  return makeEvent(history,'GATE_EVALUATION',{stage,verdict:evaluation.verdict,blocking_failures:evaluation.blocking_failures,evidence_sha256:evidenceHash(evidence),target_repository:run.target_repository,target_repository_sha256:targetRealityHash(run.target_repository),checkpoint});
}
function createSession(taskInput,evidence={version:1,claims:{}},options={}){
  const through=options.throughStage||'BOOTSTRAP',max=stageIndex(through),history=[];
  const initialRun=buildTask(taskInput,{...options,stage:'BOOTSTRAP'}),initialIds=computeRun(initialRun);
  const accepted_target_sha256=targetRealityHash(initialRun.target_repository);
  let current_stage=null,blocked_stage=null,last_evaluation=null,checkpoint=stageCheckpoint(initialRun,initialIds,'BOOTSTRAP');
  for(let i=0;i<=max;i++){
    const stage=STAGE_ORDER[i],run=i===0?initialRun:buildTask(taskInput,{...options,stage});
    const ids=i===0?initialIds:computeRun(run),attempt=stageCheckpoint(run,ids,stage);
    if(attempt.target_repository_sha256!==accepted_target_sha256||attempt.task_sha256!==initialIds.task_sha256||
      attempt.runtime_sha256!==initialRun.runtime_fingerprint.sha256||attempt.config_sha256!==initialRun.config_sha256||
      attempt.provider!==checkpoint.provider||attempt.source_root!==checkpoint.source_root){
      blocked_stage=stage;break;
    }
    const evaluation=evaluateGates(run.cfg.gates,run.gateCtx,evidence,{throughStage:stage});
    history.push(gateEvent(history,stage,evaluation,run,evidence,attempt));last_evaluation=evaluation;
    if(evaluation.verdict==='BLOCK'){blocked_stage=stage;break;}
    current_stage=stage;checkpoint=attempt;
  }
  const raw={
    version:SESSION_VERSION,
    session_id:`session-${sha256(canonicalJson({run_id:initialIds.run_id,target:accepted_target_sha256})).slice(0,16)}`,
    run_id:initialIds.run_id,
    ...fingerprints(initialRun,initialIds),
    context_sha256:checkpoint.context_sha256,
    checkpoint,
    accepted_target_sha256,
    current_stage,
    blocked_stage,
    status:blocked_stage?'BLOCKED':'ACTIVE',
    task_id:initialRun.task.id,
    harness_version:initialRun.cfg.manifest.version,
    protocol_version:initialRun.cfg.manifest.protocol_version,
    harness_git:initialRun.harness_git,
    target_repository:initialRun.target_repository,
    last_evaluation,
    history
  };
  return sealSession(raw,options);
}
function assertFresh(session,run,ids){
  const now=fingerprints(run,ids),changed=[];
  for(const key of Object.keys(now)) if(session[key]!==now[key]) changed.push(key);
  const expectedRun=session.version===2?session.checkpoint?.stage_run_id:session.run_id;
  if(expectedRun!==ids.run_id) changed.push('run_id');
  if(session.version===2){
    if(session.checkpoint?.provider!==(run.context.provider||null)) changed.push('provider');
    if(session.checkpoint?.source_root!==(run.harness_git.top_level||run.harness_git.requested_path||null)) changed.push('source_root');
  }
  if(session.task_id!==run.task.id) changed.push('task_id');
  if(session.harness_version!==run.cfg.manifest.version) changed.push('harness_version');
  if(session.protocol_version!==run.cfg.manifest.protocol_version) changed.push('protocol_version');
  return {fresh:changed.length===0,changed:[...new Set(changed)],current:now};
}
function preflightSession(session,taskInput,options={}){
  const integrity=verifySessionIntegrity(session,options);
  if(!integrity.valid) return {ok:false,result:{verdict:'BLOCK',status:'TAMPERED',reason:integrity.reason,session}};
  const stage=session.version===2?(session.current_stage||'BOOTSTRAP'):'PRE_DESIGN';
  const run=buildTask(taskInput,{...options,stage}),ids=computeRun(run),fresh=assertFresh(session,run,ids);
  if(!fresh.fresh) return {ok:false,result:{verdict:'BLOCK',status:'STALE',reason:`Harness/task/context fingerprint changed: ${fresh.changed.join(', ')}. Create a new session.`,changed:fresh.changed,session}};
  if(session.version!==SESSION_VERSION) return {ok:false,result:{verdict:'BLOCK',status:'MIGRATION_REQUIRED',reason:'Historical v1 session is readable but cannot acquire v2 stage authority; create a new session.',session}};
  return {ok:true,run,ids};
}
function assertTargetAccepted(session,run){
  const current=targetRealityHash(run.target_repository);
  return current===session.accepted_target_sha256?{accepted:true,current}:{accepted:false,current,accepted_sha256:session.accepted_target_sha256};
}
function advanceSession(session,taskInput,evidence,targetStage,options={}){
  const preflight=preflightSession(session,taskInput,options);if(!preflight.ok) return preflight.result;
  const {run}=preflight,target=assertTargetAccepted(session,run);
  if(!target.accepted) return {verdict:'BLOCK',status:'TARGET_DRIFT',reason:'Target repository reality changed. Commit/clean the intended state and explicitly refresh the target checkpoint before advancing.',accepted_target_sha256:target.accepted_sha256,current_target_sha256:target.current,current_target_repository:run.target_repository,session};
  const requested=stageIndex(targetStage),current=session.current_stage===null?-1:stageIndex(session.current_stage);
  if(requested!==current+1) return {verdict:'BLOCK',status:'INVALID_TRANSITION',reason:`Next allowed stage is ${STAGE_ORDER[current+1]||'NONE'}, not ${targetStage}.`,session};
  const stageRun=buildTask(taskInput,{...options,stage:targetStage}),stageIds=computeRun(stageRun),checkpoint=stageCheckpoint(stageRun,stageIds,targetStage);
  if(checkpoint.target_repository_sha256!==session.accepted_target_sha256) return {verdict:'BLOCK',status:'TARGET_DRIFT',reason:'Target changed during stage compilation.',session};
  if(checkpoint.task_sha256!==session.task_sha256||checkpoint.runtime_sha256!==session.runtime_sha256||
    checkpoint.config_sha256!==session.config_sha256||checkpoint.provider!==session.checkpoint.provider||
    checkpoint.source_root!==session.checkpoint.source_root) return {verdict:'BLOCK',status:'STALE',reason:'Task, runtime, configuration or provider changed during stage compilation.',session};
  const normalizedEvidence=evidence||{version:1,claims:{}},evaluation=evaluateGates(stageRun.cfg.gates,stageRun.gateCtx,normalizedEvidence,{throughStage:targetStage});
  const event=gateEvent(session.history,targetStage,evaluation,stageRun,normalizedEvidence,checkpoint);
  const updated={...session,target_repository:stageRun.target_repository,last_evaluation:evaluation,history:[...session.history,event]};
  const stage_context={checkpoint,documents:stageRun.context.status==='RESOLVED'?stageRun.context.documents:[]};
  if(evaluation.verdict==='BLOCK') return {verdict:'BLOCK',status:'BLOCKED',reason:`BLOCK gate failed at ${targetStage}.`,stage_context,session:sealSession({...updated,blocked_stage:targetStage,status:'BLOCKED'},options)};
  return {verdict:'PASS',status:'ADVANCED',stage_context,session:sealSession({...updated,checkpoint,context_sha256:checkpoint.context_sha256,current_stage:targetStage,blocked_stage:null,status:'ACTIVE'},options)};
}
function refreshTarget(session,taskInput,reason,options={}){
  if(typeof reason!=='string'||!reason.trim()) throw new Error('target refresh requires a non-empty reason');
  const preflight=preflightSession(session,taskInput,options);if(!preflight.ok) return preflight.result;
  const {run}=preflight,current=session.current_stage===null?-1:stageIndex(session.current_stage);
  if(current<stageIndex('PRE_IMPLEMENTATION')) return {verdict:'BLOCK',status:'REFRESH_NOT_ALLOWED',reason:'Target reality may only be refreshed after PRE_IMPLEMENTATION has been entered.',session};
  if(run.target_repository.status==='NOT_REQUESTED') return {verdict:'BLOCK',status:'NO_TARGET_REPOSITORY',reason:'Task does not declare a target repository.',session};
  if(run.target_repository.status!=='RESOLVED') return {verdict:'BLOCK',status:'TARGET_UNRESOLVED',reason:run.target_repository.reason||'Target repository reality is unresolved.',session};
  if(!run.target_repository.clean) return {verdict:'BLOCK',status:'TARGET_DIRTY',reason:'Refusing to adopt a dirty target repository checkpoint. Commit or otherwise restore a clean intentional state first.',current_target_repository:run.target_repository,session};
  if(['requested_path','top_level','branch','detached'].some(key=>session.target_repository[key]!==run.target_repository[key])) return {verdict:'BLOCK',status:'TARGET_IDENTITY_DRIFT',reason:'Target refresh cannot change the repository path or branch identity.',session};
  const next=targetRealityHash(run.target_repository);
  if(next===session.accepted_target_sha256) return {verdict:'PASS',status:'TARGET_UNCHANGED',session};
  const checkpoint=stageCheckpoint(run,preflight.ids,session.current_stage);
  const event=makeEvent(session.history,'TARGET_REFRESH',{stage:session.current_stage,reason:reason.trim(),previous_target_sha256:session.accepted_target_sha256,target_repository_sha256:next,target_repository:run.target_repository,checkpoint});
  const updated=sealSession({...session,checkpoint,accepted_target_sha256:next,target_repository:run.target_repository,history:[...session.history,event]},options);
  return {verdict:'PASS',status:'TARGET_REFRESHED',session:updated};
}
module.exports={SESSION_VERSION,SESSION_KEY_ENV,createSession,advanceSession,refreshTarget,assertFresh,targetRealityHash,evidenceHash,verifyHistory,sealSession,verifySessionIntegrity};
