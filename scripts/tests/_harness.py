"""Shared helpers for the shell-script tests.

Plain functions + a base TestCase (no pytest fixtures), so the suite runs under
either `pytest scripts` or `python -m unittest discover -s scripts/tests`.

The bash scripts are exercised end-to-end against throwaway git repos built in
a per-test temp dir — no AWS, no network, no touching the real repos or the
user's real tmux sessions.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "HUSKY": "0",
}


def run(args, cwd=None, check=True):
    return subprocess.run(
        [str(a) for a in args],
        cwd=str(cwd) if cwd else None,
        env=GIT_ENV,
        capture_output=True,
        text=True,
        check=check,
    )


def git(args, cwd, check=True):
    return run(["git", *args], cwd=cwd, check=check)


def has_tmux():
    return shutil.which("tmux") is not None


def script(rel):
    return os.path.join(SCRIPTS_DIR, rel)


def make_remote_repo(base, name="src", files=None):
    """Bare-origin-backed git repo on `main` with one commit; returns the
    working-clone path. origin/HEAD is set for the fast default-branch path."""
    root = os.path.join(base, name)
    origin = os.path.join(root, "origin.git")
    work = os.path.join(root, "work")
    os.makedirs(root, exist_ok=True)
    run(["git", "init", "--bare", "-b", "main", origin])
    run(["git", "clone", origin, work], check=False)  # empty-clone warning is fine
    with open(os.path.join(work, "README.md"), "w") as fh:
        fh.write(f"# {name}\n")
    for rel, content in (files or {}).items():
        p = os.path.join(work, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(content)
    git(["add", "-A"], work)
    git(["commit", "-m", "init"], work)
    git(["branch", "-M", "main"], work)
    git(["push", "-u", "origin", "main"], work)
    git(["remote", "set-head", "origin", "main"], work)
    return work


_CONTEXT_TEMPLATE = """# Context

## Overview

<!-- What is this session about, in 2-3 sentences. -->

## Tickets

| Label | Link |
|---|---|
| main | |

## Current state

- **Blocked:** no
- **Description:**

## Activity log
"""

_SESSIONS_STATE = """# Sessions State

| Session ID | Title | Tmux Session | Session Folder | Created | Last Change | Status |
|---|---|---|---|---|---|---|
| _none yet_ | | | | | | |
"""


def make_work_sessions_repo(base):
    """Minimal work-sessions git repo: session-template/ with the
    files init-session.sh copies+rewrites, and a SESSIONS_STATE.md."""
    root = os.path.join(base, "work-sessions")
    tmpl = os.path.join(root, "session-template")
    os.makedirs(os.path.join(tmpl, "worktrees"))
    os.makedirs(os.path.join(tmpl, "deployments"))
    with open(os.path.join(tmpl, "CONTEXT.md"), "w") as fh:
        fh.write(_CONTEXT_TEMPLATE)
    for f in ("PLAN.md", "SPEC.md", "TASKS.md", "WORKLOG.md"):
        with open(os.path.join(tmpl, f), "w") as fh:
            fh.write(f"# {f}\n")
    with open(os.path.join(tmpl, "worktrees", "README.md"), "w") as fh:
        fh.write("# Worktrees\n")
    with open(os.path.join(tmpl, "deployments", "README.md"), "w") as fh:
        fh.write("# Deployments\n")
    with open(os.path.join(root, "SESSIONS_STATE.md"), "w") as fh:
        fh.write(_SESSIONS_STATE)
    git(["init", "-b", "main", "."], root)
    git(["add", "-A"], root)
    git(["commit", "-m", "scaffold"], root)
    return root


class TempRepoCase(unittest.TestCase):
    """Base case giving each test an isolated temp dir (self.tmp)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cwscripts-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
