"""Tests for conflict detection via sequential integration-merge (fan-out build §3.3).

Faithful to the design: merge worker branches one at a time in merge_order onto a
disposable integration branch; a conflict is detected on the *cumulative* tree
(two branches can be clean vs base yet conflict with each other), aborted, and
reported. Driven against a throwaway git fixture (never a real repo/remote), per
the Script Testing Standard; skipped if git is absent.

Run: python3 autonomous-workflows/tests/test_integrate.py
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # autonomous-workflows/ on path
import integrate  # noqa: E402


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


@unittest.skipUnless(shutil.which("git"), "git not available")
class IntegrationMergeTest(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="cw-integ-")
        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "t")
        (Path(self.repo) / "A.txt").write_text("a1\na2\na3\n")
        (Path(self.repo) / "B.txt").write_text("b1\nb2\nb3\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-m", "base")
        # b1 edits A line 2
        _git(self.repo, "checkout", "-b", "b1", "main")
        (Path(self.repo) / "A.txt").write_text("a1\nA2-from-b1\na3\n")
        _git(self.repo, "commit", "-am", "b1 edits A")
        # b2 edits B (disjoint from b1)
        _git(self.repo, "checkout", "-b", "b2", "main")
        (Path(self.repo) / "B.txt").write_text("b1\nB2-from-b2\nb3\n")
        _git(self.repo, "commit", "-am", "b2 edits B")
        # b3 edits A line 2 differently (conflicts with b1)
        _git(self.repo, "checkout", "-b", "b3", "main")
        (Path(self.repo) / "A.txt").write_text("a1\nA2-from-b3\na3\n")
        _git(self.repo, "commit", "-am", "b3 edits A")
        _git(self.repo, "checkout", "main")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_disjoint_branches_merge_clean(self):
        r = integrate.integration_merge(self.repo, "main", ["b1", "b2"])
        self.assertFalse(r["conflict"])
        self.assertEqual(r["merged"], ["b1", "b2"])
        self.assertIsNone(r["conflicting_branch"])

    def test_conflict_detected_and_aborted(self):
        r = integrate.integration_merge(self.repo, "main", ["b1", "b3"])
        self.assertTrue(r["conflict"])
        self.assertEqual(r["conflicting_branch"], "b3")
        self.assertEqual(r["merged"], ["b1"])  # b1 merged, b3 aborted
        # the merge was cleanly aborted — no unresolved (UU) entries left behind
        self.assertNotIn("UU", _git(self.repo, "status", "--porcelain").stdout)

    def test_conflict_is_order_dependent(self):
        # same two branches, opposite order -> the *other* one is the conflicting merge
        r = integrate.integration_merge(self.repo, "main", ["b3", "b1"])
        self.assertTrue(r["conflict"])
        self.assertEqual(r["conflicting_branch"], "b1")
        self.assertEqual(r["merged"], ["b3"])


class RunCheckTest(unittest.TestCase):
    """Merged-tree QA runs the project's checks on the integration branch."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cw-qa-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_reports_pass_and_fail(self):
        self.assertTrue(integrate.run_check(self.dir, ["sh", "-c", "exit 0"])["ok"])
        self.assertFalse(integrate.run_check(self.dir, ["sh", "-c", "exit 1"])["ok"])


if __name__ == "__main__":
    unittest.main()
