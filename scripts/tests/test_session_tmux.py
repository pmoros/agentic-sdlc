"""End-to-end tests for scripts/session-tmux.sh.

`name` needs no tmux. Lifecycle tests need tmux and are skipped without it;
they use a collision-proof session id and always tear the tmux session down,
so the user's real sessions are never touched.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import sys
import tempfile
import shutil
import subprocess
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, has_tmux, script  # noqa: E402

SCRIPT = script("session-tmux.sh")
SID = "zz-selftest-session-tmux"
NAME = f"cw-{SID}"


def sh(*args, check=True):
    return run([SCRIPT, *args], check=check)


class NoTmuxNeeded(unittest.TestCase):
    def test_name_needs_no_tmux(self):
        self.assertEqual(sh("name", SID).stdout.strip(), NAME)

    def test_missing_args_is_usage_error(self):
        self.assertEqual(sh(check=False).returncode, 2)


@unittest.skipUnless(has_tmux(), "tmux not installed")
class Lifecycle(unittest.TestCase):
    def tearDown(self):
        subprocess.run(["tmux", "kill-session", "-t", f"={NAME}"], capture_output=True)

    def test_ensure_then_exists_then_kill(self):
        self.assertNotEqual(sh("exists", SID, check=False).returncode, 0)  # not there yet
        sh("ensure", SID)
        self.assertEqual(sh("exists", SID, check=False).returncode, 0)
        self.assertIn("already exists", sh("ensure", SID).stderr)          # idempotent
        self.assertIn(f"tmux attach -t {NAME}", sh("attach-hint", SID).stderr)
        sh("kill", SID)
        self.assertNotEqual(sh("exists", SID, check=False).returncode, 0)

    def test_kill_when_absent_is_ok(self):
        r = sh("kill", SID)
        self.assertEqual(r.returncode, 0)
        self.assertIn("no tmux session", r.stderr)

    def test_ensure_loads_session_env_into_tmux(self):
        workdir = tempfile.mkdtemp(prefix="cwtmux-env-")
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        with open(os.path.join(workdir, ".env"), "w") as fh:
            fh.write(
                "# comment line, ignored\n"
                "AWS_PROFILE=cw-test\n"
                "AWS_DEFAULT_REGION = us-east-1\n"      # whitespace around key/value trimmed
                "CLAUDE_CODE_DONT_INHERIT_ENV=true\n"
                'AWS_SSO_BROWSER="Google Chrome"\n'     # quotes stripped, inner space kept
            )
        r = sh("ensure", SID, workdir)
        self.assertIn(".env into tmux env", r.stderr)
        shown = subprocess.run(
            ["tmux", "show-environment", "-t", f"={NAME}"],
            capture_output=True, text=True).stdout
        self.assertIn("AWS_PROFILE=cw-test", shown)
        self.assertIn("AWS_DEFAULT_REGION=us-east-1", shown)
        self.assertIn("CLAUDE_CODE_DONT_INHERIT_ENV=true", shown)
        self.assertIn("AWS_SSO_BROWSER=Google Chrome", shown)


if __name__ == "__main__":
    unittest.main()
