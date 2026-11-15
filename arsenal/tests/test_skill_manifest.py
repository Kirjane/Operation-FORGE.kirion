"""Deterministic integrity checks for the proposed Kirion Skill Arsenal.

No YAML dependency: the canonical skill files use a small top-level key: value
frontmatter subset, and this test checks only its required name/description.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".agents" / "skills"
ADAPTERS = ROOT / "arsenal" / "adapters"


# Match concrete repository-local skill references, including the entire leaf
# path, rather than accepting an existing skill directory as proof of the leaf.
CANONICAL_SKILL_REF = re.compile(
    r"(?<![\w/])\.agents/skills/(?P<name>kirion-[a-z0-9-]+)"
    r"(?P<suffix>(?:/[A-Za-z0-9._-]+)*)"
)


def invalid_canonical_skill_references(content):
    """Return references that are neither real skill directories nor SKILL.md."""
    invalid = []
    for match in CANONICAL_SKILL_REF.finditer(content):
        name, suffix = match.group("name", "suffix")
        canonical = SKILLS / name / "SKILL.md"
        if not canonical.is_file() or suffix not in ("", "/SKILL.md"):
            invalid.append(match.group(0))
    return invalid



class SkillManifestContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "arsenal" / "manifest.json").read_text(encoding="utf-8"))
        cls.skill_files = sorted(SKILLS.glob("*/SKILL.md"))

    def test_manifest_count_matches_skill_directories(self):
        directories = {path.name for path in SKILLS.iterdir() if path.is_dir()}
        names = {path.parent.name for path in self.skill_files}
        self.assertEqual(directories, names, "each skill directory requires a SKILL.md")
        self.assertIsInstance(self.manifest["skills"], int)
        self.assertEqual(self.manifest["skills"], len(self.skill_files))
        self.assertEqual(len(names), len(self.skill_files))

    def test_required_frontmatter_matches_directory_name(self):
        seen = set()
        for path in self.skill_files:
            with self.subTest(skill=path.parent.name):
                lines = path.read_text(encoding="utf-8").splitlines()
                self.assertTrue(lines and lines[0] == "---", "missing opening frontmatter fence")
                self.assertIn("---", lines[1:], "missing closing frontmatter fence")
                closing = lines.index("---", 1)
                fields = {}
                for line in lines[1:closing]:
                    if not line.strip():
                        continue
                    match = re.fullmatch(r"([a-z][a-z0-9_-]*):\s*(.+)", line)
                    self.assertIsNotNone(match, f"invalid frontmatter: {line!r}")
                    key, value = match.groups()
                    self.assertNotIn(key, fields, f"duplicate frontmatter key: {key}")
                    value = value.strip()
                    if len(value) >= 2 and value[0] in "'\"" and value[-1] == value[0]:
                        value = value[1:-1]
                    self.assertTrue(value.strip(), f"empty {key}")
                    fields[key] = value
                self.assertIn("name", fields)
                self.assertIn("description", fields)
                self.assertEqual(fields["name"], path.parent.name)
                self.assertRegex(fields["name"], r"^kirion-[a-z0-9-]+$")
                self.assertNotIn(fields["name"], seen)
                seen.add(fields["name"])

    def test_manifest_entrypoints_are_real_skills(self):
        for field in ("default", "dispatcher"):
            name = self.manifest[field]
            self.assertTrue((SKILLS / name / "SKILL.md").is_file(), f"{field}: {name}")
        generator = ROOT / self.manifest["generator"]
        self.assertTrue(generator.is_file(), f"missing generator: {generator}")

    def test_multihost_adapter_skill_references_resolve(self):
        relative_adapters = (
            "chatgpt/PROJECT_INSTRUCTIONS.fragment.md",
            "chatgpt/WORKER_START.md",
            "codex/AGENTS.fragment.md",
            "antigravity/GEMINI.fragment.md",
        )
        for relative in relative_adapters:
            with self.subTest(adapter=relative):
                path = ADAPTERS / relative
                self.assertTrue(path.is_file(), f"missing host adapter: {relative}")
                content = path.read_text(encoding="utf-8")
                self.assertIn(".agents/skills", content)
                referenced = set(re.findall(r"\bkirion-[a-z0-9-]+\b", content))
                self.assertTrue({"kirion-core", "kirion-dispatch"}.issubset(referenced))
                for name in referenced:
                    self.assertTrue(
                        (SKILLS / name / "SKILL.md").is_file(),
                        f"{relative} references missing skill: {name}",
                    )
                invalid = invalid_canonical_skill_references(content)
                self.assertFalse(
                    invalid, f"{relative} contains invalid canonical path(s): {invalid}"
                )


    def test_rejects_missing_skill_leaf_and_typo_paths(self):
        canonical = ".agents/skills/kirion-core/SKILL.md"
        self.assertEqual(invalid_canonical_skill_references(canonical), [])
        for broken in (
            ".agents/skills/kirion-core/NOT-SKILL.md",
            ".agents/skills/kirion-core/SKILL.md.backup",
            ".agents/skills/kirion-nonexistent/SKILL.md",
        ):
            with self.subTest(broken=broken):
                self.assertEqual(invalid_canonical_skill_references(broken), [broken])


if __name__ == "__main__":
    unittest.main()
