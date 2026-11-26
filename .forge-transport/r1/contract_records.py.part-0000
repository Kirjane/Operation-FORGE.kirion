"""Detached synthetic records. No operational authority or effect interface."""
from __future__ import annotations
import json
import hashlib
import re

DOMAIN = 'FORGE_P1A_MODEL'
MAX_INT = 9007199254740991
MAX_RECORD = 262144
MAX_GRAPH = 4194304
EFFECT = ('READ','LOCAL_ARTIFACT','PROCESS_TEST','NETWORK_READ','COMMENT','SOURCE_WRITE','REF_WRITE','REMOTE_EFFECT')
STAGE = ('DISCOVERY','PLANNED','ASSIGNED','CANDIDATE','REVIEWED','ACCEPTED')
STATE = ('EMPTY','APPROVED','REJECTED','SUPERSEDED_PENDING','REVOKED','EXPIRED','UNKNOWN')
VALID = ('STRUCTURALLY_VALID','MODEL_CONSISTENT','MODEL_REJECTED','MODEL_UNKNOWN')
REDUCE = ('MODEL_COMMITTED','MODEL_ALREADY_COMMITTED','MODEL_CONFLICT','MODEL_REJECTED','MODEL_UNKNOWN')
KINDS = ('principal','oracle','intent','decision','context','capability','contract','grant','command','attempt','evidence','acceptance')
ID = ('id',)
FIX = ('fixture',)
STR = ('str',)
INT = ('int',0)
POS = ('int',1)
BOOL = ('bool',)
HEX = ('hex',)
SCOPE = {'repo_id':FIX,'lineage_id':FIX}

def enum(*values):
    return ('enum',values)

def ref(kind):
    return ('ref',kind)

def nullable(spec):
    return ('nullable',spec)

def arr(spec, ordered_set=False, minimum=0):
    return ('array',spec,ordered_set,minimum)

# Declarative closed shapes, also mirrored in the JSON schema.
REF = {'kind':enum(*KINDS),'record_id':ID,'scope':SCOPE,'revision':POS,'digest':HEX}
SOURCE = {'source_id':ID,'source_digest':HEX,'dependency_ids':arr(ID,True)}
OUTCOME = {'outcome_id':ID,'actor_id':FIX,'target_id':ID,'route':STR,'action':STR,'state':STR,'expected_result':STR,'expected_error':nullable(STR),'oracle_ref':ref('oracle')}
SOURCE_ROLE = {'source_id':ID,'role':enum('PRESENTATION','FUNCTIONAL','SECURITY'),'source_digest':HEX}
AVAIL = enum('AVAILABLE','UNAVAILABLE','UNKNOWN')
BODY = {
 'principal':{'subject_id':FIX,'issuer_id':FIX,'persona_id':ID,'role':enum('ENGINEER','MAINTAINER','WRITER','REVIEWER'),'specialization_ids':arr(ID,True),'host_id':ID,'session_id':ID,'exposure':enum('UNKNOWN','DECLARED_SHARED','DECLARED_SEPARATE'),'prior_author':BOOL},
 'oracle':{'custodian_ref':ref('principal'),'outcome_id':ID,'target_id':ID,'environment':enum('SYNTHETIC'),'positive_observation':STR,'negative_observation':STR,'expected_error':nullable(STR),'negative_expected_error':nullable(STR),'invariant_ids':arr(ID,True),'readback_required':BOOL},
 'intent':{'prior_intent_ref':nullable(ref('intent')),'outcomes':arr(OUTCOME,False,1),'source_roles':arr(SOURCE_ROLE,True),'constraints':arr(STR),'non_goals':arr(STR),'delivery_mode':enum('DEMO','REAL_MODEL'),'partial_policy':enum('NONE','EXPLICIT'),'partial_outcome_ids':arr(ID,True)},
 'decision':{'previous_ref':nullable(ref('decision')),'action':enum('APPROVE','REJECT','SUPERSEDE','REVOKE'),'intent_ref':ref('intent'),'target_approval_ref':nullable(ref('decision')),'approver_ref':ref('principal'),'reason':STR,'expiry_tick':nullable(INT),'creation_tick':INT},
 'context':{'intent_ref':ref('intent'),'required_sources':arr(SOURCE,True),'selected_sources':arr(SOURCE,True),'stale_ids':arr(ID,True),'omitted_optional_ids':arr(ID,True),'budget_bytes':INT,'consumed_bytes':INT,'evidence_level':enum('RETRIEVED','MODELED_READ','UNKNOWN')},
 'capability':{'principal_ref':ref('principal'),'resource_id':ID,'operation_family_id':ID,'availability':AVAIL,'permission':AVAIL,'quota':AVAIL,'quiescence':AVAIL,'observation_tick':INT,'expires_tick':INT},
 'contract':{'intent_ref':ref('intent'),'approved_decision_ref':ref('decision'),'principal_ref':ref('principal'),'context_ref':ref('context'),'resource_id':ID,'operation_family_id':ID,'allowed_effect_classes':arr(enum(*EFFECT),True),'constraints':arr(ID,True),'oracle_refs':arr(ref('oracle'),True),'protocol_floor_model':INT},
 'grant':{'contract_ref':ref('contract'),'decision_ref':ref('decision'),'principal_ref':ref('principal'),'capability_ref':ref('capability'),'issuer_ref':ref('principal'),'allowed_effect_classes':arr(enum(*EFFECT),True),'resource_id':ID,'operation_family_id':ID,'valid_from_tick':INT,'expires_tick':INT,'prior_grant_ref':nullable(ref('grant'))},
 'command':{'command_id':ID,'command_version':INT,'origin_ref':ref('principal'),'intent_ref':ref('intent'),'expected_decision_ref':ref('decision'),'expected_stage':enum(*STAGE),'effect_class':enum(*EFFECT),'arguments':arr({'name':STR,'value':STR}),'next_stage':enum(*STAGE)},
 'attempt':{'grant_ref':ref('grant'),'contract_ref':ref('contract'),'business_operation_id':ID,'resource_id':ID,'operation_family_id':ID,'attempt_id':ID,'predecessor_attempt_ref':nullable(ref('attempt')),'expected_target_digest':HEX,'requested_effect_class':enum(*EFFECT),'observation_state':enum('NO_EFFECT','UNKNOWN','EFFECT_OBSERVED','UNQUIESCED'),'quiesced':BOOL,'attempt_ordinal':POS},
 'evidence':{'attempt_ref':ref('attempt'),'oracle_ref':ref('oracle'),'issuer_ref':ref('principal'),'artifact_digest':HEX,'environment':enum('SYNTHETIC'),'observation':STR,'observed_error':nullable(STR),'evidence_type':enum('SOURCE','FIXTURE','MODELED_OBSERVATION'),'verdict':enum('MODELED_MATCH','MODELED_MISMATCH','UNKNOWN'),'readback_digest':nullable(HEX),'observed_target_id':ID,'control_case':enum('POSITIVE','DISCONFIRMING')},
 'acceptance':{'contract_ref':ref('contract'),'decision_ref':ref('decision'),'reviewer_ref':ref('principal'),'evidence_refs':arr(ref('evidence'),True,1),'artifact_digest':HEX,'verdict':enum('MODEL_CONSISTENT','MODEL_REJECTED','MODEL_UNKNOWN')},
}
ENVELOPE = {'domain':enum(DOMAIN),'version':('int',1,1),'kind':enum(*KINDS),'record_id':ID,'scope':SCOPE,'revision':POS,'body':('object',)}
FLOOR = {'intent_ref':ref('intent'),'required_sources':arr(SOURCE,True)}
NAMESPACE = ('COMMAND','RESOURCE','OPERATION_FAMILY')
REGISTRY = {n:arr(ID,True) for n in NAMESPACE}
ALIAS = {'alias_id':ID,'canonical_id':ID,'namespace':enum(*NAMESPACE)}
MAPPING = {'command_id':ID,'command_version':INT,'expected_stage':enum(*STAGE),'next_stage':enum(*STAGE),'effect_class':enum(*EFFECT)}
INDEX = {'resource_id':ID,'operation_family_id':ID,'business_operation_id':ID,'tip_attempt_ref':nullable(ref('attempt'))}
CASE = {'contract_ref':ref('contract'),'attempt_ref':ref('attempt'),'oracle_ref':ref('oracle'),'outcome_id':ID,'target_id':ID,'artifact_digest':HEX,'control_case':enum('POSITIVE','DISCONFIRMING'),'expected_issuer_ref':ref('principal'),'expected_readback_digest':nullable(HEX)}
SNAPSHOT = {'events':arr(('object',)),'head_ref':nullable(ref('decision'))}

