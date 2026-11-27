'use strict';
// Independent host policy: no request-provided policy, proof or key.
const fs=require('fs');
const path=require('path');
const crypto=require('crypto');
const {canonicalJson,sha256,normalizeTask}=require('../io');
const {validateFeature}=require('./resolve');
const SHA=/^[a-f0-9]{64}$/;

function intentDigest(task,target){
  const {feature_context,...intent}=normalizeTask(task);
  const {sha,...repository}=intent.repository;
  return sha256(canonicalJson({...intent,repository:{...repository,path:target.top_level}}));
}
function mac(key,payload){return crypto.createHmac('sha256',key).update(canonicalJson(payload)).digest('hex');}
function equal(a,b){return typeof a==='string'&&typeof b==='string'&&SHA.test(a)&&SHA.test(b)&&crypto.timingSafeEqual(Buffer.from(a,'hex'),Buffer.from(b,'hex'));}
function createFeatureContextHost({policyFile,key,allowedRoots}){
  if(!Buffer.isBuffer(key)||key.length<32||!Array.isArray(allowedRoots)||!allowedRoots.length)
    throw Error('FCI trusted host configuration required');
  const file=fs.realpathSync(policyFile),roots=allowedRoots.map(p=>fs.realpathSync(path.resolve(p)));
  const secret=Buffer.from(key);
  function entries(){
    const st=fs.lstatSync(file);
    if(!st.isFile()||st.isSymbolicLink()||st.size>8*1024*1024) throw Error('FCI invalid policy custody');
    const envelope=JSON.parse(fs.readFileSync(file,'utf8')),payload=envelope.payload;
    if(!payload||payload.version!==1||!equal(envelope.mac,mac(secret,payload))||
       !Number.isSafeInteger(payload.expires_at)||!Number.isSafeInteger(payload.issued_at)||
       payload.issued_at>Date.now()||payload.expires_at<=Date.now()||
       !Array.isArray(payload.entries)) throw Error('FCI invalid or stale policy');
    return payload.entries.filter(entry=>entry.revoked===false);
  }
  function valid(entry){
    const f=entry.manifest,ids=entry.required_claim_ids;
    return !validateFeature(f)&&SHA.test(entry.intent_sha256||'')&&
      entry.manifest_sha256===sha256(canonicalJson(f))&&
      Array.isArray(ids)&&ids.length>0&&new Set(ids).size===ids.length&&
      ids.every(id=>typeof id==='string'&&f.required_claim_ids?.includes(id))&&
      Array.isArray(entry.attestations)&&
      roots.includes(fs.realpathSync(path.resolve(f.repository.path)))&&
      (entry.predecessor===null||(entry.predecessor&&SHA.test(entry.predecessor.manifest_sha256||'')&&
        /^[a-f0-9]{40}$/.test(entry.predecessor.head||'')&&
        Number.isSafeInteger(entry.predecessor.contract_revision)&&entry.predecessor.contract_revision+1===f.contract.revision));
  }
  function single(rows){if(rows.length!==1||!valid(rows[0]))return null;return rows[0];}
  function policyForTask(task,target){
    if(target.status!=='RESOLVED'||target.clean!==true||!roots.includes(fs.realpathSync(target.top_level))) return null;
    const intent=intentDigest(task,target);
    const entry=single(entries().filter(e=>e.intent_sha256===intent&&e.manifest?.repository?.path===target.top_level&&
       e.manifest?.repository?.head===target.head&&e.manifest?.repository?.branch===target.branch));
    if(!entry) return null;
    return {intent_sha256:intent,feature_id:entry.manifest.feature_id,manifest_sha256:entry.manifest_sha256,
      required_claim_ids:[...entry.required_claim_ids].sort(),policy_sha256:sha256(canonicalJson(entry)),
      predecessor:entry.predecessor,contract_revision:entry.manifest.contract.revision};
  }
  function loadManifest(feature,pin){
    const entry=single(entries().filter(e=>e.manifest?.feature_id===feature&&e.manifest_sha256===pin));
    return entry?JSON.parse(JSON.stringify(entry.manifest)):null;
  }
  function attest(kind,details){
    const entry=single(entries().filter(e=>e.manifest?.feature_id===details.feature_id&&
      e.manifest?.repository?.head===details.repository_head&&
      e.manifest?.contract?.revision===details.contract_revision));
    if(!entry) return null;
    const proofs=entry.attestations.filter(p=>p.kind===kind&&p.proof?.claim_id===details.claim.id);
    return proofs.length===1?JSON.parse(JSON.stringify(proofs[0].proof)):null;
  }
  return Object.freeze({allowed_roots:Object.freeze(roots),policyForTask,loadManifest,
    verifiers:Object.freeze(Object.fromEntries(['authority','code','execution','runtime'].map(k=>[k,d=>attest(k,d)])))});
}
function hostFromEnvironment(env=process.env){
  const policyFile=env.PSB_FCI_POLICY_FILE,keyFile=env.PSB_FCI_POLICY_KEY_FILE;
  if(!policyFile&&!keyFile)return null;
  if(!policyFile||!keyFile)throw Error('FCI policy and issuer key files must both be configured');
  const allowedRoots=(env.PSB_HARNESS_ALLOWED_REPO_ROOTS||'').split(path.delimiter).map(x=>x.trim()).filter(Boolean);
  return createFeatureContextHost({policyFile,key:fs.readFileSync(keyFile),allowedRoots});
}
module.exports={createFeatureContextHost,hostFromEnvironment,intentDigest,mac};
