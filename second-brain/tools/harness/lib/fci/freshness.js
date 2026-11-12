'use strict';

// Event-triggered freshness checks; no arbitrary time-to-live assumptions.
function checkFreshness(feature,claim,source){
  if(claim.superseded_by) return {
    status:'SUPERSEDED',code:'SUPERSEDED_CLAIM'
    // Untrusted free-form memory metadata is never copied into agent output.
  };
  if(!source||source.status!=='VERIFIED') return {
    status:source&&source.status==='STALE'?'STALE':'BLOCKED',
    code:'CLAIM_SOURCE_NOT_VERIFIED'
  };
  if(claim.source_sha256 && claim.source_sha256!==source.sha256) return {
    status:'STALE',code:'CLAIM_SOURCE_DIGEST_DRIFT'
  };
  if(claim.contract_revision!==undefined && claim.contract_revision!==feature.contract.revision) return {
    status:'STALE',code:'CONTRACT_REVISION_DRIFT',
    expected_revision:feature.contract.revision,claim_revision:claim.contract_revision
  };
  return {status:'CURRENT',code:'SOURCE_AND_REVISION_CURRENT'};
}
module.exports={checkFreshness};
