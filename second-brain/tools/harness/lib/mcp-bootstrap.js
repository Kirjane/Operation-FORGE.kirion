// Pure MCP bootstrap response builder: shared by the live server and fixture tests.
// Agent-facing text must not imply a complete context when optional sources
// were omitted, even if the existing risk gate permits the partial pack.
function buildBootstrapToolResponse(run,includeContext=true){
  const ctx=run.context||{};
  const omitted=Array.isArray(ctx.omitted_optional)?ctx.omitted_optional:[];
  const truncated=ctx.truncated===true||omitted.length>0;
  const data={
    run_id:run.run_id,manifest:run.manifest,task:run.task,
    classification:run.classification,signals:run.signals,risk:run.risk,
    route:run.route,gates:run.gates,context_manifest:run.context_manifest
  };
  if(includeContext&&ctx.status==='RESOLVED') data.context_documents=ctx.documents;
  const summary=[
    'Cognition run '+run.run_id+': classification='+
    (run.classification?.status==='RESOLVED'?run.classification.type:'BLOCKED')+
    ', rigor='+(run.risk?.mode||'UNRESOLVED')+
    ', context='+(ctx.status||'UNKNOWN')+
    ', gate='+(run.gates?.verdict||'UNKNOWN')+
    ', truncated='+(truncated?'YES':'NO')+
    ', omitted_optional='+omitted.length+'.'
  ];
  if(truncated){
    const examples=omitted.slice(0,8).map(x=>JSON.stringify(x.path)+' ('+x.reason+')');
    summary.push('WARNING: NOT LOADED optional context sources'+
      (examples.length?': '+examples.join(', '):' (paths unavailable)')+
      (omitted.length>8?'; +'+(omitted.length-8)+' more in context_manifest.omitted_optional':'')+
      '. Do not infer claims from omitted sources.');
  }
  if(ctx.status==='BLOCKED'){
    const missing=[...new Set([...(ctx.missing_required||[]),...(ctx.required_not_loaded||[])])];
    summary.push('BLOCKED: REQUIRED CONTEXT NOT LOADED'+
      (missing.length?': '+missing.slice(0,8).map(x=>JSON.stringify(x)).join(', '):'')+
      '. Do not proceed with context-dependent actions.');
  }
  return {content:[{type:'text',text:summary.join(' ')}],structuredContent:data};
}
module.exports={buildBootstrapToolResponse};