class Invalid(ValueError):
    pass

class Unknown(ValueError):
    pass


def require(condition, reason='INVALID_MODEL'):
    if not condition:
        raise Invalid(reason)


def known(condition, reason='MISSING_OR_INAPPLICABLE'):
    if not condition:
        raise Unknown(reason)


def primitive(value, depth=1, ancestors=None, count=None, seen=None):
    """Check exact types before using their methods; reject cycles and aliases."""
    if ancestors is None:
        ancestors = []
    if count is None:
        count = [0]
    if seen is None:
        seen = []
    count[0] += 1
    require(depth <= 32 and count[0] <= 10000,'PRIMITIVE_LIMIT')
    t = type(value)
    if t is str:
        require(len(value)<=8192 and not re.search('[\ud800-\udfff]',value),'STRING_LIMIT')
    elif t is int:
        require(0<=value<=MAX_INT,'INTEGER_RANGE')
    elif t is bool or value is None:
        return
    elif t is list or t is dict:
        require(not any(value is a for a in seen),'CYCLE_OR_MUTABLE_ALIAS')
        seen.append(value)
        ancestors.append(value)
        if t is list:
            require(len(value)<=256,'ARRAY_LIMIT')
            for item in value:
                primitive(item,depth+1,ancestors,count,seen)
        else:
            for key,item in value.items():
                require(type(key) is str,'KEY_TYPE')
                primitive(key,depth+1,ancestors,count,seen)
                primitive(item,depth+1,ancestors,count,seen)
        ancestors.pop()
    else:
        raise Invalid('PRIMITIVE_TYPE')


def _string(s):
    return '"'+''.join('\\'+c if c in ('"','\\') else '\\u%04x'%ord(c) if ord(c)<32 else c for c in s)+'"'


def _encode(v):
    if type(v) is str:
        return _string(v)
    if type(v) is dict:
        return '{'+','.join(_string(k)+':'+_encode(v[k]) for k in sorted(v))+'}'
    if type(v) is list:
        return '['+','.join(_encode(x) for x in v)+']'
    if v is None:
        return 'null'
    if type(v) is bool:
        return 'true' if v else 'false'
    return str(v)


def canonical_bytes(value):
    primitive(value)
    return _encode(value).encode('utf-8')


def sha256(raw):
    require(type(raw) is bytes,'RAW_TYPE')
    return hashlib.sha256(raw).hexdigest()


def _integer(s):
    require(re.fullmatch(r'0|[1-9][0-9]{0,15}',s) is not None,'INTEGER_LEXICAL')
    value = int(s)
    require(value<=MAX_INT,'INTEGER_RANGE')
    return value


def _decode_json(text):
    # Explicit bounded grammar, no parser callbacks. JSON string tokens are
    # decoded by the standard library only after lexical delimiting.
    pos = 0
    nodes = 0
    def ws():
        nonlocal pos
        while pos<len(text) and text[pos] in ' \t\r\n':
            pos += 1
    def string():
        nonlocal pos
        require(pos<len(text) and text[pos]=='"','JSON_STRING')
        start=pos; pos+=1
        while pos<len(text):
            ch=text[pos]; pos+=1
            if ch=='"':
                try: result=json.loads(text[start:pos])
                except ValueError as exc: raise Invalid('JSON_STRING') from exc
                require(len(result)<=8192 and not re.search('[\ud800-\udfff]',result),'STRING_LIMIT')
                return result
            if ch=='\\':
                require(pos<len(text),'JSON_ESCAPE'); pos+=1
        raise Invalid('JSON_STRING')
    def value(depth):
        nonlocal pos,nodes
        nodes+=1; require(depth<=32 and nodes<=10000,'PRIMITIVE_LIMIT'); ws(); require(pos<len(text),'JSON_VALUE')
        ch=text[pos]
        if ch=='"': return string()
        if ch in '{[':
            obj=ch=='{'; close='}' if obj else ']'; pos+=1; ws(); result={} if obj else []
            if pos<len(text) and text[pos]==close: pos+=1; return result
            while True:
                ws()
                if obj:
                    key=string(); nodes+=1; require(nodes<=10000 and key not in result,'DUPLICATE_KEY_OR_LIMIT'); ws()
                    require(pos<len(text) and text[pos]==':','JSON_COLON'); pos+=1; result[key]=value(depth+1)
                else:
                    require(len(result)<256,'ARRAY_LIMIT'); result.append(value(depth+1))
                ws(); require(pos<len(text),'JSON_END')
                ch=text[pos]; pos+=1
                if ch==close: return result
                require(ch==',','JSON_SEPARATOR')
        for token,decoded in (('true',True),('false',False),('null',None)):
            if text.startswith(token,pos): pos+=len(token); return decoded
        start=pos
        while pos<len(text) and text[pos] not in ' \t\r\n,]}': pos+=1
        return _integer(text[start:pos])
    result=value(1); ws(); require(pos==len(text),'JSON_TRAILING'); return result


