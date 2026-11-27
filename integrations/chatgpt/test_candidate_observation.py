"""Real local Git object tests for broker candidate scope; no remote effects."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from integrations.chatgpt.scoped_broker import Denied, observe_git_candidate
from integrations.antigravity.tests.test_factory_core import make_valid_packet


class CandidateObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo=Path(self.tmp.name)
        self.git("init","-q")
        self.git("config","user.name","Fixture")
        self.git("config","user.email","fixture@localhost")
        (self.repo/"src").mkdir()
        (self.repo/"src"/"file.py").write_text("x = 1\n")
        (self.repo/"README.md").write_text("protected\n")
        self.git("add",".")
        self.git("commit","-qm","base")
        self.base=self.git("rev-parse","HEAD")
        self.packet=make_valid_packet("OBSERVED-CANDIDATE")
        self.packet.update(base_sha=self.base,owned_paths=["src/"])

    def git(self,*args):
        return subprocess.check_output(["git",*args],cwd=self.repo).decode().strip()

    def candidate(self,hidden=False):
        (self.repo/"src"/"file.py").write_text("x = 2\n")
        if hidden:
            (self.repo/"README.md").write_text("unexpected\n")
        self.git("add",".")
        self.git("commit","-qm","candidate")
        return self.git("rev-parse","HEAD"),self.git("rev-parse","HEAD^{tree}")

    def test_actual_exact_diff(self):
        sha,tree=self.candidate()
        self.assertEqual(observe_git_candidate(self.repo,self.packet,self.base,sha,tree,
                         ["src/file.py"])["paths"],["src/file.py"])

    def test_omitted_protected_path_denied(self):
        sha,tree=self.candidate(hidden=True)
        with self.assertRaises(ValueError):
            observe_git_candidate(self.repo,self.packet,self.base,sha,tree,["src/file.py"])

    def test_forged_declared_paths_and_tree_denied(self):
        sha,tree=self.candidate()
        with self.assertRaisesRegex(Denied,"CANDIDATE_DIFF_SCOPE_DRIFT"):
            observe_git_candidate(self.repo,self.packet,self.base,sha,tree,["src/other.py"])
        with self.assertRaisesRegex(Denied,"CANDIDATE_TREE_DRIFT"):
            observe_git_candidate(self.repo,self.packet,self.base,sha,"f"*40,["src/file.py"])

    def test_non_direct_parent_denied(self):
        sha,tree=self.candidate()
        self.git("commit","--allow-empty","-qm","extra")
        with self.assertRaisesRegex(Denied,"CANDIDATE_PARENT_DRIFT"):
            observe_git_candidate(self.repo,self.packet,self.base,self.git("rev-parse","HEAD"),
                                  tree,["src/file.py"])


if __name__=="__main__":
    unittest.main()
