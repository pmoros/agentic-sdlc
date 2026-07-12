"""End-to-end tests for scripts/init-session.sh.

Uses a minimal work-sessions repo + a scratch agentic-sdlc repo. tmux linkage
is exercised when tmux is present and always torn down.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import sys
import subprocess
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, has_tmux, script, make_remote_repo, make_work_sessions_repo, TempRepoCase  # noqa: E402

SCRIPT = script("init-session.sh")
SID = "ADH-selftest-init"
TMUX_NAME = f"cw-{SID}"


def _kill_tmux():
    if has_tmux():
        subprocess.run(["tmux", "kill-session", "-t", f"={TMUX_NAME}"], capture_output=True)


class InitSession(TempRepoCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(_kill_tmux)
        self.ws = make_work_sessions_repo(self.tmp)
        self.agentic = make_remote_repo(self.tmp, "agentic")

    def init(self, sid=SID, extra=()):
        return run([
            SCRIPT, sid,
            "--goal", "Self-test of init-session & create-worktree",
            "--ticket", "https://example.test/browse/ADH-1",
            "--scope", "S", "--task-type", "spike",
            "--work-sessions-repo", self.ws,
            "--agentic-sdlc-repo", self.agentic,
            *extra,
        ], check=False)

    def test_creates_folder_registry_worktree_and_tmux(self):
        r = self.init()
        self.assertEqual(r.returncode, 0, r.stderr)

        sdir = os.path.join(self.ws, "sessions", SID)
        self.assertTrue(os.path.isdir(sdir))

        context = open(os.path.join(sdir, "CONTEXT.md")).read()
        self.assertIn("[spike] Self-test of init-session", context)   # overview filled
        self.assertIn("https://example.test/browse/ADH-1", context)   # ticket row filled
        self.assertIn("session initialized", context)                 # activity log line
        self.assertIn(f"tmux: {TMUX_NAME}", context)

        env = open(os.path.join(sdir, ".env")).read()            # session .env generated
        self.assertIn("AWS_PROFILE=cw-test", env)
        self.assertIn("AWS_DEFAULT_REGION=us-east-1", env)
        self.assertIn("AWS_ALLOWED_PROFILES=cw-test,cw-partner", env)
        self.assertIn("CLAUDE_CODE_DONT_INHERIT_ENV=true", env)

        state = open(os.path.join(self.ws, "SESSIONS_STATE.md")).read()
        self.assertIn(SID, state)
        self.assertIn(TMUX_NAME, state)                               # tmux column, not n/a
        self.assertNotIn("| _none yet_ |", state)                     # placeholder replaced

        wt = os.path.join(sdir, "worktrees", "agentic-sdlc")
        self.assertTrue(os.path.isdir(wt))
        branch = run(["git", "-C", wt, "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        self.assertEqual(branch, "HEAD")                              # detached

        if has_tmux():
            self.assertEqual(
                subprocess.run(["tmux", "has-session", "-t", f"={TMUX_NAME}"],
                               capture_output=True).returncode, 0)

    def test_requires_goal(self):
        r = run([SCRIPT, "ADH-x", "--work-sessions-repo", self.ws,
                 "--agentic-sdlc-repo", self.agentic], check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--goal", r.stderr)

    def test_rejects_duplicate_session(self):
        self.assertEqual(self.init().returncode, 0)
        r = self.init()                                               # same id again
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already exists", r.stderr)


if __name__ == "__main__":
    unittest.main()
