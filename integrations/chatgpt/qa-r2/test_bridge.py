"""Actual imported R1 bridge, canonical fixtures; no mocked core calls."""
import copy,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path.cwd()))
from integrations.antigravity.factory.authority import AuthorityError
from integrations.antigravity.factory.scheduler import FactoryJournal
from integrations.antigravity.tests.test_factory_core import make_valid_packet
from integrations.chatgpt.host_bridge import plan_sequential,prepare_handoff,repair_controller
class HostBridge(unittest.TestCase):
    def setUp(self):
        self.a=make_valid_packet("QA-R2-A")
        self.b=make_valid_packet("QA-R2-B",depends_on=["QA-R2-A"])
        self.k=dict(expected_repo=self.a["repo_name"],observed_base_sha=self.a["base_sha"],trusted_verifiers={self.a["verifier"]})
    def test_plan_is_not_launch(self):
        v=plan_sequential([self.b,self.a],**self.k)
        self.assertEqual(v["sequential_handoffs"],["QA-R2-A","QA-R2-B"])
        self.assertFalse(v["native_context_created"])
        self.assertEqual(v["max_active_including_primary"],3)
    def test_bad_trust(self):
        for trust in (set(),{"untrusted"}):
            with self.subTest(trust=trust),self.assertRaises(AuthorityError):
                plan_sequential([self.a],**(self.k|{"trusted_verifiers":trust}))
    def test_repo_and_sha_drift(self):
        for override in ({"expected_repo":"wrong/repo"},{"observed_base_sha":"f"*40}):
            with self.subTest(override=override),self.assertRaises(AuthorityError):
                plan_sequential([self.a],**(self.k|override))
    def test_cycle(self):
        self.a["depends_on"]=["QA-R2-B"]
        with self.assertRaises(AuthorityError):
            plan_sequential([self.a,self.b],**self.k)
    def test_journal_reopen_and_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)/"journal.db"
            v=prepare_handoff(self.a,**self.k,journal_path=path)
            self.assertEqual(v["status"],"SEPARATE_SESSION_REQUIRED")
            self.assertIsNone(v["context_id"])
            self.assertFalse(v["independent_review"])
            self.assertEqual(v,prepare_handoff(copy.deepcopy(self.a),**self.k,journal_path=path))
            self.assertTrue(FactoryJournal(path).verify_hash_chain())
            conflict=copy.deepcopy(self.a); conflict["acceptance_criteria"]=["changed"]
            with self.assertRaises(AuthorityError):
                prepare_handoff(conflict,**self.k,journal_path=path)
    def test_repair_controller_is_canonical(self):
        from integrations.antigravity.factory.quality import SelfHealingController
        self.assertIsInstance(repair_controller(),SelfHealingController)
if __name__=="__main__":unittest.main(verbosity=2)
