"""Harness tests for run-worker.sh's subscription-lane seam (ADH-003 D5).

The security-critical surface of the pivot: on the subscription lane the
`claude` invocation must run with the COMPLETE documented auth-precedence chain
scrubbed (a credential lingering in the caller's shell can never silently flip
the lane back to API billing), the launch must abort when `apiKeyHelper` is
configured (env -u cannot scrub a setting), and the CLI version pre-flight must
use a numeric compare (a string compare passes "2.1.3" > "2.1.211").

These drive the real script with a fake `claude` on PATH that records the env it
was invoked with — so we assert against the actual invocation env, per vector.
No real `claude`, no gateway, no spend. Run: python3 -m pytest tests/test_run_worker.py
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
RUN_WORKER = SCRIPTS / "run-worker.sh"

# The complete documented auth-precedence chain the subscription lane scrubs (D5).
SCRUB_VECTORS = [
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY", "CLAUDE_CODE_USE_MANTLE",
]

FAKE_CLAUDE = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then echo "${FAKE_CLAUDE_VERSION:-2.1.212} (Claude Code)"; exit 0; fi
# A `-p` invocation: record the environment we were called with, then emit one
# minimal stream-json result event so the script's trace filter has input.
env > "$FAKE_CLAUDE_ENV_DUMP"
echo '{"type":"result","is_error":false,"num_turns":1,"total_cost_usd":0.02,"session_id":"sess-test"}'
exit 0
"""


class RunWorkerSubscriptionTest(unittest.TestCase):
    def _setup(self, tmp, **over):
        tmp = Path(tmp)
        bindir = tmp / "bin"
        bindir.mkdir()
        fake = bindir / "claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(0o755)
        home = tmp / "home"
        (home / ".claude").mkdir(parents=True)
        env = {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "HOME": str(home),
            "LANE": "subscription",
            "RUN_RECORDS_DIR": str(tmp / "rr"),
            "FAKE_CLAUDE_ENV_DUMP": str(tmp / "claude_env.txt"),
        }
        env.update(over)
        return env, home

    def _run(self, env, tmp):
        return subprocess.run(
            ["bash", str(RUN_WORKER), "t1", "hello world"],
            env=env, cwd=str(tmp), capture_output=True, text=True)

    def test_each_auth_vector_is_scrubbed(self):
        for vec in SCRUB_VECTORS:
            with tempfile.TemporaryDirectory() as tmp:
                env, _ = self._setup(tmp)
                env[vec] = "LEAKED-VALUE"
                r = self._run(env, tmp)
                self.assertEqual(r.returncode, 0, f"{vec}: {r.stderr}")
                lines = Path(env["FAKE_CLAUDE_ENV_DUMP"]).read_text().splitlines()
                leaked = [ln for ln in lines if ln.startswith(vec + "=")]
                self.assertEqual(leaked, [], f"{vec} reached the subscription invocation env")

    def test_apikeyhelper_setting_aborts(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, home = self._setup(tmp)
            (home / ".claude" / "settings.json").write_text(json.dumps({"apiKeyHelper": "echo k"}))
            r = self._run(env, tmp)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("apiKeyHelper", r.stderr)

    def test_old_cli_version_aborts(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, _ = self._setup(tmp, FAKE_CLAUDE_VERSION="2.1.3")
            r = self._run(env, tmp)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("2.1.211", r.stderr)

    def test_version_numeric_compare_accepts_212(self):
        # 2.1.212 >= 2.1.211 — a lexical string compare would wrongly reject it.
        with tempfile.TemporaryDirectory() as tmp:
            env, _ = self._setup(tmp, FAKE_CLAUDE_VERSION="2.1.212")
            r = self._run(env, tmp)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_subscription_needs_no_gateway_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, _ = self._setup(tmp)
            r = self._run(env, tmp)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("gateway", r.stderr.lower())

    def test_record_carries_lane_and_cost_basis(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, _ = self._setup(tmp)
            r = self._run(env, tmp)
            self.assertEqual(r.returncode, 0, r.stderr)
            results = list((Path(tmp) / "rr" / "traces").glob("t1-*.result.json"))
            self.assertEqual(len(results), 1, "expected one result record")
            rec = json.loads(results[0].read_text())
            self.assertEqual(rec["lane"], "subscription")
            self.assertEqual(rec["cost_basis"], "estimated")
            self.assertEqual(rec["task_id"], "t1")


if __name__ == "__main__":
    unittest.main()
