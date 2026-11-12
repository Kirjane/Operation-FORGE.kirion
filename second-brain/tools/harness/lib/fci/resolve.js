'use strict';

// FCI-M02 Wave 1. Read-only feature/source reconstruction. No live runtime,
// merge, account, role, or Engineer-authority operations occur here.
const path=require('path');
const {inspectProject,inspectSource}=require('./project');
const {evaluateClaim,findConflicts,CLAIM_CLASSES}=require('./provenance');
const {assessAction}=require('./guard');

const ID=/^[a-z][a-z0-9._-]{0,79}$/;
const SHA256=/^[a-f0-9]{64}$/;
const SHA40=/^[a-f0-9]{40}$/;
const KINDS=new Set(['CONTRACT','CODE','TEST','RUNTIME','DOCUMENT']);

// Mirror the complete constraints in feature-context.schema.json and the
// referenced claim-provenance.schema.json, including additionalProperties:false.
// Keep this dependency-free validation narrow; new schema keywords need tests.
const SUBJECT=/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,239}$/;
const SUPERSESSION_REF=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,239}$/;
const FEATURE_ID=/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/;
function isRecord(obj){
  return obj!==null && typeof obj==='object' && !Array.isArray(obj) &&
    (Object.getPrototypeOf(obj)===Object.prototype || Object.getPrototypeOf(obj)===null);
}
function shape(obj,keys,required){
  if(!isRecord(obj))return false;
  const actual=Reflect.ownKeys(obj);
  return actual.every(k=>typeof k==='string'&&keys.includes(k)) &&
    required.every(k=>Object.prototype.hasOwnProperty.call(obj,k));
}
function stringRange(value,min,max){
  return typeof value==='string'&&value.length>=min&&
    (max===undefined||value.length<=max);
}
function optionalString(obj,key,min,max,pattern){
  return !Object.prototype.hasOwnProperty.call(obj,key) ||
    (stringRange(obj[key],min,max)&&(!pattern||pattern.test(obj[key])));
}
function validateFeature(feature){
  if(!shape(feature,['version','feature_id','repository','contract','sources','claims','required_claim_ids'],
    ['version','feature_id','repository','contract','sources','claims']) ||
    feature.version!==1||!FEATURE_ID.test(feature.feature_id||''))
    return 'INVALID_FEATURE_ID';
  if(!shape(feature.repository,['path','head','branch'],['path','head'])||
     !stringRange(feature.repository.path,1)||!SHA40.test(feature.repository.head||'')||
     !optionalString(feature.repository,'branch',1))
    return 'INVALID_REPOSITORY_PIN';
  if(!shape(feature.contract,['source_id','revision'],['source_id','revision'])||
     !ID.test(feature.contract.source_id||'')||
     !Number.isSafeInteger(feature.contract.revision)||feature.contract.revision<1)
    return 'INVALID_CONTRACT_PIN';
  if(!Array.isArray(feature.sources)||!feature.sources.length||feature.sources.length>100||
     !Array.isArray(feature.claims)||feature.claims.length>200) return 'INVALID_FEATURE_COLLECTIONS';
  const sourceIds=new Set(),claimIds=new Set();
  for(const source of feature.sources){
    if(!shape(source,['id','path','sha256','kind','required'],['id','path','sha256','kind'])||
       !ID.test(source.id||'')||!stringRange(source.path,1,500)||
       !SHA256.test(source.sha256||'')||!KINDS.has(source.kind)||
       (Object.prototype.hasOwnProperty.call(source,'required')&&typeof source.required!=='boolean')||
       sourceIds.has(source.id)) return 'INVALID_OR_DUPLICATE_SOURCE';
    sourceIds.add(source.id);
  }
  const contract=feature.sources.find(x=>x.id===feature.contract.source_id);
  if(!contract||contract.kind!=='CONTRACT') return 'CONTRACT_SOURCE_NOT_DECLARED';
  for(const c of feature.claims){
    if(!shape(c,['id','subject','value','classification','source_id','source_sha256',
      'contract_revision','approval_ref','evidence_ref','superseded_by'],
      ['id','subject','value','classification','source_id'])||
       !ID.test(c.id||'')||claimIds.has(c.id)||!sourceIds.has(c.source_id)||
       !CLAIM_CLASSES.has(c.classification)||!SUBJECT.test(c.subject||'')||
       !stringRange(c.value,1,2000)||
       (Object.prototype.hasOwnProperty.call(c,'source_sha256')&&!SHA256.test(c.source_sha256||''))||
       (Object.prototype.hasOwnProperty.call(c,'contract_revision')&&
        (!Number.isSafeInteger(c.contract_revision)||c.contract_revision<1))||
       !optionalString(c,'approval_ref',1,240)||
       !optionalString(c,'evidence_ref',1,240)||
       !optionalString(c,'superseded_by',1,240,SUPERSESSION_REF))
      return 'INVALID_OR_DUPLICATE_CLAIM';
    claimIds.add(c.id);
  }
  if(Object.prototype.hasOwnProperty.call(feature,'required_claim_ids')&&
     (!Array.isArray(feature.required_claim_ids)||
      new Set(feature.required_claim_ids).size!==feature.required_claim_ids.length||
      feature.required_claim_ids.some(id=>!ID.test(id||''))))
    return 'INVALID_REQUIRED_CLAIM_IDS';
  return null;
}