def parse_record(raw):
    require(type(raw) is bytes and len(raw)<=MAX_RECORD,'RAW_LIMIT')
    require(not raw.startswith(b'\xef\xbb\xbf'),'BOM')
    try:
        value=_decode_json(raw.decode('utf-8','strict'))
    except (ValueError,RecursionError) as exc:
        raise Invalid('RAW_INGRESS') from exc
    structural(value)
    return value


def shape(v,s):
    if type(s) is dict:
        require(type(v) is dict and set(v)==set(s),'CLOSED_KEYS')
        for k in s:
            shape(v[k],s[k])
        return
    tag=s[0]
    if tag in ('id','fixture','hex'):
        pattern = '[0-9a-f]{64}' if tag=='hex' else '[A-Za-z0-9][A-Za-z0-9._:-]{0,127}'
        require(type(v) is str and re.fullmatch(pattern,v) is not None,'IDENTIFIER')
        if tag=='fixture':
            require(v.startswith('fixture:') and len(v)>8,'FIXTURE_ID')
    elif tag=='str':
        require(type(v) is str,'STRING_TYPE')
    elif tag=='int':
        require(type(v) is int and s[1]<=v<=(s[2] if len(s)>2 else MAX_INT),'INTEGER_TYPE')
    elif tag=='bool':
        require(type(v) is bool,'BOOLEAN_TYPE')
    elif tag=='enum':
        require(type(v) is str and v in s[1],'ENUM')
    elif tag=='nullable':
        if v is not None:
            shape(v,s[1])
    elif tag=='object':
        require(type(v) is dict,'OBJECT_TYPE')
    elif tag=='ref':
        shape(v,REF)
        require(v['kind']==s[1],'REF_KIND')
    elif tag=='array':
        require(type(v) is list and s[3]<=len(v)<=256,'ARRAY_TYPE')
        for item in v:
            shape(item,s[1])
        if s[2]:
            enc=[canonical_bytes(x) for x in v]
            require(all(a<b for a,b in zip(enc,enc[1:])),'SET_ORDER')
    else:
        raise Invalid('SHAPE')


def structural(record):
    primitive(record)
    shape(record,ENVELOPE)
    shape(record['body'],BODY[record['kind']])
    require(len(canonical_bytes(record))<=MAX_RECORD,'RECORD_LIMIT')
    return record


def digest(record):
    structural(record)
    return sha256(('FORGE_P1A_MODEL/v1/'+record['kind']+'\n').encode('ascii')+canonical_bytes(record))


def record_ref(record):
    structural(record)
    return {'kind':record['kind'],'record_id':record['record_id'],'scope':dict(record['scope']),'revision':record['revision'],'digest':digest(record)}


def _key(ref_value):
    return (ref_value['scope']['repo_id'],ref_value['scope']['lineage_id'],ref_value['kind'],ref_value['record_id'],ref_value['revision'])


def _resolve(index,r):
    found=index.get(_key(r))
    require(found is not None and record_ref(found)==r,'UNRESOLVED_REF')
    return found


def _refs(v,s,path=()):
    if type(s) is dict:
        for k in s:
            yield from _refs(v[k],s[k],path+(k,))
    elif s[0]=='ref':
        yield path,v
    elif s[0]=='nullable' and v is not None:
        yield from _refs(v,s[1],path)
    elif s[0]=='array':
        for i,item in enumerate(v):
            yield from _refs(item,s[1],path+(i,))


def _unique(values):
    return len(values)==len(set(values))


def _record_links(r,index):
    b=r['body']; k=r['kind']
    for path,rr in _refs(b,BODY[k]):
        other=_resolve(index,rr)
        if k=='attempt' and path==('predecessor_attempt_ref',):
            require(other['scope']['repo_id']==r['scope']['repo_id'],'REPO_SCOPE')
        else:
            require(rr['scope']==r['scope'],'REF_SCOPE')
    if k=='intent':
        p=b['prior_intent_ref']
        require((r['revision']==1 and p is None) or (p is not None and p['revision']==r['revision']-1 and p['record_id']==r['record_id']),'INTENT_PREDECESSOR')
        ids=[o['outcome_id'] for o in b['outcomes']]; refs=[canonical_bytes(o['oracle_ref']) for o in b['outcomes']]
        require(_unique(ids) and _unique(refs),'DUPLICATE_OUTCOME')
        require((b['partial_policy']=='NONE' and not b['partial_outcome_ids']) or (b['partial_policy']=='EXPLICIT' and bool(b['partial_outcome_ids']) and set(b['partial_outcome_ids'])<=set(ids)),'PARTIAL_POLICY')
        require(_unique([s['source_id'] for s in b['source_roles']]),'SOURCE_DUPLICATE')
        for o in b['outcomes']:
            oracle=_resolve(index,o['oracle_ref'])['body']
            require(oracle['outcome_id']==o['outcome_id'] and oracle['target_id']==o['target_id'] and oracle['positive_observation'] and oracle['negative_observation'] and oracle['invariant_ids'],'ORACLE_BINDING')
            require(o['expected_result']==oracle['positive_observation'] and o['expected_error']==oracle['expected_error'],'ORACLE_EXPECTATION')
    elif k=='grant' and b['prior_grant_ref'] is not None:
        p=b['prior_grant_ref']; require(p['record_id']==r['record_id'] and p['revision']<r['revision'],'GRANT_PREDECESSOR')
    elif k=='decision':
        p=b['previous_ref']; require((p is None and r['revision']==1) or (p is not None and p['revision']+1==r['revision']),'DECISION_REVISION')


