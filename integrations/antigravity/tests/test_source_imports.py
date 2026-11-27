import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.verify_source_imports import MANIFEST, verify


class SourceImportsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Source Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / "base.txt").write_text("unchanged\n", encoding="utf-8")
        self.git("add", "base.txt")
        self.git("commit", "-qm", "baseline")
        self.baseline = self.git("rev-parse", "HEAD")
        (self.root / "donor.txt").write_text("retained\n", encoding="utf-8")
        self.git("add", "donor.txt")
        self.git("commit", "-qm", "donor")
        self.donor = self.git("rev-parse", "HEAD")
        self.blob = self.git("rev-parse", "HEAD:donor.txt")
        self.git("checkout", "--detach", "-q", self.baseline)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args],
                                       stderr=subprocess.PIPE).decode().strip()

    def candidate(self, *, altered=False, extra=False, wrong_donor=False, changed_base=False):
        (self.root / "donor.txt").write_text("altered\n" if altered else "retained\n", encoding="utf-8")
        if extra:
            (self.root / "untracked-import.txt").write_text("extra\n", encoding="utf-8")
        if changed_base:
            (self.root / "base.txt").write_text("changed\n", encoding="utf-8")
        manifest = self.root / MANIFEST
        manifest.parent.mkdir()
        manifest.write_text(json.dumps({
            "format": "forge-source-import/v1",
            "baseline": self.baseline,
            "imports": [{"path": "donor.txt", "commit": self.baseline if wrong_donor else self.donor,
                         "mode": "100644", "blob": self.blob, "size": 9}],
        }), encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "import")
        return self.git("rev-parse", "HEAD")

    def test_exact_import_without_operator_archive(self):
        result = verify(self.root, self.candidate())
        self.assertEqual(result["status"], "SOURCE_IMPORT_VERIFIED")
        self.assertEqual(result["imported_leaves"], 1)
        self.assertEqual(result["preserved_leaves"], 1)
        self.assertEqual(result["runtime"], "NOT_RUN")
        self.assertFalse(result["promotion_authorized"])

    def test_changed_import_denied(self):
        with self.assertRaisesRegex(ValueError, "DONOR_OR_IMPORT_BLOB_MISMATCH"):
            verify(self.root, self.candidate(altered=True))

    def test_extra_path_denied(self):
        with self.assertRaisesRegex(ValueError, "IMPORT_PATH_SET_MISMATCH"):
            verify(self.root, self.candidate(extra=True))

    def test_wrong_donor_denied(self):
        with self.assertRaisesRegex(ValueError, "DONOR_OR_IMPORT_BLOB_MISMATCH"):
            verify(self.root, self.candidate(wrong_donor=True))

    def test_changed_baseline_denied(self):
        with self.assertRaisesRegex(ValueError, "BASELINE_LEAF_CHANGED"):
            verify(self.root, self.candidate(changed_base=True))
