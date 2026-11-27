const {sha256,validateSignals,validateRiskOverrides}=require('./io');

function intakeTask(input){
  if(typeof input==='string') input={intent:input};
  if(!input || typeof input.intent!=='string' || !input.intent.trim()) throw new Error('intake requires non-empty intent');
  const intent=input.intent.trim();
  const task={
    version:1,
    id:(input.id&&String(input.id).trim())||`task-${sha256(intent).slice(0,12)}`,
    intent,
    constraints:Array.isArray(input.constraints)?input.constraints.map(String):[],
    signals:validateSignals(input.signals),
    risk_overrides:validateRiskOverrides(input.risk_overrides),
    primary_journeys:Array.isArray(input.primary_journeys)?input.primary_journeys:[],
    ...(Object.hasOwn(input,'feature_context')?{feature_context:input.feature_context}:{}),
    repository:input.repository&&typeof input.repository==='object'?input.repository:{},
    acceptance:Array.isArray(input.acceptance)?input.acceptance.map(String):[]
  };
  if(input.type) task.type=String(input.type).trim();
  return task;
}
module.exports={intakeTask};
