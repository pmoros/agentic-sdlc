"""End-to-end tests for scripts/session-log.sh.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, script, make_work_sessions_repo, TempRepoCase  # noqa: E402

SCRIPT = script("session-log.sh")
SID = "ADH-selftest-log"
TS_RE = r"- \d{4}-\d{2}-\d{2} \d{2}:\d{2} "


def make_session(ws, sid=SID):
    sdir = os.path.join(ws, "sessions", sid)
    os.makedirs(sdir)
    with open(os.path.join(sdir, "WORKLOG.md"), "w") as fh:
        fh.write("# Worklog\n")
    with open(os.path.join(sdir, "CONTEXT.md"), "w") as fh:
        fh.write("# Context\n\n## Activity log\n")
    return sdir


class SessionLog(TempRepoCase):
    def setUp(self):
        super().setUp()
        self.ws = make_work_sessions_repo(self.tmp)
        self.sdir = make_session(self.ws)

    def log(self, *args, check=True):
        return run([SCRIPT, *args, "--work-sessions-repo", self.ws], check=check)

    def read(self, name):
        return open(os.path.join(self.sdir, name)).read()

    def test_default_writes_both_with_timestamp(self):
        r = self.log(SID, "opened PR #123")
        self.assertEqual(r.returncode, 0, r.stderr)
        for name in ("WORKLOG.md", "CONTEXT.md"):
            body = self.read(name)
            self.assertRegex(body, TS_RE + re.escape("opened PR #123"))

    def test_to_worklog_only(self):
        self.log(SID, "worklog only", "--to", "worklog")
        self.assertIn("worklog only", self.read("WORKLOG.md"))
        self.assertNotIn("worklog only", self.read("CONTEXT.md"))

    def test_to_context_only(self):
        self.log(SID, "context only", "--to", "context")
        self.assertIn("context only", self.read("CONTEXT.md"))
        self.assertNotIn("context only", self.read("WORKLOG.md"))

    def test_appends_do_not_clobber(self):
        self.log(SID, "first")
        self.log(SID, "second")
        wl = self.read("WORKLOG.md")
        self.assertIn("first", wl)
        self.assertIn("second", wl)
        self.assertTrue(wl.index("first") < wl.index("second"))  # append order

    def test_missing_session_errors(self):
        r = self.log("ADH-nope", "x", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("session folder not found", r.stderr)

    def test_bad_target_errors(self):
        r = self.log(SID, "x", "--to", "everywhere", check=False)
        self.assertNotEqual(r.returncode, 0)

    def test_needs_message(self):
        r = self.log(SID, check=False)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
