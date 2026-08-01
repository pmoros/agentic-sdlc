"""Tests for the autonomous-execution authorization classifier (Phase 1).

Makes the allow/gate boundary from docs/autonomous-execution.instructions.md
executable: every action a worker might take resolves to "allowed" (unattended)
or "gated" (route to a human via any channel). Fail-closed by default.

Run: python3 autonomous-workflows/tests/test_policy.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # autonomous-workflows/ on path
import policy  # noqa: E402

ROOT = "/wt/session"  # the worker's session root (its worktrees + tracking files live under here)


def clf(**action):
    return policy.classify_action(action, ROOT)


class AllowedUnattendedTest(unittest.TestCase):
    def test_read_is_allowed(self):
        self.assertEqual(clf(kind="read", path="/anywhere/at/all"), policy.ALLOWED)

    def test_local_test_build_lint_allowed(self):
        for k in ("test", "build", "lint"):
            self.assertEqual(clf(kind=k), policy.ALLOWED, k)

    def test_edit_within_session_root_allowed(self):
        self.assertEqual(clf(kind="edit", path="/wt/session/worktrees/code/app.py"), policy.ALLOWED)

    def test_write_session_tracking_file_allowed(self):
        self.assertEqual(clf(kind="write", path="/wt/session/CONTEXT.md"), policy.ALLOWED)

    def test_local_git_ops_allowed(self):
        for sub in ("add", "commit", "status", "diff", "branch", "checkout", "worktree", "stash"):
            self.assertEqual(clf(kind="git", subcommand=sub), policy.ALLOWED, sub)


class GatedTest(unittest.TestCase):
    def test_edit_outside_session_root_gated(self):
        self.assertEqual(clf(kind="edit", path="/etc/hosts"), policy.GATED)

    def test_edit_path_traversal_escape_gated(self):
        # normpath collapses .. — must not let it escape the session root
        self.assertEqual(clf(kind="edit", path="/wt/session/../other/secret"), policy.GATED)

    def test_git_push_gated(self):
        self.assertEqual(clf(kind="git", subcommand="push"), policy.GATED)

    def test_unknown_git_subcommand_gated(self):
        self.assertEqual(clf(kind="git", subcommand="filter-branch"), policy.GATED)

    def test_external_write_gated(self):
        self.assertEqual(clf(kind="external_write", target="jira"), policy.GATED)

    def test_aws_always_gated(self):
        self.assertEqual(clf(kind="aws", subcommand="s3 cp"), policy.GATED)

    def test_pr_and_deploy_gated(self):
        self.assertEqual(clf(kind="pr"), policy.GATED)
        self.assertEqual(clf(kind="deploy"), policy.GATED)


class OverrideAndFailClosedTest(unittest.TestCase):
    def test_destructive_overrides_even_if_local(self):
        # a delete inside the worktree is still destructive -> gated
        self.assertEqual(clf(kind="edit", path="/wt/session/x", destructive=True), policy.GATED)

    def test_unknown_kind_fails_closed(self):
        self.assertEqual(clf(kind="teleport"), policy.GATED)

    def test_missing_kind_fails_closed(self):
        self.assertEqual(policy.classify_action({}, ROOT), policy.GATED)


class BashGatingTest(unittest.TestCase):
    """F1: a bash/shell command that does a gated thing (push/PR/cloud/destructive/
    network) must classify as GATED even though it's 'just bash' — so a gated action
    laundered through Bash can't score zero guardrail violations."""

    def test_gated_bash_commands(self):
        for cmd in ("git push origin main", "gh pr create -t x", "aws s3 cp a b",
                    "gcloud compute instances list", "az vm list", "sudo rm -rf /x",
                    "npm publish", "docker push repo/img", "curl https://evil.example",
                    "rm -rf build"):
            self.assertEqual(policy.classify_action({"kind": "bash", "command": cmd}, ROOT),
                             policy.GATED, cmd)

    def test_local_bash_commands_allowed(self):
        for cmd in ("pytest -q", "npm test", "git status", "git commit -m 'x'",
                    "ls -la", "python3 run.py", "git diff"):
            self.assertEqual(policy.classify_action({"kind": "bash", "command": cmd}, ROOT),
                             policy.ALLOWED, cmd)

    def test_opaque_bash_without_command_fails_closed(self):
        self.assertEqual(policy.classify_action({"kind": "bash"}, ROOT), policy.GATED)


if __name__ == "__main__":
    unittest.main()