def graph_index(graph):
    require(type(graph) is list and len(graph)<=256,'GRAPH_COUNT')
    index={}; total=0; decision_ids=set()
    # Share identity tracking across records, but reset each record's depth and
    # node budget. Identity comparisons, not value equality: independently
    # decoded equal containers are valid. The root list is also tracked.
    seen=[graph]
    for r in graph:
        primitive(r,seen=seen)
        structural(r); total+=len(canonical_bytes(r)); require(total<=MAX_GRAPH,'GRAPH_BYTES')
        key=_key(r); require(key not in index,'DUPLICATE_RECORD')
        if r['kind']=='decision':
            dkey=key[:4]; require(dkey not in decision_ids,'DUPLICATE_DECISION_ID'); decision_ids.add(dkey)
        _record_links(r,index); index[key]=r
    return index


def _result(code,record_digest=None,reason=None):
    return {'domain':DOMAIN,'fixture_only':True,'authority_granted':False,'promotion_authorized':False,'result_kind':'VALIDATION','result_code':code,'reason_codes':[] if reason is None else [reason],'record_digest':record_digest}


def validate_raw(raw):
    try:
        return _result('STRUCTURALLY_VALID',digest(parse_record(raw)))
    except Invalid as exc:
        return _result('MODEL_REJECTED',reason=str(exc))


def validate_record(record):
    try:
        return _result('STRUCTURALLY_VALID',digest(record))
    except Invalid as exc:
        return _result('MODEL_REJECTED',reason=str(exc))


def validate_graph(graph):
    try:
        graph_index(graph); return _result('MODEL_CONSISTENT')
    except Invalid as exc:
        return _result('MODEL_REJECTED',reason=str(exc))


def _state(event,tick):
    if event is None:
        return 'EMPTY'
    b=event['body']; state={'APPROVE':'APPROVED','REJECT':'REJECTED','SUPERSEDE':'SUPERSEDED_PENDING','REVOKE':'REVOKED'}[b['action']]
    return 'EXPIRED' if state=='APPROVED' and b['expiry_tick'] is not None and tick>=b['expiry_tick'] else state


def _transition(event,prior,index):
    b=event['body']; tick=b['creation_tick']; action=b['action']; prior_ref=None if prior is None else record_ref(prior)
    require(b['previous_ref']==prior_ref and event['revision']==(1 if prior is None else prior['revision']+1),'DECISION_PREDECESSOR')
    require(prior is None or (prior['scope']==event['scope'] and tick>=prior['body']['creation_tick']),'DECISION_CHRONOLOGY')
    require(_resolve(index,b['approver_ref'])['body']['role']=='ENGINEER','ENGINEER_REQUIRED')
    intent=_resolve(index,b['intent_ref']); old=None if prior is None else prior['body']['intent_ref']; state=_state(prior,tick)
    same=b['intent_ref']==old; next_intent=old is not None and intent['body']['prior_intent_ref']==old and intent['revision']==old['revision']+1
    expiry=b['expiry_tick']; target=b['target_approval_ref']
    require((action=='APPROVE' and (expiry is None or expiry>tick)) or (action!='APPROVE' and expiry is None),'EXPIRY')
    if action in ('APPROVE','REJECT'):
        require(state!='APPROVED' and target is None and ((prior is None and intent['revision']==1) or same or next_intent),'DECISION_TRANSITION')
    elif action=='SUPERSEDE':
        require(prior is not None and next_intent and target==(prior_ref if state in ('APPROVED','EXPIRED') else None),'SUPERSEDE_TRANSITION')
    else:
        require(state in ('APPROVED','EXPIRED') and same and target==prior_ref,'REVOKE_TRANSITION')


def _snapshot(snapshot,tick,index):
    primitive(snapshot); shape(snapshot,SNAPSHOT); shape(tick,INT)
    events={}; ids=set(); scope=None
    for e in snapshot['events']:
        structural(e); require(e['kind']=='decision','SNAPSHOT_KIND')
        require(e['body']['creation_tick']<=tick,'FUTURE_HISTORY')
        if scope is None: scope=e['scope']
        require(e['scope']==scope and e['record_id'] not in ids,'SNAPSHOT_ID_SCOPE')
        ids.add(e['record_id']); combined=dict(index); combined.update(events)
        for field in ('previous_ref','target_approval_ref'):
            if e['body'][field] is not None: _resolve(events,e['body'][field])
        _record_links(e,combined)
        predecessor=e['body']['previous_ref']
        prior=None if predecessor is None else _resolve(events,predecessor)
        _transition(e,prior,combined)
        existing=index.get(_key(e)); require(existing is None or existing==e,'SNAPSHOT_CONFLICT')
        events[_key(e)]=e
    head=snapshot['head_ref']; current=None if head is None else _resolve(events,head)
    chain=[]; cursor=current
    while cursor is not None:
        require(len(chain)<len(events),'HISTORY_CYCLE'); chain.append(cursor)
        p=cursor['body']['previous_ref']; cursor=None if p is None else _resolve(events,p)
    combined=dict(index); combined.update(events); prior=None
    for e in reversed(chain):
        _transition(e,prior,combined); prior=e
    return current,chain,combined


def _reducer(code,submitted,committed,previous,current,state,tick,reason=None):
    # Each returned reference is a fresh primitive value, including exact retries.
    active=committed is not None and committed==current and state=='APPROVED' and code in ('MODEL_COMMITTED','MODEL_ALREADY_COMMITTED')
    submitted,committed,previous,current=(json.loads(canonical_bytes(r)) if r is not None else None for r in (submitted,committed,previous,current))
    return {'domain':DOMAIN,'fixture_only':True,'authority_granted':False,'promotion_authorized':False,'result_kind':'DECISION_REDUCER','result_code':code,'reason_codes':[] if reason is None else [reason],'submitted_event_ref':submitted,'committed_event_ref':committed,'previous_head_ref':previous,'current_head_ref':current,'current_state':state,'evaluation_tick':tick,'submitted_event_is_current_approval':active}