function blocked(code,detail={}){
  return {version:1,status:'BLOCKED',code,authority_granted:false,
    sources:[],claims:[],conflicts:[],action_gate:assessAction('BLOCKED',[],[]),...detail};
}

function resolveFeatureContext(feature,options={}){
  const invalid=validateFeature(feature);
  if(invalid) return blocked(invalid);
  // Freeze the declared input at the beginning of the source inspection;
  // callbacks may mutate their own original input object but not this snapshot.
  feature=JSON.parse(JSON.stringify(feature));
  // Configured by a trusted host, never from feature input. The caller cannot
  // direct the resolver at arbitrary private paths by supplying a repository path.
  if(!Array.isArray(options.allowed_roots)||!options.allowed_roots.length||
     !options.allowed_roots.some(root=>typeof root==='string'&&
       path.resolve(root)===path.resolve(feature.repository.path)))
    return blocked('REPOSITORY_NOT_ALLOWLISTED');
  const repo=inspectProject(feature.repository);
  if(repo.status!=='VERIFIED') return {
    ...blocked(repo.code||'SOURCE_NOT_VERIFIED'),status:repo.status,
    repository:repo
  };
  const sources=feature.sources.map(source=>inspectSource(repo,source));
  const badSource=sources.find(source=>source.status!=='VERIFIED');
  if(badSource) return {
    ...blocked('DECLARED_SOURCE_NOT_VERIFIED'),status:badSource.status,
    feature_id:feature.feature_id,repository:{head:repo.head,branch:repo.branch,scope:repo.scope},
    sources
  };
  const sourceMap=new Map(sources.map(source=>[source.id,source]));
  // Recheck local Git reality after reading sources, preventing a source/HEAD
  // transition during compilation from being reported as a coherent snapshot.
  const stable=inspectProject(feature.repository);
  if(stable.status!=='VERIFIED') return {
    ...blocked('SOURCE_CHANGED_DURING_VERIFICATION'),status:stable.status,
    feature_id:feature.feature_id,repository:stable,sources
  };
  const claims=feature.claims.map(claim=>evaluateClaim(feature,claim,sourceMap.get(claim.source_id),options.verifiers||{}));
  // Attesters are external synchronous callbacks: they can mutate the repo.
  // Recheck Git *after* all callbacks before returning any evidence readiness.
  const afterAttestation=inspectProject(feature.repository);
  if(afterAttestation.status!=='VERIFIED') return {
    ...blocked('SOURCE_CHANGED_AFTER_ATTESTATION'),
    status:afterAttestation.status,feature_id:feature.feature_id,
    repository:afterAttestation,sources
  };
  const conflicts=findConflicts(claims);
  const state=conflicts.length?'CONFLICTED':'RESOLVED';
  return {
    version:1,feature_id:feature.feature_id,status:state,
    // RESOLVED means source pins checked, not that every claim is true.
    context_scope:'LOCAL_GIT_SOURCES_ONLY',
    authority_granted:false,
    repository:{head:repo.head,branch:repo.branch,scope:repo.scope},
    contract:{source_id:feature.contract.source_id,revision:feature.contract.revision},
    sources,claims,conflicts,
    action_gate:assessAction(state,claims,feature.required_claim_ids||[])
  };
}

module.exports={resolveFeatureContext,validateFeature};
