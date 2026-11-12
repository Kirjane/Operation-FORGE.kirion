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

function validateFeature(feature){
  if(!feature||feature.version!==1||typeof feature.feature_id!=='string'||
     !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(feature.feature_id))
    return 'INVALID_FEATURE_ID';
  if(!feature.repository||typeof feature.repository.path!=='string'||
     !SHA40.test(feature.repository.head||'')||
     (feature.repository.branch!==undefined&&(typeof feature.repository.branch!=='string'||!feature.repository.branch.trim())))
    return 'INVALID_REPOSITORY_PIN';
  if(!feature.contract||!ID.test(feature.contract.source_id||'')||
     !Number.isSafeInteger(feature.contract.revision)||feature.contract.revision<1)
    return 'INVALID_CONTRACT_PIN';
  if(!Array.isArray(feature.sources)||!feature.sources.length||feature.sources.length>100||
     !Array.isArray(feature.claims)||feature.claims.length>200) return 'INVALID_FEATURE_COLLECTIONS';
  const sourceIds=new Set(),claimIds=new Set();
  for(const source of feature.sources){
    if(!source||!ID.test(source.id||'')||typeof source.path!=='string'||
       !SHA256.test(source.sha256||'')||!KINDS.has(source.kind)||
       sourceIds.has(source.id)) return 'INVALID_OR_DUPLICATE_SOURCE';
    sourceIds.add(source.id);
  }
  const contract=feature.sources.find(x=>x.id===feature.contract.source_id);
  if(!contract||contract.kind!=='CONTRACT') return 'CONTRACT_SOURCE_NOT_DECLARED';
  for(const c of feature.claims){
    if(!c||!ID.test(c.id||'')||claimIds.has(c.id)||
       !sourceIds.has(c.source_id)||!CLAIM_CLASSES.has(c.classification)||
       typeof c.subject!=='string'||!c.subject.trim()||
       typeof c.value!=='string'||!c.value.trim()||
       (c.source_sha256!==undefined&&!SHA256.test(c.source_sha256))||
       (c.contract_revision!==undefined&&(!Number.isSafeInteger(c.contract_revision)||c.contract_revision<1)))
      return 'INVALID_OR_DUPLICATE_CLAIM';
    claimIds.add(c.id);
  }
  if(feature.required_claim_ids!==undefined&&(!Array.isArray(feature.required_claim_ids)||
     new Set(feature.required_claim_ids).size!==feature.required_claim_ids.length||
     feature.required_claim_ids.some(id=>!ID.test(id)))) return 'INVALID_REQUIRED_CLAIM_IDS';
  return null;
}

function blocked(code,detail={}){
  return {version:1,status:'BLOCKED',code,authority_granted:false,
    sources:[],claims:[],conflicts:[],action_gate:assessAction('BLOCKED',[],[]),...detail};
}

function resolveFeatureContext(feature,options={}){
  const invalid=validateFeature(feature);
  if(invalid) return blocked(invalid);
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
  const claims=feature.claims.map(claim=>evaluateClaim(feature,claim,sourceMap.get(claim.source_id),options.verifiers||{}));
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