def reduce_decision(graph,snapshot,submitted_event,evaluation_tick,stage_only=False):
    sr=None; tick=None
    try:
        shape(evaluation_tick,INT); tick=evaluation_tick
        structural(submitted_event); require(submitted_event['kind']=='decision','SUBMISSION_KIND'); sr=record_ref(submitted_event)
    except Invalid:
        pass
    try:
        index=graph_index(graph); head,chain,combined=_snapshot(snapshot,tick,index)
    except Invalid as exc:
        return _reducer('MODEL_UNKNOWN',sr,None,None,None,'UNKNOWN',tick,str(exc)),None
    previous=snapshot['head_ref']; state=_state(head,tick); unchanged=json.loads(canonical_bytes(snapshot))
    try:
        require(sr is not None and type(stage_only) is bool,'SUBMISSION')
        require(not snapshot['events'] or submitted_event['scope']==snapshot['events'][0]['scope'],'SUBMISSION_SCOPE')
        matching=[e for e in snapshot['events'] if e['record_id']==submitted_event['record_id']]
        require(not matching or matching[0]==submitted_event,'EVENT_ID_COLLISION')
        if submitted_event in chain:
            return _reducer('MODEL_ALREADY_COMMITTED',sr,sr,previous,previous,state,tick),unchanged
        b=submitted_event['body']; creation=b['creation_tick']
        require(creation<=tick and (head is None or creation>=head['body']['creation_tick'] or bool(matching)),'DECISION_CHRONOLOGY')
        if b['previous_ref']!=previous or (matching and creation!=tick):
            return _reducer('MODEL_CONFLICT',sr,None,previous,previous,state,tick,'STALE_HEAD_OR_TICK'),unchanged
        require(creation==tick,'PUBLICATION_TICK'); _record_links(submitted_event,combined); _transition(submitted_event,head,combined)
        if not matching: unchanged['events'].append(json.loads(canonical_bytes(submitted_event)))
        if stage_only:
            return _reducer('MODEL_UNKNOWN',sr,None,previous,previous,state,tick,'STAGED_NOT_COMMITTED'),unchanged
        unchanged['head_ref']=json.loads(canonical_bytes(sr))
        return _reducer('MODEL_COMMITTED',sr,sr,previous,sr,_state(submitted_event,tick),tick),unchanged
    except Invalid as exc:
        return _reducer('MODEL_REJECTED',sr,None,previous,previous,state,tick,str(exc)),unchanged


def _context(record,index,floor):
    primitive(floor); shape(floor,FLOOR); b=record['body']
    require(floor['intent_ref']==b['intent_ref'],'CONTEXT_INTENT'); _resolve(index,b['intent_ref'])
    require(b['required_sources']==floor['required_sources'],'CONTEXT_FLOOR')
    required={s['source_id']:s for s in floor['required_sources']}; selected={s['source_id']:s for s in b['selected_sources']}
    require(len(required)==len(floor['required_sources']) and len(selected)==len(b['selected_sources']),'SOURCE_DUPLICATE')
    require(all(selected.get(k)==v for k,v in required.items()),'CONTEXT_PIN')
    require(not set(required)&set(b['stale_ids']) and not set(required)&set(b['omitted_optional_ids']),'CONTEXT_STALE_OMITTED')
    require(not set(selected)&set(b['omitted_optional_ids']),'CONTEXT_CONTRADICTION')
    require(b['consumed_bytes']<=b['budget_bytes'],'CONTEXT_BUDGET')
    def visit(key,trail,done):
        require(key in selected and key not in trail,'DEPENDENCY_MISSING_OR_CYCLE')
        if key in done: return
        for dep in selected[key]['dependency_ids']:
            visit(dep,trail+(key,),done)
        done.add(key)
    done=set()
    for key in selected:
        visit(key,(),done)
    # Independent required closure cannot be reduced to caller-selected rows.
    require(all(dep in required for row in required.values() for dep in row['dependency_ids']),'FLOOR_CLOSURE')
    known(b['evidence_level']!='UNKNOWN','CONTEXT_UNKNOWN')


def _subject(p):
    return (p['subject_id'],p['issuer_id'])


def _eligible(person,writer):
    return person['role']=='REVIEWER' and not person['prior_author'] and person['exposure']=='DECLARED_SEPARATE' and _subject(person)!=_subject(writer) and person['session_id']!=writer['session_id']


def _current(index,snapshot,tick,decision_ref,intent_ref):
    try:
        head,_,combined=_snapshot(snapshot,tick,index)
    except Invalid as exc:
        raise Unknown('DECISION_SNAPSHOT_UNKNOWN') from exc
    require(head is not None and record_ref(head)==decision_ref and _state(head,tick)=='APPROVED' and head['body']['intent_ref']==intent_ref,'CURRENT_APPROVAL_REQUIRED')
    return combined


def _registry(canonical,aliases):
    primitive(canonical); shape(canonical,REGISTRY); primitive(aliases); shape(aliases,arr(ALIAS,True))
    result={}
    for row in aliases:
        n=row['namespace']; a=row['alias_id']; c=row['canonical_id']; key=(n,a)
        require(key not in result and a not in canonical[n] and c in canonical[n],'ALIAS_COLLISION_OR_CHAIN'); result[key]=c
    return result


def _canonical_resource(body,canonical):
    require(body['resource_id'] in canonical['RESOURCE'] and body['operation_family_id'] in canonical['OPERATION_FAMILY'],'NONCANONICAL_RESOURCE')


def _contract(record,index,snapshot,tick,floor,canonical):
    b=record['body']; _canonical_resource(b,canonical)
    index=_current(index,snapshot,tick,b['approved_decision_ref'],b['intent_ref'])
    intent=_resolve(index,b['intent_ref'])['body']; context=_resolve(index,b['context_ref']); require(context['body']['intent_ref']==b['intent_ref'],'CONTRACT_CONTEXT')
    _context(context,index,floor)
    outcomes=intent['outcomes']; require(all(o['target_id']==b['resource_id'] for o in outcomes),'SINGLE_RESOURCE')
    require({canonical_bytes(o['oracle_ref']) for o in outcomes}=={canonical_bytes(r) for r in b['oracle_refs']},'CONTRACT_ORACLE_COVERAGE')
    return index,intent


def _grant(grant,contract,index,snapshot,tick,floor,canonical):
    b=grant['body']; c=contract['body']; index,_=_contract(contract,index,snapshot,tick,floor,canonical)
    require(b['contract_ref']==record_ref(contract) and b['decision_ref']==c['approved_decision_ref'] and b['principal_ref']==c['principal_ref'],'GRANT_BINDING')
    require(b['resource_id']==c['resource_id'] and b['operation_family_id']==c['operation_family_id'],'GRANT_RESOURCE')
    require(set(b['allowed_effect_classes'])<=set(c['allowed_effect_classes']),'GRANT_EFFECT_INTERSECTION')
    issuer=_resolve(index,b['issuer_ref'])['body']; require(issuer['role']=='ENGINEER','GRANT_ISSUER')
    capability=_resolve(index,b['capability_ref'])['body']
    require(all(capability[k]==b[k] for k in ('principal_ref','resource_id','operation_family_id')),'CAPABILITY_BINDING')
    require(b['valid_from_tick']<b['expires_tick']<=capability['expires_tick'] and capability['observation_tick']<=b['valid_from_tick'] and b['valid_from_tick']<=tick<b['expires_tick'],'GRANT_TIME')
    known(all(capability[k]=='AVAILABLE' for k in ('availability','permission','quota','quiescence')),'CAPABILITY_UNAVAILABLE')
    return index


