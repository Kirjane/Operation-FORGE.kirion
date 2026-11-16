import importlib.util
import pathlib
import tempfile
import unittest
import zipfile

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "build_vault.py"
spec = importlib.util.spec_from_file_location("forge_obsidian_vault", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ObsidianVaultTests(unittest.TestCase):
    def test_sha_pins(self):
        self.assertTrue(mod.SHA.fullmatch(mod.ACCEPTED))
        self.assertTrue(mod.SHA.fullmatch(mod.CANDIDATE))
        self.assertFalse(mod.SHA.fullmatch("latest"))

    def test_blob_sha1(self):
        self.assertEqual(mod.blob_id(b"hello\n"),
                         "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_frontmatter_contract(self):
        good = ('---\nid: "forge.sample"\nsource_repo: "' +
                mod.REPOSITORY + '"\nsource_ref: "' + mod.CANDIDATE +
                '"\nsource_path: "some/SKILL.md"\nsource_status: "CANDIDATE"\n---\n')
        self.assertEqual(mod.fields(good)["source_status"], "CANDIDATE")
        with self.assertRaises(ValueError):
            mod.fields(good.replace('source_path: "some/SKILL.md"\n', ""))

    def test_zip_roundtrip_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "KIRION-FORGE-VAULT"
            root.mkdir()
            file = root / "Example.md"
            file.write_text("sample\n")
            notes = {"Example": (file, "sample\n", {"id": "forge.sample"})}
            a = root.parent / "one.zip"
            b = root.parent / "two.zip"
            mod.make_zip(notes, "{}\n", a)
            mod.make_zip(notes, "{}\n", b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with zipfile.ZipFile(a) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(len(archive.namelist()), 3)

if __name__ == "__main__":
    unittest.main()
