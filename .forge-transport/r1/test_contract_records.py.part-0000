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
        self.assertIn(result['result_code'], model.REDUCE if reducer else model.VALID)
        reasons=result['reason_codes']
        self.assertEqual(type(reasons),list)
        self.assertEqual(len(reasons),len(set(reasons)))
        for reason in reasons:
            self.assertRegex(reason,r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')
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
                self.assertRegex(result['record_digest'],r'^[0-9a-f]{64}$')
            if 'digest_if_structurally_hashed' in expected:
                self.assertEqual(result['record_digest'],expected['digest_if_structurally_hashed'])
        else:
            for k in ('submitted_event_ref','committed_event_ref','previous_head_ref','current_head_ref'):
                if result[k] is not None:
                    self.assertEqual(set(result[k]),{'kind','record_id','scope','revision','digest'})
                    self.assertEqual(result[k]['kind'],'decision')
            self.assertIn(result['current_state'],model.STATE)
            self.assertEqual(type(result['submitted_event_is_current_approval']),bool)

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