def _attempt_grant(record,index,snapshot,tick,floor,canonical):
    b=record['body']; _canonical_resource(b,canonical)
    contract=_resolve(index,b['contract_ref']); grant=_resolve(index,b['grant_ref'])
    require(grant['scope']==record['scope']==contract['scope'],'ATTEMPT_SCOPE')
    index=_grant(grant,contract,index,snapshot,tick,floor,canonical)
    g=grant['body']; c=contract['body']
    require(all(b[k]==g[k]==c[k] for k in ('resource_id','operation_family_id')),'ATTEMPT_RESOURCE')
    require(b['requested_effect_class'] in g['allowed_effect_classes'] and b['requested_effect_class'] in c['allowed_effect_classes'],'ATTEMPT_EFFECT')
    return index


def _submission_index(graph,record,kind):
    structural(record); require(record['kind']==kind,'SUBMISSION_KIND'); index=graph_index(graph)
    # Graph validation remains strict, even if an invalid evidence record was
    # supplied as a graph member. A proposal is not an admitted graph record.
    existing=index.get(_key(record)); require(existing is None or existing==record,'GRAPH_SUBMISSION_CONFLICT')
    return index


def _semantic_record(graph,record,kind):
    index=_submission_index(graph,record,kind)
    _record_links(record,index)
    return index


def _applicability_links(record,index):
    # Only the submitted receipt's applicability is evaluated here. Exact
    # shape, typed references and the existing graph were already checked.
    # A cross-scope or unresolved evidence relation is unknown, not an
    # applicable negative control. It is never admitted to graph_index.
    kind=record['kind']
    for path,r in _refs(record['body'],BODY[kind]):
        receipt_link=kind=='evidence' or (kind=='acceptance' and path[0]=='evidence_refs')
        if receipt_link:
            known(r['scope']==record['scope'],'INAPPLICABLE_REF_SCOPE')
            try:
                _resolve(index,r)
            except Invalid as exc:
                raise Unknown('INAPPLICABLE_REF') from exc
        else:
            _resolve(index,r)
            require(r['scope']==record['scope'],'REF_SCOPE')


def evaluate_context(graph,context,expected_context_floor):
    d=None
    try:
        d=digest(context); index=_semantic_record(graph,context,'context'); _context(context,index,expected_context_floor); return _result('MODEL_CONSISTENT',d)
    except Unknown as exc: return _result('MODEL_UNKNOWN',d,str(exc))
    except Invalid as exc: return _result('MODEL_REJECTED',d,str(exc))


COMMAND_AUX = {'evaluation_tick':INT,'decision_snapshot':SNAPSHOT,'expected_context_floor':FLOOR,'canonical_ids':REGISTRY,'alias_registry':arr(ALIAS,True),'command_mapping':arr(MAPPING,True)}
ASSURANCE_AUX = dict(COMMAND_AUX,expected_cases=arr(CASE,True),logical_index=arr(INDEX,True))


def _aux(aux,spec):
    # Large snapshots are bounded record-by-record, not a single record budget.
    require(type(aux) is dict and all(type(k) is str for k in aux) and set(aux)==set(spec),'AUX_KEYS')
    seen=[aux]
    for k in spec:
        primitive(aux[k],seen=seen); shape(aux[k],spec[k])


def evaluate_command(graph,command,auxiliary):
    d=None
    try:
        d=digest(command); index=_semantic_record(graph,command,'command'); _aux(auxiliary,COMMAND_AUX); a=auxiliary; b=command['body']
        aliases=_registry(a['canonical_ids'],a['alias_registry']); canonical=a['canonical_ids']['COMMAND']
        name=aliases.get(('COMMAND',b['command_id']),b['command_id']); require(name in canonical,'COMMAND_UNKNOWN')
        _current(index,a['decision_snapshot'],a['evaluation_tick'],b['expected_decision_ref'],b['intent_ref'])
        origin=_resolve(index,b['origin_ref'])['body']
        require(origin['role']!='REVIEWER' or b['effect_class']=='READ','REVIEWER_EFFECT')
        rows=a['command_mapping']; keys=[(r['command_id'],r['command_version'],r['expected_stage']) for r in rows]
        require(_unique(keys) and all(r['command_id'] in canonical for r in rows),'COMMAND_MAPPING')
        exact=[r for r in rows if (r['command_id'],r['command_version'],r['expected_stage'])==(name,b['command_version'],b['expected_stage'])]
        require(len(exact)==1 and exact[0]['next_stage']==b['next_stage'] and exact[0]['effect_class']==b['effect_class'],'COMMAND_TRANSITION')
        require(a['expected_context_floor']['intent_ref']==b['intent_ref'],'COMMAND_CONTEXT_INTENT')
        return _result('MODEL_CONSISTENT',d)
    except Unknown as exc: return _result('MODEL_UNKNOWN',d,str(exc))
    except Invalid as exc: return _result('MODEL_REJECTED',d,str(exc))


def _logical(body):
    return tuple(body[k] for k in ('resource_id','operation_family_id','business_operation_id'))


def _history_inputs(index,floors,snapshots):
    require(type(floors) is list and len(floors)<=256 and type(snapshots) is list and len(snapshots)<=256,'HISTORY_INPUTS')
    require(floors is not snapshots,'HISTORY_MUTABLE_ALIAS')
    fm={}; sm={}; seen=[floors,snapshots]
    for f in floors:
        primitive(f,seen=seen); shape(f,FLOOR); k=canonical_bytes(f['intent_ref']); require(k not in fm,'DUPLICATE_HISTORY_FLOOR'); fm[k]=f
        _resolve(index,f['intent_ref'])
    for s in snapshots:
        primitive(s,seen=seen); shape(s,SNAPSHOT); require(s['head_ref'] is not None,'HISTORY_HEAD'); k=canonical_bytes(s['head_ref']); require(k not in sm,'DUPLICATE_HISTORY_HEAD'); sm[k]=s
    return fm,sm


