"""End-to-end tests for scripts/init-session.sh.

Uses a minimal work-sessions repo + a scratch agentic-sdlc repo. tmux linkage
is exercised when tmux is present and always torn down.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import json
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

    def read_json(self, name):
        with open(os.path.join(self.ws, "work", name)) as fh:
            return json.load(fh)

    def read_item(self, item_id):
        return self.read_json(os.path.join("items", f"{item_id}.json"))

    def write_item(self, item_id, item):
        items_dir = os.path.join(self.ws, "work", "items")
        os.makedirs(items_dir, exist_ok=True)
        with open(os.path.join(items_dir, f"{item_id}.json"), "w") as fh:
            json.dump(item, fh, indent=2)

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

    def test_seeds_item_when_none_exists(self):
        self.assertEqual(self.init().returncode, 0)

        item = self.read_item(SID)
        self.assertEqual(item["status"], "in progress")               # picked up for active work
        self.assertIn("Self-test of init-session", item["title"])     # seeded from goal
        self.assertFalse(item["current_state"]["is_blocked"])         # not blocked by default
        self.assertIn("https://example.test/browse/ADH-1", json.dumps(item["tickets"]))
        self.assertTrue(any("session started" in h.get("action", "").lower()
                            for h in item["history"]), item["history"])

        # define-work-item.sh's automatic regenerate-views.sh call means the
        # (derived) wip.json view picks the item up too, backlog stays empty.
        wip_view = self.read_json("wip.json")
        self.assertIn(SID, wip_view)
        self.assertEqual(self.read_json("backlog.json"), {})

    def test_reshapes_existing_groomed_item_preserving_fields(self):
        self.write_item(SID, {
            "id": SID,
            "title": "Groomed item title",
            "description": "already-shaped item",
            "status": "ready",
            "roadmap": [{"step": "do the thing", "owner": "me"}],
            "current_state": {"description": "groomed, not started", "is_blocked": False},
            "history": [{"action": "groomed", "timestamp": "2026-08-01", "by": "pm"}],
            "sessions": [],
        })
        self.assertEqual(self.init().returncode, 0)

        item = self.read_item(SID)
        self.assertEqual(item["status"], "in progress")                # flipped
        self.assertEqual(item["title"], "Groomed item title")          # groomed field preserved
        self.assertEqual(item["roadmap"], [{"step": "do the thing", "owner": "me"}])
        actions = [h["action"] for h in item["history"]]
        self.assertEqual(actions, ["groomed", "session started"])      # appended, not reset

    def test_registration_does_not_touch_other_items(self):
        self.write_item("OTHER-1", {
            "id": "OTHER-1", "title": "someone else's work", "status": "in progress",
            "current_state": {"description": "x", "is_blocked": False}, "history": [], "sessions": [],
        })
        self.assertEqual(self.init().returncode, 0)

        self.assertEqual(self.read_item("OTHER-1")["title"], "someone else's work")
        self.assertIn(SID, self.read_json("wip.json"))

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


class MigrationSafetyGuard(TempRepoCase):
    """ADH-008 Phase 7: init-session.sh must refuse rather than silently
    derive views from an empty work/items/ while backlog.json/wip.json
    still hold real, un-migrated content."""

    def setUp(self):
        super().setUp()
        self.addCleanup(_kill_tmux)
        self.agentic = make_remote_repo(self.tmp, "agentic")

    def init(self, ws):
        return run([
            SCRIPT, SID, "--goal", "g", "--work-sessions-repo", ws,
            "--agentic-sdlc-repo", self.agentic,
        ], check=False)

    def test_refuses_when_backlog_has_real_content_and_items_dir_absent(self):
        ws = make_work_sessions_repo(self.tmp, backlog={"OLD-1": {"title": "t", "status": "grooming"}})
        r = self.init(ws)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("migrate-items-v2.sh", r.stderr)
        self.assertFalse(os.path.isdir(os.path.join(ws, "sessions", SID)))  # nothing created

    def test_guard_not_masked_by_a_crash_orphaned_lock_dir(self):
        # ADH-008 Gate B QA finding: a define-work-item.sh run killed before
        # its EXIT trap fires can leave an empty <id>.json.lock/ dir in
        # work/items/ with no real item file. `ls -A` alone would see that
        # as "populated" and silently skip the guard — exactly the hazard
        # the guard exists to prevent.
        ws = make_work_sessions_repo(self.tmp, backlog={"OLD-1": {"title": "t", "status": "grooming"}})
        items_dir = os.path.join(ws, "work", "items")
        os.makedirs(os.path.join(items_dir, "SOME-ID.json.lock"))
        r = self.init(ws)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("migrate-items-v2.sh", r.stderr)

    def test_refuses_on_corrupt_backlog_json_rather_than_silently_proceeding(self):
        # A file that exists but fails to parse must fail CLOSED (treated
        # as "might hold real content") — not silently treated as empty.
        ws = make_work_sessions_repo(self.tmp)
        with open(os.path.join(ws, "work", "backlog.json"), "w") as fh:
            fh.write("not valid json {{{")
        r = self.init(ws)
        self.assertNotEqual(r.returncode, 0)

    def test_refuses_when_wip_has_real_content_and_items_dir_absent(self):
        ws = make_work_sessions_repo(self.tmp, wip={"OLD-1": {"title": "t", "status": "in progress"}})
        r = self.init(ws)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("migrate-items-v2.sh", r.stderr)

    def test_proceeds_normally_when_backlog_and_wip_are_empty(self):
        ws = make_work_sessions_repo(self.tmp)  # default: backlog={}, wip={}
        r = self.init(ws)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_proceeds_normally_once_items_dir_is_populated(self):
        ws = make_work_sessions_repo(self.tmp, backlog={"OLD-1": {"title": "t", "status": "grooming"}})
        items_dir = os.path.join(ws, "work", "items")
        os.makedirs(items_dir)
        with open(os.path.join(items_dir, "OLD-1.json"), "w") as fh:
            json.dump({"id": "OLD-1", "title": "t", "status": "grooming",
                      "current_state": {"description": "", "is_blocked": False},
                      "history": [], "sessions": []}, fh)
        r = self.init(ws)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
