'use strict';

const {checkFreshness}=require('./freshness');
const CLAIM_CLASSES=new Set([
  'OPERATOR_APPROVED','CODE_VERIFIED','TEST_VERIFIED',
  'RUNTIME_OBSERVED','INFERRED','UNKNOWN'
]);

// All verifiers are OUT-OF-BAND host adapters, not fields in a user-supplied
// context manifest. By default none exist and no reported authority is promoted.
function safeAttestation(fn,details,expected){
  if(typeof fn!=='function') return false;
  try {
    const proof=fn(Object.freeze(details));
    if(!proof||proof.verified!==true) return false;
    return Object.entries(expected).every(([key,value])=>proof[key]===value);
  } catch {return false;}
}

function evaluateClaim(feature,claim,source,verifiers={}){
  const basis={id:claim.id,subject:claim.subject,value:claim.value,
    classification:claim.classification,source_id:claim.source_id};
  if(!CLAIM_CLASSES.has(claim.classification)) return {...basis,status:'BLOCKED',code:'INVALID_CLAIM_CLASS'};
  const fresh=checkFreshness(feature,claim,source);
  if(fresh.status!=='CURRENT') return {...basis,...fresh};
  if(claim.classification==='INFERRED') return {...basis,status:'INFERRED',code:'INFERENCE_NOT_EVIDENCE'};
  if(claim.classification==='UNKNOWN') return {...basis,status:'UNKNOWN',code:'UNKNOWN_NOT_EVIDENCE'};

  const details={feature_id:feature.feature_id,repository_head:feature.repository.head,
    contract_revision:feature.contract.revision,claim,source};
  if(claim.classification==='OPERATOR_APPROVED'){
    if(source.kind!=='CONTRACT'||claim.source_id!==feature.contract.source_id||
       !claim.approval_ref || claim.contract_revision!==feature.contract.revision)
      return {...basis,status:'BLOCKED',code:'APPROVAL_CONTEXT_INCOMPLETE'};
    const expected={verified:true,feature_id:feature.feature_id,
      approval_ref:claim.approval_ref,revision:feature.contract.revision,
      source_sha256:source.sha256};
    return safeAttestation(verifiers.authority,details,expected)
      ? {...basis,status:'VERIFIED',code:'EXTERNAL_AUTHORITY_ATTESTED'}
      : {...basis,status:'UNVERIFIED',code:'AUTHORITY_NOT_ATTESTED'};
  }
  if(claim.classification==='CODE_VERIFIED'){
    if(source.kind!=='CODE') return {...basis,status:'BLOCKED',code:'CODE_SOURCE_KIND_MISMATCH'};
    const expected={verified:true,repository_head:feature.repository.head,
      source_sha256:source.sha256,claim_id:claim.id};
    return safeAttestation(verifiers.code,details,expected)
      ? {...basis,status:'VERIFIED',code:'EXTERNAL_CODE_CHECK_ATTESTED'}
      : {...basis,status:'UNVERIFIED',code:'CODE_CLAIM_NOT_ATTESTED'};
  }
  if(!claim.evidence_ref||source.kind!==(claim.classification==='TEST_VERIFIED'?'TEST':'RUNTIME'))
    return {...basis,status:'BLOCKED',code:'EVIDENCE_CONTEXT_INCOMPLETE'};
  const expected={verified:true,repository_head:feature.repository.head,
    source_sha256:source.sha256,evidence_ref:claim.evidence_ref,claim_id:claim.id};
  const type=claim.classification==='TEST_VERIFIED'?'execution':'runtime';
  return safeAttestation(verifiers[type],details,expected)
    ? {...basis,status:'VERIFIED',code:'EXTERNAL_'+type.toUpperCase()+'_ATTESTED'}
    : {...basis,status:'UNVERIFIED',code:'EVIDENCE_NOT_ATTESTED'};
}

function findConflicts(claims){
  const active=new Map(),conflicts=[];
  for(const c of claims){
    if(c.status!=='VERIFIED') continue;
    const previous=active.get(c.subject);
    if(previous && previous.value!==c.value) conflicts.push({
      subject:c.subject,claim_ids:[previous.id,c.id],code:'VERIFIED_CLAIMS_DISAGREE'
    });
    else if(!previous) active.set(c.subject,c);
  }
  return conflicts;
}
module.exports={CLAIM_CLASSES,evaluateClaim,findConflicts};