def evaluate_attempt(graph,proposed_attempt,logical_index,evaluation_tick,current_decision_snapshot,canonical_ids,alias_registry,expected_context_floor,historical_context_floors,historical_decision_snapshots):
    d=None
    try:
        d=digest(proposed_attempt); index=_semantic_record(graph,proposed_attempt,'attempt'); b=proposed_attempt['body']; shape(evaluation_tick,INT)
        _registry(canonical_ids,alias_registry); _canonical_resource(b,canonical_ids); primitive(expected_context_floor); shape(expected_context_floor,FLOOR); primitive(current_decision_snapshot); shape(current_decision_snapshot,SNAPSHOT); primitive(logical_index); shape(logical_index,arr(INDEX,True))
        require(proposed_attempt['revision']==1,'NEW_ATTEMPT_REVISION')
        require(_key(proposed_attempt) not in index,'ATTEMPT_ALREADY_PRESENT')
        rows={_logical(r):r for r in logical_index}; require(len(rows)==len(logical_index),'INDEX_DUPLICATE')
        known(_logical(b) in rows,'UNREGISTERED_OPERATION')
        fm,sm=_history_inputs(index,historical_context_floors,historical_decision_snapshots)
        chains={}
        for r in graph:
            if r['kind']!='attempt': continue
            rb=r['body']; k=_logical(rb); _canonical_resource(rb,canonical_ids); chain=chains.setdefault(k,[])
            require(rb['attempt_ordinal']==len(chain)+1 and rb['predecessor_attempt_ref']==(record_ref(chain[-1]) if chain else None),'PRIOR_CHAIN_FORK_OR_GAP')
            require(all(x['body']['attempt_id']!=rb['attempt_id'] for x in chain),'ATTEMPT_ID_DUPLICATE')
            if chain:
                require(chain[-1]['body']['observation_state']=='NO_EFFECT' and chain[-1]['body']['quiesced'],'INVALID_HISTORICAL_SUCCESSOR')
            c=_resolve(index,rb['contract_ref'])['body']; g=_resolve(index,rb['grant_ref'])['body']; f=fm.get(canonical_bytes(c['intent_ref'])); s=sm.get(canonical_bytes(c['approved_decision_ref']))
            # Current lineage can also appear in the prior chain. Historical use
            # is checked at the grant's modeled start tick, not today's expiry.
            if f is None and expected_context_floor['intent_ref']==c['intent_ref']: f=expected_context_floor
            if s is None and current_decision_snapshot['head_ref']==c['approved_decision_ref']: s=current_decision_snapshot
            known(f is not None and s is not None,'HISTORICAL_AUTHORITY_MISSING')
            _attempt_grant(r,index,s,g['valid_from_tick'],f,canonical_ids); chain.append(r)
        for k,chain in chains.items():
            require(k in rows and rows[k]['tip_attempt_ref']==record_ref(chain[-1]),'INDEX_TRUNCATION')
        for k,row in rows.items():
            _canonical_resource(row,canonical_ids)
            require(row['tip_attempt_ref']==(record_ref(chains[k][-1]) if k in chains else None),'INDEX_TIP')
        k=_logical(b); known(k in rows,'UNREGISTERED_OPERATION'); chain=chains.get(k,[]); tip=rows[k]['tip_attempt_ref']
        require(b['predecessor_attempt_ref']==tip and b['attempt_ordinal']==len(chain)+1,'ATTEMPT_PREDECESSOR_OR_ORDINAL')
        require(all(x['body']['attempt_id']!=b['attempt_id'] for x in chain),'ATTEMPT_ID_DUPLICATE')
        if chain:
            prior=chain[-1]['body']; require(prior['observation_state']!='EFFECT_OBSERVED','DUPLICATE_EFFECT'); known(prior['observation_state']=='NO_EFFECT' and prior['quiesced'],'PRIOR_EFFECT_UNKNOWN')
        _attempt_grant(proposed_attempt,index,current_decision_snapshot,evaluation_tick,expected_context_floor,canonical_ids)
        return _result('MODEL_CONSISTENT',d)
    except Unknown as exc: return _result('MODEL_UNKNOWN',d,str(exc))
    except Invalid as exc: return _result('MODEL_REJECTED',d,str(exc))


def _covered(intent):
    return [o for o in intent['outcomes'] if intent['partial_policy']=='NONE' or o['outcome_id'] in intent['partial_outcome_ids']]


def _assurance_index(index,rows,canonical):
    by_key={_logical(row):row for row in rows}
    require(len(by_key)==len(rows),'INDEX_DUPLICATE')
    chains={}
    for r in index.values():
        if r['kind']!='attempt': continue
        b=r['body']; key=_logical(b); _canonical_resource(b,canonical); chain=chains.setdefault(key,[])
        require(b['attempt_ordinal']==len(chain)+1 and b['predecessor_attempt_ref']==(record_ref(chain[-1]) if chain else None),'PRIOR_CHAIN_FORK_OR_GAP')
        require(all(x['body']['attempt_id']!=b['attempt_id'] for x in chain),'ATTEMPT_ID_DUPLICATE')
        if chain:
            require(chain[-1]['body']['observation_state']=='NO_EFFECT' and chain[-1]['body']['quiesced'],'INVALID_HISTORICAL_SUCCESSOR')
        chain.append(r)
    require(set(chains)<=set(by_key),'INDEX_MISSING')
    for key,row in by_key.items():
        _canonical_resource(row,canonical)
        require(row['tip_attempt_ref']==(record_ref(chains[key][-1]) if key in chains else None),'INDEX_TIP')


