"""Explicit public-oracle tests. Only the fixed sibling vector file is read."""
from __future__ import annotations
import unittest
from pathlib import Path
import json
import hashlib
import re
import contract_records as model

PUBLIC_SHA = 'c4cdbf36c9ded8ef8d54ef692c63ef4ef0dc454be7130859e59feb6656781ab3'
COMMON = {'domain','fixture_only','authority_granted','promotion_authorized','result_kind','result_code','reason_codes'}
VALIDATION = COMMON | {'record_digest'}
REDUCER = COMMON | {'submitted_event_ref','committed_event_ref','previous_head_ref','current_head_ref','current_state','evaluation_tick','submitted_event_is_current_approval'}
# Exact independent R4 D1 constants, not candidate-owned enums.
R4_VALID = ('STRUCTURALLY_VALID','MODEL_CONSISTENT','MODEL_REJECTED','MODEL_UNKNOWN')
R4_REDUCE = ('MODEL_COMMITTED','MODEL_ALREADY_COMMITTED','MODEL_CONFLICT','MODEL_REJECTED','MODEL_UNKNOWN')
R4_STATES = ('EMPTY','APPROVED','REJECTED','SUPERSEDED_PENDING','REVOKED','EXPIRED','UNKNOWN')
R4_MAX_INT = 9007199254740991
ID_PATTERN = r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}'
HEX_PATTERN = r'[0-9a-f]{64}'


def hashed(raw):
    return hashlib.sha256(raw).hexdigest()


class PublicOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name('vectors.json')
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('fixed sibling vectors.json unavailable')
        cls.bundle = json.loads(path.read_bytes().decode('utf-8'))
        source = cls.bundle['public_vectors_utf8'].encode('utf-8')
        if hashed(source) != PUBLIC_SHA or cls.bundle['public_vectors_sha256'] != PUBLIC_SHA:
            raise RuntimeError('public oracle bytes changed')
        cls.public = json.loads(source)

    def check_result(self, result, expected):
        self.assertEqual(type(result),dict)
        reducer = expected['result_kind']=='DECISION_REDUCER'
        self.assertEqual(set(result), REDUCER if reducer else VALIDATION)
        for key in result:
            if key in expected:
                self.assertEqual(result[key],expected[key],key)
        self.assertEqual(result['domain'],'FORGE_P1A_MODEL')
        self.assertIs(result['fixture_only'],True)
        self.assertIs(result['authority_granted'],False)
        self.assertIs(result['promotion_authorized'],False)
        self.assertEqual(result['result_kind'],expected['result_kind'])
        self.assertIs(type(result['result_code']),str)
        self.assertIn(result['result_code'], R4_REDUCE if reducer else R4_VALID)
        reasons=result['reason_codes']
        self.assertEqual(type(reasons),list)
        self.assertEqual(len(reasons),len(set(reasons)))
        for reason in reasons:
            self.assertIs(type(reason),str)
            self.assertIsNotNone(re.fullmatch(ID_PATTERN,reason))
        if result['result_code'] in ('MODEL_REJECTED','MODEL_UNKNOWN','MODEL_CONFLICT'):
            self.assertTrue(reasons)
        if 'required_reason_code' in expected:
            self.assertIn(expected['required_reason_code'],reasons)
        if 'allowed_result_codes' in expected:
            self.assertIn(result['result_code'],expected['allowed_result_codes'])
        if expected.get('required_not_consistent'):
            self.assertNotEqual(result['result_code'],'MODEL_CONSISTENT')
        if not reducer:
            if result['record_digest'] is not None:
                self.assertIs(type(result['record_digest']),str)
                self.assertIsNotNone(re.fullmatch(HEX_PATTERN,result['record_digest']))
            if 'digest_if_structurally_hashed' in expected:
                self.assertEqual(result['record_digest'],expected['digest_if_structurally_hashed'])
        else:
            for k in ('submitted_event_ref','committed_event_ref','previous_head_ref','current_head_ref'):
                if result[k] is not None:
                    rr=result[k]; self.assertIs(type(rr),dict)
                    self.assertEqual(set(rr),{'kind','record_id','scope','revision','digest'})
                    self.assertEqual(rr['kind'],'decision')
                    self.assertIs(type(rr['record_id']),str); self.assertIsNotNone(re.fullmatch(ID_PATTERN,rr['record_id']))
                    self.assertIs(type(rr['scope']),dict); self.assertEqual(set(rr['scope']),{'repo_id','lineage_id'})
                    for v in rr['scope'].values():
                        self.assertIs(type(v),str); self.assertIsNotNone(re.fullmatch(ID_PATTERN,v)); self.assertTrue(v.startswith('fixture:') and len(v)>8)
                    self.assertIs(type(rr['revision']),int); self.assertTrue(1<=rr['revision']<=R4_MAX_INT)
                    self.assertIs(type(rr['digest']),str); self.assertIsNotNone(re.fullmatch(HEX_PATTERN,rr['digest']))
            self.assertIn(result['current_state'],R4_STATES)
            tick=result['evaluation_tick']
            if tick is not None:
                self.assertIs(type(tick),int); self.assertTrue(0<=tick<=R4_MAX_INT)
            code=result['result_code']; committed=result['committed_event_ref']; current=result['current_head_ref']; previous=result['previous_head_ref']
            if code in ('MODEL_COMMITTED','MODEL_ALREADY_COMMITTED'):
                self.assertIsNotNone(committed); self.assertEqual(committed,result['submitted_event_ref'])
            else: self.assertIsNone(committed)
            if code=='MODEL_COMMITTED': self.assertEqual(current,committed)
            else: self.assertEqual(current,previous)
            if result['current_state']=='UNKNOWN': self.assertIsNone(current); self.assertIsNone(previous)
            if result['current_state']=='EMPTY': self.assertIsNone(current)
            self.assertIs(type(result['submitted_event_is_current_approval']),bool)
            self.assertIs(result['submitted_event_is_current_approval'],committed is not None and committed==current and result['current_state']=='APPROVED' and code in ('MODEL_COMMITTED','MODEL_ALREADY_COMMITTED'))

    def test_public_inventory(self):
        raw=self.public['raw_vectors']; semantic=self.public['semantic_cases']
        ids=[c['case_id'] for c in raw+semantic]
        self.assertEqual((len(raw),len(semantic),len(set(ids))),(47,76,123))
        self.assertEqual(set(self.bundle['raw_hex_by_case']),{c['case_id'] for c in raw})
        self.assertEqual(self.public['pins']['source_commit'],'928d08edc691dfaeccd4929d2a6566d1f3a3a789')
        self.assertEqual(self.public['pins']['source_tree'],'5c3c6a5557b9faa7f7dfbb66d226afa38f17d4b4')

    def test_historical_byte_custody_only(self):
        # This is not a rerun of the old operational parser or its tests.
        expected={'v1.raw.json':(1122,'7fc5dcf470b2f0c2d9c92d1271446e1c7478e3bc86d8e297bb084e11905dc05b'),
                  'v2.raw.json':(2843,'a972624be0c5a2e74027228fdd5007ef898560aee1ff29238b2d408ea33973d5'),
                  'v2.projection.json':(2645,'756497187dac8a8bcf9486ebc0c99227acabdef5a9efb6aa488a2895a6c37c4e')}
        self.assertEqual(set(self.bundle['historical_hex']),set(expected))
        for name,(length,digest) in expected.items():
            with self.subTest(name=name):
                raw=bytes.fromhex(self.bundle['historical_hex'][name]); self.assertEqual((len(raw),hashed(raw)),(length,digest))
                self.assertEqual(model.validate_raw(raw)['result_code'],'MODEL_REJECTED')

    def test_encoding_example(self):
        for case in self.public['encoding_only']:
            with self.subTest(scope=case['scope']):
                raw=model.canonical_bytes(case['input'])
                self.assertEqual(raw,case['canonical_utf8'].encode('utf-8'))
                self.assertEqual(hashed(raw),case['canonical_sha256'])

    def test_all_raw_cases(self):
        for case in self.public['raw_vectors']:
            with self.subTest(case_id=case['case_id']):
                raw=bytes.fromhex(self.bundle['raw_hex_by_case'][case['case_id']])
                self.assertEqual(len(raw),case['raw_bytes']); self.assertEqual(hashed(raw),case['raw_sha256'])
                result=model.validate_raw(raw); self.check_result(result,case['expected'])
                if 'canonical_utf8' in case:
                    record=model.parse_record(raw); canonical=model.canonical_bytes(record)
                    self.assertEqual(canonical,case['canonical_utf8'].encode('utf-8'))
                    self.assertEqual(hashed(canonical),case['canonical_sha256'])
                    self.assertEqual(model.digest(record),case['model_digest'])

    def test_all_semantic_cases(self):
        for case in self.public['semantic_cases']:
            with self.subTest(case_id=case['case_id']):
                # Fresh decoded fixture copies prevent a test from modifying another case.
                i=json.loads(json.dumps(case['inputs'])); before=json.dumps(i,sort_keys=True)
                op=case['operation_label']; snapshot=None
                if op=='decision_reducer':
                    result,snapshot=model.reduce_decision(i['graph'],i['snapshot'],i['submitted_event'],i['evaluation_tick'],i.get('stage_only',False))
                elif op=='context': result=model.evaluate_context(i['graph'],i['context'],i['expected_context_floor'])
                elif op=='command': result=model.evaluate_command(i['graph'],i['command'],i['auxiliary'])
                elif op=='attempt': result=model.evaluate_attempt(i['graph'],i['proposed_attempt'],i['logical_index'],i['evaluation_tick'],i['current_decision_snapshot'],i['canonical_ids'],i['alias_registry'],i['expected_context_floor'],i['historical_context_floors'],i['historical_decision_snapshots'])
                elif op=='evidence': result=model.evaluate_evidence(i['graph'],i['evidence'],i['auxiliary'])
                elif op=='acceptance': result=model.evaluate_acceptance(i['graph'],i['acceptance'],i['auxiliary'])
                elif op=='graph': result=model.validate_graph(i['graph'])
                elif op=='record_ingress': result=model.validate_record(i['record'])
                else: self.fail('unmapped public operation '+op)
                self.check_result(result,case['expected'])
                if op=='decision_reducer': self.assertEqual(snapshot,case['expected']['next_snapshot'])
                self.assertEqual(json.dumps(i,sort_keys=True),before,'input changed')

    # Corrective R1 regressions authored by Jane. Public oracle rows above
    # remain byte-identical; these are separate derived-input witnesses.
    def _writer_input(self, case_id):
        case=next(c for c in self.public['semantic_cases'] if c['case_id']==case_id)
        return json.loads(json.dumps(case['inputs']))

    def _writer_result(self, result, code, kind='VALIDATION', reason=None):
        expected={'result_kind':kind,'result_code':code}
        if reason is not None: expected['required_reason_code']=reason
        self.check_result(result,expected)

    def _attempt_result(self,i):
        return model.evaluate_attempt(i['graph'],i['proposed_attempt'],i['logical_index'],i['evaluation_tick'],i['current_decision_snapshot'],i['canonical_ids'],i['alias_registry'],i['expected_context_floor'],i['historical_context_floors'],i['historical_decision_snapshots'])

    def test_r1_f1_new_attempt_local_revision(self):
        # Both first use and successor start local revision 1. Ordinal is
        # independent, including the third successor positive witness.
        for case_id in ('registered-distinct-operation','cross-lineage-successor','third-successor'):
            with self.subTest(case_id=case_id):
                i=self._writer_input(case_id)
                self.assertEqual(i['proposed_attempt']['revision'],1)
                self._writer_result(self._attempt_result(i),'MODEL_CONSISTENT')
                i['proposed_attempt']['revision']=2
                self._writer_result(self._attempt_result(i),'MODEL_REJECTED',reason='NEW_ATTEMPT_REVISION')

    def _foreign_graph(self):
        # Exact public A prefix and B's independently registered operation.
        # B is not a replacement for A's current decision or grant.
        a=self._writer_input('exact-positive-evidence')
        b=self._writer_input('registered-distinct-operation')
        lineage=b['proposed_attempt']['scope']['lineage_id']
        extra=[r for r in b['graph'] if r['scope']['lineage_id']==lineage]
        extra.append(b['proposed_attempt'])
        graph=a['graph']+extra
        return a,b,graph,extra

    def test_r1_f2_foreign_evidence_refs_are_unknown_not_graph_admitted(self):
        for field,kind in (('attempt_ref','attempt'),('oracle_ref','oracle'),('issuer_ref','principal')):
            with self.subTest(field=field):
                a,b,graph,extra=self._foreign_graph()
                foreign=next(r for r in extra if r['kind']==kind)
                evidence=a['evidence']; evidence['record_id']='fixture:r1-foreign-'+kind
                evidence['body'][field]=model.record_ref(foreign)
                before=json.dumps(graph,sort_keys=True)
                self._writer_result(model.validate_graph(graph),'MODEL_CONSISTENT')
                self._writer_result(model.evaluate_evidence(graph,evidence,a['auxiliary']),'MODEL_UNKNOWN',reason='INAPPLICABLE_REF_SCOPE')
                self._writer_result(model.validate_graph(graph+[evidence]),'MODEL_REJECTED',reason='REF_SCOPE')
                # A malformed graph cannot be made acceptable by the receipt API.
                self._writer_result(model.evaluate_evidence(graph+[evidence],evidence,a['auxiliary']),'MODEL_REJECTED',reason='REF_SCOPE')
                self.assertEqual(json.dumps(graph,sort_keys=True),before)

    def test_r1_f2_unresolved_and_malformed_receipt_distinguished(self):
        i=self._writer_input('exact-positive-evidence'); evidence=i['evidence']; evidence['record_id']='fixture:r1-unresolved'
        evidence['body']['attempt_ref']['digest']='0'*64
        self._writer_result(model.evaluate_evidence(i['graph'],evidence,i['auxiliary']),'MODEL_UNKNOWN',reason='INAPPLICABLE_REF')
        self._writer_result(model.validate_graph(i['graph']+[evidence]),'MODEL_REJECTED',reason='UNRESOLVED_REF')
        evidence['body']['attempt_ref']['kind']='oracle'
        self._writer_result(model.evaluate_evidence(i['graph'],evidence,i['auxiliary']),'MODEL_REJECTED',reason='REF_KIND')

    def test_r1_f2_unrelated_attempt_cannot_select_wrong_contract(self):
        a,b,graph,extra=self._foreign_graph()
        evidence=a['evidence']; evidence['record_id']='fixture:r1-unrelated-attempt'; evidence['scope']=dict(b['proposed_attempt']['scope'])
        evidence['body']['attempt_ref']=model.record_ref(b['proposed_attempt'])
        evidence['body']['oracle_ref']=model.record_ref(next(r for r in extra if r['kind']=='oracle'))
        evidence['body']['issuer_ref']=model.record_ref(next(r for r in extra if r['kind']=='principal' and r['record_id']=='fixture:b-custodian'))
        # Exact valid B receipt links, but no independent expected B case.
        self._writer_result(model.validate_graph(graph+[evidence]),'MODEL_CONSISTENT')
        self._writer_result(model.evaluate_evidence(graph,evidence,a['auxiliary']),'MODEL_UNKNOWN',reason='INAPPLICABLE_CASE')

    def test_r1_f2_foreign_acceptance_evidence_cannot_grant_credit(self):
        a,b,graph,extra=self._foreign_graph()
        evidence=a['evidence']; evidence['record_id']='fixture:r1-foreign-receipt'; evidence['scope']=dict(b['proposed_attempt']['scope'])
        evidence['body']['attempt_ref']=model.record_ref(b['proposed_attempt'])
        evidence['body']['oracle_ref']=model.record_ref(next(r for r in extra if r['kind']=='oracle'))
        evidence['body']['issuer_ref']=model.record_ref(next(r for r in extra if r['kind']=='principal' and r['record_id']=='fixture:b-custodian'))
        graph.append(evidence)
        i=self._writer_input('both-controls'); acceptance=i['acceptance']; acceptance['record_id']='fixture:r1-foreign-acceptance'
        acceptance['body']['evidence_refs']=[model.record_ref(evidence)]
        acceptance['body']['verdict']='MODEL_UNKNOWN'
        self._writer_result(model.validate_graph(graph),'MODEL_CONSISTENT')
        self._writer_result(model.evaluate_acceptance(graph,acceptance,i['auxiliary']),'MODEL_UNKNOWN',reason='INAPPLICABLE_REF_SCOPE')
        self._writer_result(model.validate_graph(graph+[acceptance]),'MODEL_REJECTED',reason='REF_SCOPE')
        self._writer_result(model.evaluate_acceptance(graph+[acceptance],acceptance,i['auxiliary']),'MODEL_REJECTED',reason='REF_SCOPE')

    def test_r1_orphan_chronology_and_expiry(self):
        # Orphan validity is evaluated against its declared predecessor at its
        # own creation tick, never against the later winning head.
        for defect in ('decreasing','nonapproval-expiry','approval-expiry','future'):
            with self.subTest(defect=defect):
                i=self._writer_input('stale-orphan'); orphan=i['snapshot']['events'][1]
                if defect=='decreasing': orphan['body']['creation_tick']=0
                elif defect=='nonapproval-expiry': orphan['body']['expiry_tick']=3
                elif defect=='approval-expiry':
                    # Use a staged genesis APPROVE with expiry at creation.
                    i=self._writer_input('late-staged-orphan'); orphan=i['snapshot']['events'][0]
                    orphan['body']['expiry_tick']=orphan['body']['creation_tick']
                else: orphan['body']['creation_tick']=i['evaluation_tick']+1
                before=json.dumps(i,sort_keys=True)
                result,snapshot=model.reduce_decision(i['graph'],i['snapshot'],i['submitted_event'],i['evaluation_tick'],i['stage_only'])
                self._writer_result(result,'MODEL_UNKNOWN','DECISION_REDUCER')
                self.assertIsNone(snapshot); self.assertEqual(result['current_state'],'UNKNOWN')
                self.assertIsNone(result['previous_head_ref']); self.assertIsNone(result['current_head_ref']); self.assertIsNone(result['committed_event_ref'])
                self.assertIs(result['submitted_event_is_current_approval'],False)
                self.assertEqual(json.dumps(i,sort_keys=True),before)

    def test_r1_valid_orphans_remain_non_authoritative(self):
        for case_id,code,state in (('stale-orphan','MODEL_CONFLICT','REVOKED'),('late-staged-orphan','MODEL_CONFLICT','EMPTY'),('same-tick-staged-winner','MODEL_COMMITTED','APPROVED')):
            with self.subTest(case_id=case_id):
                i=self._writer_input(case_id); before=json.dumps(i,sort_keys=True)
                result,snapshot=model.reduce_decision(i['graph'],i['snapshot'],i['submitted_event'],i['evaluation_tick'],i['stage_only'])
                self._writer_result(result,code,'DECISION_REDUCER'); self.assertEqual(result['current_state'],state)
                self.assertIs(result['submitted_event_is_current_approval'],code=='MODEL_COMMITTED')
                if code=='MODEL_CONFLICT': self.assertEqual(snapshot,i['snapshot'])
                self.assertEqual(json.dumps(i,sort_keys=True),before)

    def test_r1_graph_nested_mutable_aliases(self):
        for form in ('scope','list','deep-ref','top-level','cycle'):
            with self.subTest(form=form):
                graph=self._writer_input('exact-positive-evidence')['graph']
                self._writer_result(model.validate_graph(graph),'MODEL_CONSISTENT')
                if form=='scope':
                    self.assertEqual(graph[0]['scope'],graph[1]['scope']); graph[1]['scope']=graph[0]['scope']
                elif form=='list':
                    graph[1]['body']['specialization_ids']=graph[0]['body']['specialization_ids']
                elif form=='deep-ref':
                    oracle=next(r for r in graph if r['kind']=='oracle'); intent=next(r for r in graph if r['kind']=='intent')
                    intent['body']['outcomes'][0]['oracle_ref']['scope']=oracle['body']['custodian_ref']['scope']
                elif form=='top-level': graph.append(graph[0])
                else: graph[0]['body']['specialization_ids'].append(graph[0]['body'])
                self._writer_result(model.validate_graph(graph),'MODEL_REJECTED',reason='CYCLE_OR_MUTABLE_ALIAS')

    def test_r1_auxiliary_nested_aliases(self):
        i=self._writer_input('exact-positive-evidence'); a=i['auxiliary']
        original=a['expected_context_floor']['intent_ref']; linked=a['decision_snapshot']['events'][0]['body']['intent_ref']
        self.assertEqual(original,linked); a['expected_context_floor']['intent_ref']=linked
        self._writer_result(model.evaluate_evidence(i['graph'],i['evidence'],a),'MODEL_REJECTED',reason='CYCLE_OR_MUTABLE_ALIAS')

    def test_r1_history_nested_aliases(self):
        i=self._writer_input('cross-lineage-successor')
        floor=i['historical_context_floors'][0]; snapshot=i['historical_decision_snapshots'][0]
        linked=snapshot['events'][0]['body']['intent_ref']
        self.assertEqual(floor['intent_ref'],linked); floor['intent_ref']=linked
        self._writer_result(self._attempt_result(i),'MODEL_REJECTED',reason='CYCLE_OR_MUTABLE_ALIAS')


    # R2 writer-authored witnesses; never alter the frozen public oracle.
    def _copy(self,v):
        return json.loads(json.dumps(v))

    def _ordered(self,rows):
        return sorted(rows,key=model.canonical_bytes)

    def _reduce(self,i):
        return model.reduce_decision(i['graph'],i['snapshot'],i['submitted_event'],i['evaluation_tick'],i.get('stage_only',False))

    def _accept(self,i):
        return model.evaluate_acceptance(i['graph'],i['acceptance'],i['auxiliary'])

    def _receipt(self,i):
        return model.evaluate_evidence(i['graph'],i['evidence'],i['auxiliary'])

    def _rewrite_refs(self,value,changes):
        if type(value) is dict:
            if set(value)=={'kind','record_id','scope','revision','digest'}:
                return self._copy(changes.get(model.canonical_bytes(value),value))
            result={k:self._rewrite_refs(v,changes) for k,v in value.items()}
            for k in ('evidence_refs','oracle_refs','expected_cases','logical_index'):
                if k in result: result[k]=self._ordered(result[k])
            return result
        if type(value) is list: return [self._rewrite_refs(v,changes) for v in value]
        return value

    def _mutate_graph(self,i,change):
        # Rebuild all downstream exact refs in topological order; no stale
        # digest is allowed to accidentally satisfy a negative test.
        changes={}; graph=[]
        for old in i['graph']:
            r=self._rewrite_refs(old,changes)
            change(r)
            changes[model.canonical_bytes(model.record_ref(old))]=model.record_ref(r)
            graph.append(r)
        result={k:self._rewrite_refs(v,changes) for k,v in i.items() if k!='graph'}
        result['graph']=graph
        return result

    def test_r2_n1_graph_snapshot_submission_identity(self):
        i=self._writer_input('fresh-approval'); event=self._copy(i['submitted_event'])
        i['graph'].append(event)
        self._writer_result(self._reduce(i)[0],'MODEL_COMMITTED','DECISION_REDUCER')
        i['submitted_event']['body']['reason']='distinct event bytes'
        result,next_snapshot=self._reduce(i)
        self._writer_result(result,'MODEL_REJECTED','DECISION_REDUCER','EVENT_ID_COLLISION')
        self.assertEqual(next_snapshot,i['snapshot'])
        i['submitted_event']['revision']=2
        self._writer_result(self._reduce(i)[0],'MODEL_REJECTED','DECISION_REDUCER','EVENT_ID_COLLISION')
        i['snapshot']['events']=[self._copy(i['submitted_event'])]
        i['snapshot']['head_ref']=model.record_ref(i['submitted_event'])
        self._writer_result(self._reduce(i)[0],'MODEL_UNKNOWN','DECISION_REDUCER')

    def test_r2_n2_output_capacity_and_consumability(self):
        for n in (157,158):
            for stage in (False,True):
                with self.subTest(events=n,stage=stage):
                    i=self._writer_input('fresh-approval'); i['stage_only']=stage
                    for k in range(n):
                        event=self._copy(i['submitted_event']); event['record_id']='fixture:r2-capacity-'+str(k)
                        i['snapshot']['events'].append(event)
                    before=self._copy(i)
                    result,next_snapshot=self._reduce(i)
                    if n==158:
                        self._writer_result(result,'MODEL_REJECTED','DECISION_REDUCER','PRIMITIVE_LIMIT')
                        self.assertEqual(next_snapshot,before['snapshot'])
                    else:
                        self._writer_result(result,'MODEL_UNKNOWN' if stage else 'MODEL_COMMITTED','DECISION_REDUCER')
                        self.assertEqual(len(next_snapshot['events']),n+1)
                        i['snapshot']=next_snapshot; i['stage_only']=False
                        result2,_=self._reduce(i)
                        self._writer_result(result2,'MODEL_COMMITTED' if stage else 'MODEL_ALREADY_COMMITTED','DECISION_REDUCER')
                    self.assertEqual(i['graph'],before['graph'])
                    self.assertEqual(i['submitted_event'],before['submitted_event'])
        # The primitive array ceiling is independent of the tighter event-node
        # limit. A 256-event snapshot cannot reach that ceiling with valid records.
        self.assertEqual(len(model.canonical_bytes([0]*256)),513)
        with self.assertRaises(ValueError): model.canonical_bytes([0]*257)

    def test_r2_n3_stale_predecessor_chronology(self):
        i=self._writer_input('stale-orphan'); del i['snapshot']['events'][1]
        winner=i['snapshot']['events'][-1]; winner['body']['creation_tick']=3
        i['snapshot']['head_ref']=model.record_ref(winner); i['evaluation_tick']=3
        result,snapshot=self._reduce(i)
        self._writer_result(result,'MODEL_CONFLICT','DECISION_REDUCER')
        self.assertEqual(result['current_state'],'REVOKED'); self.assertEqual(snapshot,i['snapshot'])
        i['submitted_event']['body']['creation_tick']=0
        self._writer_result(self._reduce(i)[0],'MODEL_REJECTED','DECISION_REDUCER','DECISION_CHRONOLOGY')

    def test_r2_n4_historical_local_revision(self):
        def change(r):
            if r['kind']=='attempt': r['revision']=2
        i=self._writer_input('cross-lineage-successor')
        self._writer_result(self._attempt_result(i),'MODEL_CONSISTENT')
        i=self._mutate_graph(i,change)
        self._writer_result(self._attempt_result(i),'MODEL_REJECTED',reason='HISTORICAL_ATTEMPT_REVISION')
        a=self._writer_input('both-controls')
        self._writer_result(self._accept(a),'MODEL_CONSISTENT')
        a=self._mutate_graph(a,change)
        self._writer_result(self._accept(a),'MODEL_REJECTED',reason='HISTORICAL_ATTEMPT_REVISION')

    def _two_attempt_assurance(self,invalid_prior):
        i=self._writer_input('both-controls'); old=next(r for r in i['graph'] if r['kind']=='attempt')
        old_ref=model.record_ref(old); first=self._copy(old); second=self._copy(old)
        if invalid_prior: first['body']['requested_effect_class']='SOURCE_WRITE'
        second['record_id']='fixture:r2-attempt-two'; second['body']['attempt_id']='fixture:r2-attempt-two'
        second['body']['attempt_ordinal']=2; second['body']['predecessor_attempt_ref']=model.record_ref(first)
        changes={model.canonical_bytes(old_ref):model.record_ref(second)}
        graph=[]
        for r in i['graph']:
            if r['kind']=='attempt': graph.extend((first,second)); continue
            if r['kind']=='acceptance': continue
            new=self._rewrite_refs(r,changes)
            changes[model.canonical_bytes(model.record_ref(r))]=model.record_ref(new)
            graph.append(new)
        i['graph']=graph
        i['auxiliary']=self._rewrite_refs(i['auxiliary'],changes)
        i['acceptance']=self._rewrite_refs(i['acceptance'],changes)
        return i

    def test_r2_n5_assurance_validates_historical_grant(self):
        self._writer_result(self._accept(self._two_attempt_assurance(False)),'MODEL_CONSISTENT')
        self._writer_result(self._accept(self._two_attempt_assurance(True)),'MODEL_REJECTED',reason='ATTEMPT_EFFECT')

    def test_r2_n5_missing_historical_authority(self):
        i=self._writer_input('cross-lineage-successor')
        self._writer_result(self._attempt_result(i),'MODEL_CONSISTENT')
        i['historical_context_floors']=[]
        self._writer_result(self._attempt_result(i),'MODEL_UNKNOWN',reason='HISTORICAL_AUTHORITY_MISSING')
        i=self._writer_input('cross-lineage-successor'); i['historical_decision_snapshots']=[]
        self._writer_result(self._attempt_result(i),'MODEL_UNKNOWN',reason='HISTORICAL_AUTHORITY_MISSING')

    def _cross_lineage_assurance(self):
        src=self._writer_input('cross-lineage-successor'); a=self._writer_input('both-controls')
        graph=src['graph']; second=src['proposed_attempt']; graph.append(second)
        lineage=second['scope']['lineage_id']
        b={r['kind']:r for r in graph if r['scope']['lineage_id']==lineage and r['kind'] not in ('principal',)}
        reviewer=next(r for r in graph if r['scope']['lineage_id']==lineage and r['record_id']=='fixture:b-reviewer')
        aux=a['auxiliary']; aux['decision_snapshot']=self._copy(src['current_decision_snapshot'])
        aux['expected_context_floor']=self._copy(src['expected_context_floor'])
        aux['evaluation_tick']=src['evaluation_tick']; aux['canonical_ids']=self._copy(src['canonical_ids'])
        aux['logical_index'][0]['tip_attempt_ref']=model.record_ref(second)
        evidence_refs=[]
        for row in aux['expected_cases']:
            row['contract_ref']=model.record_ref(b['contract']); row['attempt_ref']=model.record_ref(second)
            row['oracle_ref']=model.record_ref(b['oracle']); row['expected_issuer_ref']=self._copy(b['oracle']['body']['custodian_ref'])
            row['outcome_id']=b['oracle']['body']['outcome_id']; row['target_id']=b['oracle']['body']['target_id']
            e=self._copy(next(r for r in a['graph'] if r['kind']=='evidence' and r['body']['control_case']==row['control_case']))
            e['record_id']='fixture:r2-b-'+row['control_case']; e['scope']=dict(second['scope'])
            e['body']['attempt_ref']=model.record_ref(second); e['body']['oracle_ref']=model.record_ref(b['oracle'])
            e['body']['issuer_ref']=self._copy(row['expected_issuer_ref']); e['body']['observed_target_id']=row['target_id']
            positive=row['control_case']=='POSITIVE'; oracle=b['oracle']['body']
            e['body']['observation']=oracle['positive_observation' if positive else 'negative_observation']
            e['body']['observed_error']=oracle['expected_error' if positive else 'negative_expected_error']
            graph.append(e); evidence_refs.append(model.record_ref(e))
        aux['expected_cases']=self._ordered(aux['expected_cases'])
        acceptance=a['acceptance']; acceptance['record_id']='fixture:r2-b-acceptance'; acceptance['scope']=dict(second['scope'])
        acceptance['body']['contract_ref']=model.record_ref(b['contract']); acceptance['body']['decision_ref']=model.record_ref(b['decision'])
        acceptance['body']['reviewer_ref']=model.record_ref(reviewer); acceptance['body']['evidence_refs']=self._ordered(evidence_refs)
        a['graph']=graph
        return a,src

    def test_r2_n5_assurance_cross_lineage_history(self):
        # A separately supplied historical A floor/snapshot must be available
        # when the selected B control attempt follows A.
        a,src=self._cross_lineage_assurance(); aux=a['auxiliary']
        self._writer_result(self._accept(a),'MODEL_UNKNOWN',reason='HISTORICAL_AUTHORITY_MISSING')
        aux['historical_context_floors']=self._copy(src['historical_context_floors'])
        aux['historical_decision_snapshots']=self._copy(src['historical_decision_snapshots'])
        self._writer_result(self._accept(a),'MODEL_CONSISTENT')

    def test_r2_n6_missing_index_is_not_wrong_tip(self):
        i=self._writer_input('registered-distinct-operation')
        i['logical_index']=[row for row in i['logical_index'] if row['tip_attempt_ref'] is None]
        self._writer_result(self._attempt_result(i),'MODEL_UNKNOWN',reason='INDEX_MISSING')
        i=self._writer_input('registered-distinct-operation')
        next(row for row in i['logical_index'] if row['tip_attempt_ref'] is not None)['tip_attempt_ref']=None
        self._writer_result(self._attempt_result(i),'MODEL_REJECTED',reason='INDEX_TIP')
        a=self._writer_input('both-controls'); a['auxiliary']['logical_index']=[]
        self._writer_result(self._accept(a),'MODEL_UNKNOWN',reason='INDEX_MISSING')
        a=self._writer_input('both-controls'); a['auxiliary']['logical_index'][0]['tip_attempt_ref']=None
        self._writer_result(self._accept(a),'MODEL_REJECTED',reason='INDEX_TIP')

    def test_r2_n7_expected_binding_vs_structure(self):
        for field in ('expected_issuer_ref','attempt_ref','oracle_ref'):
            with self.subTest(field=field):
                i=self._writer_input('exact-positive-evidence'); aux=i['auxiliary']
                row=next(r for r in aux['expected_cases'] if r['control_case']=='DISCONFIRMING')
                row[field]['digest']='0'*64; aux['expected_cases']=self._ordered(aux['expected_cases'])
                self._writer_result(self._receipt(i),'MODEL_UNKNOWN',reason='EXPECTED_BINDING_UNKNOWN')
                row[field]['digest']='bad'
                self._writer_result(self._receipt(i),'MODEL_REJECTED')
        i=self._writer_input('exact-positive-evidence'); aux=i['auxiliary']
        row=self._copy(aux['expected_cases'][0]); row['artifact_digest']='0'*64
        aux['expected_cases']=self._ordered(aux['expected_cases']+[row])
        self._writer_result(self._receipt(i),'MODEL_REJECTED',reason='EXPECTED_CASE_COLLISION')

    def test_r2_n8_duplicate_applicable_mismatch_is_ambiguous(self):
        i=self._writer_input('both-controls')
        positive=self._copy(next(r for r in i['graph'] if r['kind']=='evidence' and r['body']['control_case']=='POSITIVE'))
        positive['record_id']='fixture:r2-duplicate-mismatch'; positive['body']['observation']='distinct wrong observation'; positive['body']['verdict']='MODELED_MISMATCH'
        i['graph'].append(positive); i['acceptance']['record_id']='fixture:r2-duplicate-assessment'
        b=i['acceptance']['body']; b['evidence_refs']=self._ordered(b['evidence_refs']+[model.record_ref(positive)])
        b['verdict']='MODEL_UNKNOWN'
        self._writer_result(self._accept(i),'MODEL_UNKNOWN')
        b['verdict']='MODEL_CONSISTENT'
        self._writer_result(self._accept(i),'MODEL_REJECTED',reason='CLAIM_MISMATCH')
        b['evidence_refs']=self._ordered(b['evidence_refs']+[model.record_ref(positive)])
        self._writer_result(self._accept(i),'MODEL_REJECTED')
        self._writer_result(self._accept(self._writer_input('applicable-failure-missing-positive')),'MODEL_REJECTED')

    def test_r2_n9_cross_argument_aliases_and_fresh_outputs(self):
        i=self._writer_input('context-complete')
        self._writer_result(model.evaluate_context(i['graph'],i['context'],i['expected_context_floor']),'MODEL_CONSISTENT')
        i['expected_context_floor']['required_sources']=i['context']['body']['required_sources']
        self._writer_result(model.evaluate_context(i['graph'],i['context'],i['expected_context_floor']),'MODEL_REJECTED',reason='CYCLE_OR_MUTABLE_ALIAS')
        i=self._writer_input('command-valid'); i['auxiliary']['expected_context_floor']['intent_ref']=i['command']['body']['intent_ref']
        self._writer_result(model.evaluate_command(i['graph'],i['command'],i['auxiliary']),'MODEL_REJECTED',reason='CYCLE_OR_MUTABLE_ALIAS')
        i=self._writer_input('cross-lineage-successor'); i['historical_context_floors'][0]['intent_ref']=next(r for r in i['graph'] if r['kind']=='context')['body']['intent_ref']
        self._writer_result(self._attempt_result(i),'MODEL_REJECTED',reason='CYCLE_OR_MUTABLE_ALIAS')
        i=self._writer_input('exact-positive-evidence'); i['auxiliary']['expected_cases'][0]['attempt_ref']=i['evidence']['body']['attempt_ref']
        self._writer_result(self._receipt(i),'MODEL_REJECTED',reason='CYCLE_OR_MUTABLE_ALIAS')
        i=self._writer_input('both-controls'); i['auxiliary']['expected_cases'][0]['contract_ref']=i['acceptance']['body']['contract_ref']
        self._writer_result(self._accept(i),'MODEL_REJECTED',reason='CYCLE_OR_MUTABLE_ALIAS')
        i=self._writer_input('fresh-approval'); original=self._copy(i)
        result,snapshot=self._reduce(i); self._writer_result(result,'MODEL_COMMITTED','DECISION_REDUCER')
        result['current_head_ref']['scope']['repo_id']='fixture:changed'
        self.assertNotEqual(result['current_head_ref'],result['committed_event_ref'])
        self.assertEqual(snapshot['head_ref'],result['committed_event_ref'])
        snapshot['events'][0]['body']['reason']='changed output'
        self.assertEqual(i,original)
        i['submitted_event']['scope']=i['graph'][0]['scope']
        self._writer_result(self._reduce(i)[0],'MODEL_REJECTED','DECISION_REDUCER','CYCLE_OR_MUTABLE_ALIAS')

    def test_r2_n10_reviewer_read_only_and_capability_modes(self):
        for effect in ('READ','SOURCE_WRITE','REF_WRITE'):
            with self.subTest(effect=effect):
                def change(r):
                    if r['record_id']=='fixture:b-writer': r['body']['role']='REVIEWER'
                    if r['scope']['lineage_id']=='fixture:public-b' and r['kind'] in ('contract','grant'):
                        r['body']['allowed_effect_classes']=sorted({'READ',effect})
                i=self._mutate_graph(self._writer_input('registered-distinct-operation'),change)
                i['proposed_attempt']['body']['requested_effect_class']=effect
                self._writer_result(self._attempt_result(i),'MODEL_CONSISTENT' if effect=='READ' else 'MODEL_REJECTED',reason=None if effect=='READ' else 'REVIEWER_EFFECT')
        for field in ('availability','permission','quota','quiescence'):
            for mode in ('UNKNOWN','UNAVAILABLE'):
                with self.subTest(field=field,mode=mode):
                    def change(r):
                        if r['kind']=='capability' and r['scope']['lineage_id']=='fixture:public-b': r['body'][field]=mode
                    i=self._mutate_graph(self._writer_input('registered-distinct-operation'),change)
                    self._writer_result(self._attempt_result(i),'MODEL_UNKNOWN',reason='CAPABILITY_UNAVAILABLE')

    # R3 residual witnesses, derived only from the unchanged public fixtures.
    def _r3_historical_tick(self,i,tick,mode):
        prior=next(r for r in i['graph'] if r['kind']=='attempt' and r['body']['attempt_ordinal']==1)
        grant_ref=prior['body']['grant_ref']
        def change(r):
            if r['kind']=='grant' and r['record_id']==grant_ref['record_id'] and r['scope']==grant_ref['scope'] and r['revision']==grant_ref['revision']:
                if mode=='future': r['body']['valid_from_tick']=tick+1
                elif mode=='equal': r['body']['valid_from_tick']=tick
                else: r['body']['expires_tick']=tick
        return self._mutate_graph(i,change)

    def test_r3_n5_attempt_historical_tick_bound(self):
        for mode in ('future','equal','expired'):
            with self.subTest(mode=mode):
                i=self._writer_input('cross-lineage-successor')
                self.assertEqual(i['evaluation_tick'],2)
                i=self._r3_historical_tick(i,i['evaluation_tick'],mode)
                self._writer_result(model.validate_graph(i['graph']+[i['proposed_attempt']]),'MODEL_CONSISTENT')
                self._writer_result(self._attempt_result(i),'MODEL_REJECTED' if mode=='future' else 'MODEL_CONSISTENT',reason='HISTORICAL_GRANT_FUTURE' if mode=='future' else None)

    def test_r3_n5_assurance_historical_tick_bound(self):
        for mode in ('future','equal','expired'):
            with self.subTest(mode=mode):
                a,src=self._cross_lineage_assurance(); aux=a['auxiliary']
                aux['historical_context_floors']=self._copy(src['historical_context_floors'])
                aux['historical_decision_snapshots']=self._copy(src['historical_decision_snapshots'])
                self.assertEqual(aux['evaluation_tick'],2)
                a=self._r3_historical_tick(a,aux['evaluation_tick'],mode)
                self._writer_result(model.validate_graph(a['graph']+[a['acceptance']]),'MODEL_CONSISTENT')
                code='MODEL_REJECTED' if mode=='future' else 'MODEL_CONSISTENT'
                reason='HISTORICAL_GRANT_FUTURE' if mode=='future' else None
                self._writer_result(self._accept(a),code,reason=reason)
                evidence=self._copy(next(r for r in a['graph'] if r['kind']=='evidence' and r['body']['control_case']=='POSITIVE'))
                self._writer_result(model.evaluate_evidence(a['graph'],evidence,a['auxiliary']),code,reason=reason)

    def _r3_wrong_selected_grant(self,case_id):
        i=self._writer_input(case_id)
        selected_ref=i['auxiliary']['expected_cases'][0]['attempt_ref']
        attempt=next(r for r in i['graph'] if model.record_ref(r)==selected_ref)
        cref=attempt['body']['contract_ref']; gref=attempt['body']['grant_ref']
        pos=next(k for k,r in enumerate(i['graph']) if model.record_ref(r)==cref)
        other=self._copy(i['graph'][pos]); other['record_id']='fixture:r3-other-contract'
        i['graph'].insert(pos+1,other)
        def change(r):
            if r['kind']=='grant' and r['record_id']==gref['record_id'] and r['scope']==gref['scope'] and r['revision']==gref['revision']:
                r['body']['contract_ref']=model.record_ref(other)
        i=self._mutate_graph(i,change)
        self._writer_result(model.validate_graph(i['graph']),'MODEL_CONSISTENT')
        return i

    def test_r3_n7_evidence_wrong_selected_grant_is_unknown(self):
        i=self._r3_wrong_selected_grant('exact-positive-evidence')
        self._writer_result(self._receipt(i),'MODEL_UNKNOWN',reason='EXPECTED_ATTEMPT_BINDING')
        original=self._copy(i['evidence'])
        self.assertIn(original,i['graph'])
        i['evidence']['body']['verdict']='UNKNOWN'
        self.assertNotEqual(i['evidence'],original)
        # R4: a changed verdict with the original graph identity must reject.
        self._writer_result(self._receipt(i),'MODEL_REJECTED',reason='GRAPH_SUBMISSION_CONFLICT')
        i['evidence']['record_id']='fixture:r4-unknown-evidence'
        self._writer_result(model.validate_graph(i['graph']+[i['evidence']]),'MODEL_CONSISTENT')
        self._writer_result(self._receipt(i),'MODEL_UNKNOWN',reason='EXPECTED_ATTEMPT_BINDING')
        i['auxiliary']['logical_index'][0]['tip_attempt_ref']=None
        self._writer_result(self._receipt(i),'MODEL_REJECTED',reason='INDEX_TIP')

    def test_r3_n7_acceptance_wrong_selected_grant_is_unknown(self):
        i=self._r3_wrong_selected_grant('both-controls')
        original=self._copy(i['acceptance'])
        self.assertIn(original,i['graph'])
        self._writer_result(self._accept(i),'MODEL_UNKNOWN',reason='EXPECTED_ATTEMPT_BINDING')
        i['acceptance']['body']['verdict']='MODEL_UNKNOWN'
        self.assertNotEqual(i['acceptance'],original)
        # Keep the same-key divergent-bytes denial as an explicit control.
        self._writer_result(self._accept(i),'MODEL_REJECTED',reason='GRAPH_SUBMISSION_CONFLICT')
        i['acceptance']['record_id']='fixture:r4-unknown-acceptance'
        self._writer_result(model.validate_graph(i['graph']+[i['acceptance']]),'MODEL_CONSISTENT')
        self._writer_result(self._accept(i),'MODEL_UNKNOWN',reason='EXPECTED_ATTEMPT_BINDING')
        i['auxiliary']['logical_index'][0]['tip_attempt_ref']=None
        self._writer_result(self._accept(i),'MODEL_REJECTED',reason='INDEX_TIP')
