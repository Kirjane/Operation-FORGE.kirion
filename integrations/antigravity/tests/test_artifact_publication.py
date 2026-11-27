"""Local artifact custody regressions; not restricted-holdout qualification."""
import hashlib
import platform
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from integrations.antigravity.factory.authority import AuthorityError
from integrations.antigravity.factory.evidence import TrustedEvidenceRunner, read_assurance_artifact


class ArtifactPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runner = TrustedEvidenceRunner(self.root)
        self.raw = b"complete evidence"
        self.digest = hashlib.sha256(self.raw).hexdigest()
        self.target = self.root / self.digest[:2] / (self.digest + ".log")

    def test_publish_failure_does_not_leave_partial_final_name(self):
        with patch("integrations.antigravity.factory.evidence.os.link", side_effect=OSError("injected publication failure")):
            with self.assertRaises(OSError):
                self.runner._store_artifact(self.raw.decode())
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.glob("*.pending")), [])
        path, size, digest = self.runner._store_artifact(self.raw.decode())
        self.assertEqual((path, size, digest), (self.target, len(self.raw), self.digest))
        self.assertEqual(read_assurance_artifact(self.root, {
            "artifact_path": str(path), "artifact_size_bytes": size, "artifact_sha256": digest
        }), self.raw)

    def test_failed_flush_never_publishes(self):
        with patch("integrations.antigravity.factory.evidence.os.fsync", side_effect=OSError("injected flush failure")):
            with self.assertRaises(OSError):
                self.runner._store_artifact(self.raw.decode())
        self.assertFalse(self.target.exists())

    def test_existing_corrupt_object_not_overwritten(self):
        self.target.parent.mkdir()
        self.target.write_bytes(b"wrong")
        with self.assertRaises(AuthorityError):
            self.runner._store_artifact(self.raw.decode())
        self.assertEqual(self.target.read_bytes(), b"wrong")

    def test_existing_exact_object_reused(self):
        first = self.runner._store_artifact(self.raw.decode())
        second = self.runner._store_artifact(self.raw.decode())
        self.assertEqual(first, second)
        self.assertEqual(self.target.stat().st_nlink, 1)

    def test_default_versions_do_not_invent_toolchain(self):
        self.assertEqual(self.runner.environment_versions, {"forge_python": platform.python_version()})
        self.assertEqual(TrustedEvidenceRunner(self.root, {}).environment_versions, {})


if __name__ == "__main__":
    unittest.main()
