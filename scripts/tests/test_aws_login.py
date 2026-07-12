"""End-to-end tests for scripts/aws-login.sh.

Drives the script against a stubbed `aws` CLI on PATH (no real AWS, no browser).
The stub is state-file backed: `sts get-caller-identity` fails until an
`sso login` has "run" (which touches the state file), so the expired -> login
-> re-verify path is exercised deterministically.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import sys
import stat
import subprocess
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import script, TempRepoCase  # noqa: E402

SCRIPT = script("aws-login.sh")

# Stub `aws`: valid identity only once the state file exists; `sso login`
# creates it. Any other invocation is an error so unexpected calls surface.
FAKE_AWS = """#!/usr/bin/env bash
state="$FAKE_AWS_STATE"
case "$1 $2" in
  "sts get-caller-identity")
    if [[ -f "$state" ]]; then
      echo "123456789012  arn:aws:sts::123456789012:assumed-role/Admin/tester"
      exit 0
    fi
    echo "The SSO session ... has expired" >&2
    exit 255 ;;
  "sso login")
    : > "$state"
    echo "logged in" ;;
  *)
    echo "unexpected aws call: $*" >&2; exit 3 ;;
esac
"""


class AwsLogin(TempRepoCase):
    def setUp(self):
        super().setUp()
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir)
        fake = os.path.join(bindir, "aws")
        with open(fake, "w") as fh:
            fh.write(FAKE_AWS)
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        self.bindir = bindir
        self.state = os.path.join(self.tmp, "aws-state")  # absent => creds expired

    def write_env(self, body, sub="session"):
        d = os.path.join(self.tmp, sub)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, ".env"), "w") as fh:
            fh.write(body)
        return d

    def login(self, args, cwd, valid=False):
        if valid and not os.path.exists(self.state):
            open(self.state, "w").close()   # pre-authenticated
        env = {
            **os.environ,
            "PATH": self.bindir + os.pathsep + os.environ["PATH"],
            "FAKE_AWS_STATE": self.state,
        }
        return subprocess.run(
            [SCRIPT, *args], cwd=cwd, env=env,
            capture_output=True, text=True,
        )

    DEFAULT_ENV = (
        "AWS_PROFILE=cw-test\n"
        "AWS_DEFAULT_REGION=us-east-1\n"
        "AWS_ALLOWED_PROFILES=cw-test,cw-partner\n"
        "CLAUDE_CODE_DONT_INHERIT_ENV=true\n"
    )

    def test_help_needs_no_aws(self):
        r = subprocess.run([SCRIPT, "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("aws-login.sh", r.stdout)

    def test_list_resolves_from_env(self):
        d = self.write_env(self.DEFAULT_ENV)
        r = self.login(["--list"], d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("profile:          cw-test", r.stderr)
        self.assertIn("region:           us-east-1", r.stderr)
        self.assertIn("cw-test,cw-partner", r.stderr)

    def test_valid_creds_skip_login(self):
        d = self.write_env(self.DEFAULT_ENV)
        r = self.login([], d, valid=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("credentials valid", r.stderr)
        self.assertNotIn("running 'aws sso login'", r.stderr)

    def test_expired_triggers_login_then_verifies(self):
        d = self.write_env(self.DEFAULT_ENV)
        r = self.login([], d)                       # state absent => expired
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("running 'aws sso login'", r.stderr)
        self.assertIn("authenticated", r.stderr)
        self.assertTrue(os.path.exists(self.state))  # login ran

    def test_refuses_disallowed_profile(self):
        d = self.write_env(self.DEFAULT_ENV)
        r = self.login(["cw-prod"], d, valid=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not in AWS_ALLOWED_PROFILES", r.stderr)

    def test_arg_profile_overrides_env(self):
        d = self.write_env(self.DEFAULT_ENV)
        r = self.login(["cw-partner", "--list"], d)
        self.assertIn("profile:          cw-partner", r.stderr)

    def test_all_requires_allowlist(self):
        d = self.write_env("AWS_PROFILE=cw-test\nAWS_DEFAULT_REGION=us-east-1\n")
        r = self.login(["--all"], d, valid=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--all needs AWS_ALLOWED_PROFILES", r.stderr)

    def test_all_iterates_allowed_profiles(self):
        d = self.write_env(self.DEFAULT_ENV)
        r = self.login(["--all"], d, valid=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cw-test: credentials valid", r.stderr)
        self.assertIn("cw-partner: credentials valid", r.stderr)

    def test_walks_up_to_find_env(self):
        d = self.write_env(self.DEFAULT_ENV)
        nested = os.path.join(d, "a", "b")
        os.makedirs(nested)
        r = self.login(["--list"], nested)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("profile:          cw-test", r.stderr)


if __name__ == "__main__":
    unittest.main()