def _cases(contract,index,a,artifact=None):
    c=contract['body']; cref=record_ref(contract)
    _assurance_index(index,a['logical_index'],a['canonical_ids'])
    _,intent=_contract(contract,index,a['decision_snapshot'],a['evaluation_tick'],a['expected_context_floor'],a['canonical_ids'])
    outcomes={o['outcome_id']:o for o in _covered(intent)}; rows={}; expected={}
    writer=_resolve(index,c['principal_ref'])['body']
    for row in a['expected_cases']:
        key=(canonical_bytes(row['contract_ref']),canonical_bytes(row['attempt_ref']),canonical_bytes(row['oracle_ref']),row['control_case'])
        require(key not in rows,'EXPECTED_CASE_COLLISION'); rows[key]=row
        # Validate every row's typed refs. Another contract is not evidence for this one.
        for field in ('contract_ref','attempt_ref','oracle_ref','expected_issuer_ref'): _resolve(index,row[field])
        if row['contract_ref']!=cref: continue
        o=outcomes.get(row['outcome_id']); known(o is not None and row['oracle_ref']==o['oracle_ref'],'EXPECTED_OUTCOME')
        attempt=_resolve(index,row['attempt_ref']); oracle=_resolve(index,row['oracle_ref'])['body']; issuer=_resolve(index,row['expected_issuer_ref'])['body']
        known(attempt['body']['contract_ref']==cref and row['target_id']==o['target_id']==oracle['target_id']==c['resource_id']==attempt['body']['resource_id'],'EXPECTED_TARGET')
        known(row['expected_issuer_ref']==oracle['custodian_ref'] and _eligible(issuer,writer),'EXPECTED_ISSUER')
        known(not oracle['readback_required'] or row['expected_readback_digest'] is not None,'EXPECTED_READBACK')
        _attempt_grant(attempt,index,a['decision_snapshot'],a['evaluation_tick'],a['expected_context_floor'],a['canonical_ids'])
        if artifact is not None: known(row['artifact_digest']==artifact,'EXPECTED_ARTIFACT')
        casekey=(row['outcome_id'],row['control_case']); require(casekey not in expected,'EXPECTED_CASE_DUPLICATE'); expected[casekey]=row
    known(set(expected)=={(o,c) for o in outcomes for c in ('POSITIVE','DISCONFIRMING')},'EXPECTED_CASE_COVERAGE')
    known(len({r['artifact_digest'] for r in expected.values()})==1,'EXPECTED_ARTIFACT')
    return rows,expected


def _evidence(record,contract,index,rows):
    b=record['body']; attempt=_resolve(index,b['attempt_ref']); key=(canonical_bytes(attempt['body']['contract_ref']),canonical_bytes(b['attempt_ref']),canonical_bytes(b['oracle_ref']),b['control_case'])
    row=rows.get(key)
    if row is None or row['contract_ref']!=record_ref(contract): return 'MODEL_UNKNOWN',None,'INAPPLICABLE_CASE'
    casekey=(row['outcome_id'],row['control_case'])
    if b['observed_target_id']!=row['target_id'] or b['artifact_digest']!=row['artifact_digest'] or b['issuer_ref']!=row['expected_issuer_ref'] or b['evidence_type']=='SOURCE': return 'MODEL_UNKNOWN',None,'INAPPLICABLE_EVIDENCE'
    oracle=_resolve(index,b['oracle_ref'])['body']; positive=b['control_case']=='POSITIVE'
    if row['expected_readback_digest'] is not None and b['readback_digest'] is None: return 'MODEL_UNKNOWN',casekey,'MISSING_READBACK'
    if b['verdict']=='UNKNOWN': return 'MODEL_UNKNOWN',casekey,'UNKNOWN_VERDICT'
    match=b['observation']==oracle['positive_observation' if positive else 'negative_observation'] and b['observed_error']==oracle['expected_error' if positive else 'negative_expected_error'] and b['readback_digest']==row['expected_readback_digest']
    if b['verdict']!=('MODELED_MATCH' if match else 'MODELED_MISMATCH'): return 'MODEL_REJECTED',casekey,'CLAIM_MISMATCH'
    return ('MODEL_CONSISTENT',casekey,None) if match else ('MODEL_REJECTED',casekey,'OBSERVATION_MISMATCH')


def evaluate_evidence(graph,evidence,auxiliary):
    d=None
    try:
        d=digest(evidence); index=_submission_index(graph,evidence,'evidence'); _aux(auxiliary,ASSURANCE_AUX); a=auxiliary
        _registry(a['canonical_ids'],a['alias_registry']); _applicability_links(evidence,index)
        b=evidence['body']; attempt=_resolve(index,b['attempt_ref']); contract=_resolve(index,attempt['body']['contract_ref'])
        # An unrelated attempt must not select a different contract and turn
        # its failed current-approval check into an applicable failure.
        cref=record_ref(contract)
        known(any(row['contract_ref']==cref and row['attempt_ref']==b['attempt_ref'] and row['oracle_ref']==b['oracle_ref'] and row['control_case']==b['control_case'] for row in a['expected_cases']),'INAPPLICABLE_CASE')
        rows,_=_cases(contract,index,a)
        code,_,reason=_evidence(evidence,contract,index,rows); return _result(code,d,reason)
    except Unknown as exc: return _result('MODEL_UNKNOWN',d,str(exc))
    except Invalid as exc: return _result('MODEL_REJECTED',d,str(exc))


def evaluate_acceptance(graph,acceptance,auxiliary):
    d=None
    try:
        d=digest(acceptance); index=_submission_index(graph,acceptance,'acceptance'); _aux(auxiliary,ASSURANCE_AUX); a=auxiliary; b=acceptance['body']
        _applicability_links(acceptance,index)
        _registry(a['canonical_ids'],a['alias_registry']); contract=_resolve(index,b['contract_ref']); c=contract['body']; require(b['decision_ref']==c['approved_decision_ref'],'ACCEPTANCE_DECISION')
        writer=_resolve(index,c['principal_ref'])['body']; reviewer=_resolve(index,b['reviewer_ref'])['body']; known(_eligible(reviewer,writer),'REVIEWER_INELIGIBLE')
        rows,expected=_cases(contract,index,a,b['artifact_digest']); observed={}; failure=False
        for r in b['evidence_refs']:
            evidence=_resolve(index,r); code,key,_=_evidence(evidence,contract,index,rows)
            if key is None: continue
            observed.setdefault(key,[]).append(code)
            if code=='MODEL_REJECTED': failure=True
        if failure: derived='MODEL_REJECTED'
        elif any(observed.get(k)!=['MODEL_CONSISTENT'] for k in expected): derived='MODEL_UNKNOWN'
        else: derived='MODEL_CONSISTENT'
        if b['verdict']!=derived: return _result('MODEL_REJECTED',d,'CLAIM_MISMATCH')
        return _result(derived,d,None if derived=='MODEL_CONSISTENT' else 'ACCEPTANCE_INCOMPLETE_OR_MISMATCH')
    except Unknown as exc: return _result('MODEL_UNKNOWN',d,str(exc))
    except Invalid as exc: return _result('MODEL_REJECTED',d,str(exc))
