"""Package source-selection regression; no installation or provider invocation."""
import subprocess
import unittest

from integrations.chatgpt.package import (
    SOURCE, TREE, VERSION, CONVERGED_BASE, CONVERGED_VERSION, select_package_source,
)


class PackageSourceTests(unittest.TestCase):
    def setUp(self):
        self.candidate = "a" * 40
        self.tree = "b" * 40
        self.head = self.candidate
        self.dirty = b""
        self.diff = b"integrations/chatgpt/README.md\n"
        self.ancestors = {SOURCE, CONVERGED_BASE}
        self.calls = []

    def git(self, *args):
        self.calls.append(args)
        if args == ("rev-parse", SOURCE + "^{tree}"):
            return TREE.encode()
        if args == ("rev-parse", self.candidate + "^{commit}"):
            return self.candidate.encode()
        if args == ("rev-parse", self.candidate + "^{tree}"):
            return self.tree.encode()
        if args == ("rev-parse", "HEAD"):
            return self.head.encode()
        if args == ("status", "--porcelain"):
            return self.dirty
        if args == ("diff", "--name-only", SOURCE, self.candidate):
            return self.diff
        if args[:2] == ("merge-base", "--is-ancestor"):
            if args[2] not in self.ancestors:
                raise subprocess.CalledProcessError(1, args)
            return b""
        raise AssertionError(args)

    def test_historical_policy_preserved(self):
        self.assertEqual(select_package_source(self.git, self.candidate), (SOURCE, TREE, VERSION))
        self.diff = b"integrations/antigravity/factory/authority.py\n"
        with self.assertRaisesRegex(SystemExit, "inherited source modified"):
            select_package_source(self.git, self.candidate)

    def test_convergence_requires_exact_tree_and_both_ancestors(self):
        self.diff = b"integrations/antigravity/factory/authority.py\n"
        self.assertEqual(select_package_source(self.git, self.candidate, self.tree),
                         (self.candidate, self.tree, CONVERGED_VERSION))
        self.assertIn(("merge-base", "--is-ancestor", CONVERGED_BASE, self.candidate), self.calls)
        self.assertIn(("merge-base", "--is-ancestor", SOURCE, self.candidate), self.calls)
        with self.assertRaisesRegex(SystemExit, "tree mismatch"):
            select_package_source(self.git, self.candidate, "c" * 40)
        self.ancestors.remove(CONVERGED_BASE)
        with self.assertRaises(subprocess.CalledProcessError):
            select_package_source(self.git, self.candidate, self.tree)

    def test_dirty_moved_or_symbolic_source_rejected(self):
        with self.assertRaises(SystemExit):
            select_package_source(self.git, "HEAD", self.tree)
        self.head = "c" * 40
        with self.assertRaisesRegex(SystemExit, "clean exact"):
            select_package_source(self.git, self.candidate, self.tree)
        self.head = self.candidate
        self.dirty = b" M tracked\n"
        with self.assertRaisesRegex(SystemExit, "clean exact"):
            select_package_source(self.git, self.candidate, self.tree)


if __name__ == "__main__":
    unittest.main()
