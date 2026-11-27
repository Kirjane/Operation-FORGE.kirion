'use strict';

// Evidence readiness is deliberately distinct from action authorization.
// A caller may use an eligible context in a separate, approved Forge flow;
// this module cannot grant merge, role, implementation, or release permissions.
function assessAction(state,claims,requiredClaimIds=[]){
  if(state!=='RESOLVED') return {
    status:'BLOCKED',code:'CONTEXT_NOT_RESOLVED',
    authority_granted:false,evidence_ready:false
  };
  if(!Array.isArray(requiredClaimIds)||requiredClaimIds.length===0) return {
    status:'BLOCKED',code:'NO_REQUIRED_CLAIMS',authority_granted:false,evidence_ready:false
  };
  const byId=new Map(claims.map(c=>[c.id,c]));
  const invalid=requiredClaimIds.filter(id=>byId.get(id)?.status!=='VERIFIED');
  if(invalid.length) return {
    status:'BLOCKED',code:'REQUIRED_CLAIMS_UNVERIFIED',
    claim_ids:invalid,authority_granted:false,evidence_ready:false
  };
  return {
    status:'EVIDENCE_READY',code:'SEPARATE_FORGE_AUTHORIZATION_REQUIRED',
    authority_granted:false,evidence_ready:true
  };
}
module.exports={assessAction};
