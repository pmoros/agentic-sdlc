"""End-to-end tests for scripts/create-worktree.sh against throwaway repos.

No AWS, no node_modules (so --deps auto resolves to none), no tmux.
Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, git, script, make_remote_repo, TempRepoCase  # noqa: E402

SCRIPT = script("create-worktree.sh")


def cw(*args, check=True):
    return run([SCRIPT, *args], check=check)


def head(path):
    return run(["git", "-C", str(path), "rev-parse", "HEAD"]).stdout.strip()


def cur_branch(path):
    return run(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


class CreateWorktree(TempRepoCase):
    def test_help_exits_zero(self):
        self.assertEqual(cw("--help").returncode, 0)

    def test_requires_dest_and_mode(self):
        src = make_remote_repo(self.tmp, "src")
        dest = os.path.join(self.tmp, "wt")
        self.assertNotEqual(cw(src, "--branch", "x", check=False).returncode, 0)   # no --dest
        self.assertNotEqual(cw(src, "--dest", dest, check=False).returncode, 0)    # no mode
        # --branch + --detach are mutually exclusive
        self.assertNotEqual(
            cw(src, "--dest", dest, "--branch", "x", "--detach", check=False).returncode, 0)

    def test_detach_worktree(self):
        src = make_remote_repo(self.tmp, "src")
        dest = os.path.join(self.tmp, "wt-detached")
        self.assertEqual(cw(src, "--dest", dest, "--detach").returncode, 0)
        self.assertTrue(os.path.isdir(dest))
        self.assertEqual(cur_branch(dest), "HEAD")     # detached
        self.assertEqual(head(dest), head(src))

    def test_branch_worktree(self):
        src = make_remote_repo(self.tmp, "src")
        dest = os.path.join(self.tmp, "wt-branch")
        self.assertEqual(cw(src, "--dest", dest, "--branch", "feat/test-x").returncode, 0)
        self.assertEqual(cur_branch(dest), "feat/test-x")

    def test_refresh_fast_forwards_detached(self):
        src = make_remote_repo(self.tmp, "src")
        dest = os.path.join(self.tmp, "wt-detached")
        cw(src, "--dest", dest, "--detach")
        before = head(dest)

        origin_url = run(["git", "-C", src, "remote", "get-url", "origin"]).stdout.strip()
        other = os.path.join(self.tmp, "other")
        run(["git", "clone", origin_url, other])
        with open(os.path.join(other, "new.txt"), "w") as fh:
            fh.write("x")
        git(["add", "-A"], other)
        git(["commit", "-m", "second"], other)
        git(["push", "origin", "main"], other)

        self.assertEqual(cw("--refresh", dest).returncode, 0)
        self.assertNotEqual(head(dest), before)        # advanced

    def test_sync_refuses_dirty_source(self):
        src = make_remote_repo(self.tmp, "src")
        with open(os.path.join(src, "README.md"), "w") as fh:
            fh.write("locally dirtied\n")               # uncommitted change
        dest = os.path.join(self.tmp, "wt")
        r = cw(src, "--dest", dest, "--branch", "x", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("local changes", r.stderr)
        self.assertFalse(os.path.exists(dest))

    def test_no_sync_skips_the_dirty_guard(self):
        src = make_remote_repo(self.tmp, "src")
        with open(os.path.join(src, "README.md"), "w") as fh:
            fh.write("locally dirtied\n")
        dest = os.path.join(self.tmp, "wt")
        r = cw(src, "--dest", dest, "--detach", "--no-sync", check=False)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(os.path.isdir(dest))


if __name__ == "__main__":
    unittest.main()
