"""Local artifact custody regressions; not restricted-holdout qualification."""
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
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

    @unittest.skipUnless(os.name == "posix", "POSIX publication lock")
    def test_recovers_exact_interrupted_link_without_overwrite(self):
        self.target.parent.mkdir()
        stage=self.target.parent/(".artifact-"+self.digest+".pending")
        stage.write_bytes(self.raw)
        os.link(stage,self.target)
        inode=self.target.stat().st_ino
        self.runner._store_artifact(self.raw.decode())
        self.assertFalse(stage.exists())
        self.assertEqual(self.target.stat().st_ino,inode)
        self.assertEqual(self.target.stat().st_nlink,1)

    @unittest.skipUnless(os.name == "posix", "POSIX publication lock")
    def test_concurrent_publishers_share_exact_object(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(self.runner._store_artifact,[self.raw.decode()]*16))
        self.assertTrue(all(row==results[0] for row in results))
        self.assertEqual(self.target.stat().st_nlink,1)

    @unittest.skipUnless(os.name == "posix", "POSIX publication lock")
    def test_unknown_link_preserved_and_denied(self):
        self.target.parent.mkdir()
        stage=self.target.parent/(".artifact-"+self.digest+".pending")
        stage.write_bytes(self.raw)
        other=self.target.parent/"other"
        os.link(stage,other)
        with self.assertRaises(AuthorityError):
            self.runner._store_artifact(self.raw.decode())
        self.assertTrue(stage.exists())
        self.assertTrue(other.exists())
        self.assertFalse(self.target.exists())

    def test_default_versions_do_not_invent_toolchain(self):
        self.assertEqual(self.runner.environment_versions, {"forge_python": platform.python_version()})
        self.assertEqual(TrustedEvidenceRunner(self.root, {}).environment_versions, {})


if __name__ == "__main__":
    unittest.main()
