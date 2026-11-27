import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.qualify_completion import counts, run_suite, environment, pinned, actual_cases, approved_inventory
from tools.verify_source_imports import verify, APPROVED_IMPORT


class QualificationReceiptTests(unittest.TestCase):
    def test_fixed_count_formats(self):
        self.assertEqual(counts(b"Ran 3 tests in 0.01s\n\nOK\n","unittest"),(3,0))
        self.assertEqual(counts(b"Ran 3 tests in 0.01s\n\nOK (skipped=1)\n","unittest"),(3,1))
        self.assertEqual(counts(b"# tests 5\n# skipped 2\n","tap"),(5,2))
        self.assertEqual(counts(b"Ran 0 tests in 0.01s\nOK\n","unittest"),(0,0))
        self.assertEqual(counts(b"unexpected","unittest"),(None,0))

    def test_success_exit_without_tests_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            env=environment(root)
            receipt=run_suite("empty",[sys.executable,"-c","print('Ran 0 tests in 0.1s')"],
                              "unittest",env,root)
            self.assertEqual(receipt["exit_code"],0)
            self.assertEqual(receipt["status"],"INCOMPLETE")
            self.assertEqual(receipt["tests"],0)

    def test_case_inventory_and_exclusions(self):
        raw=b'Ran 2 tests in 0.1s\nOK\nFORGE_CASE_RESULTS [{"id":"a","status":"PASS"},{"id":"b","status":"PASS"}]\n'
        self.assertEqual(actual_cases(raw,"unittest"),["a","b"])
        self.assertEqual(actual_cases(raw.replace(b'"PASS"',b'"XFAIL"'),"unittest"),[])
        self.assertEqual(actual_cases(b"ok 1 - skipped # TODO later\n","tap"),[])
        self.assertEqual(counts(b"Ran 1 test in 0.1s\nOK (expected failures=1)\n","unittest"),(1,1))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            receipt=run_suite("partial",[sys.executable,"-c","print("+repr(raw.decode())+")"],
                              "unittest",environment(root),root,["a","c"])
            self.assertEqual(receipt["status"],"INCOMPLETE")

    def test_dirty_checkout_rejected(self):
        with patch("tools.qualify_completion.git",side_effect=[b"a"*40,b"b"*40,b"M path"]):
            self.assertFalse(pinned({},"a"*40,"b"*40))

    def test_wrong_import_denied_without_git_access(self):
        with patch("tools.verify_source_imports.git") as git:
            with self.assertRaisesRegex(ValueError,"UNAPPROVED_IMPORT_COMMIT"):
                verify(Path.cwd(),"a"*40)
            git.assert_not_called()

    def test_altered_manifest_denied_before_donor_lookup(self):
        with patch("tools.verify_source_imports.git",return_value=b'{"format":"forge-source-import/v1"}'):
            with self.assertRaisesRegex(ValueError,"UNAPPROVED_IMPORT_MANIFEST"):
                verify(Path.cwd(),APPROVED_IMPORT)


if __name__=="__main__":
    unittest.main()
