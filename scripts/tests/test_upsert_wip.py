"""Unit tests for the pure wip-upsert logic (scripts/lib/upsert_wip.py).

Tests the decision-making function directly with plain dicts — no filesystem,
no subprocess. The end-to-end wiring through init-session.sh is covered in
test_init_session.py.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import upsert_wip as U  # noqa: E402

NOW = "2026-07-13 10:00"


class SeedFreshEntry(unittest.TestCase):
    def test_seeds_from_goal_ticket_scope_task_type(self):
        wip, backlog = U.upsert_wip(
            {}, {}, sid="ADH-9", goal="Do a thing",
            ticket="https://x/browse/ADH-9", scope="M",
            task_type="feat", now=NOW)
        item = wip["ADH-9"]
        self.assertEqual(item["status"], "in progress")
        self.assertEqual(item["title"], "[feat] Do a thing")
        self.assertEqual(item["description"], "Do a thing")
        self.assertEqual(item["scope"], "M")
        self.assertEqual(item["tickets"], {"main-bug-tracking": "https://x/browse/ADH-9"})
        self.assertFalse(item["current_state"]["is_blocked"])
        self.assertEqual(item["current_state"]["description"], "Do a thing")
        self.assertEqual(backlog, {})

    def test_blockers_set_blocked_state(self):
        wip, _ = U.upsert_wip(
            {}, {}, sid="ADH-9", goal="Do a thing",
            blockers="waiting on access", now=NOW)
        cs = wip["ADH-9"]["current_state"]
        self.assertTrue(cs["is_blocked"])
        self.assertEqual(cs["description"], "waiting on access")

    def test_history_has_single_session_started_entry(self):
        wip, _ = U.upsert_wip({}, {}, sid="ADH-9", goal="g", now=NOW)
        hist = wip["ADH-9"]["history"]
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["action"], "session started")
        self.assertEqual(hist[0]["timestamp"], NOW)


class MoveFromBacklog(unittest.TestCase):
    def test_moves_and_preserves_groomed_fields(self):
        backlog = {"PROJ-1": {
            "title": "Groomed", "description": "shaped",
            "status": "ready",
            "tickets": {"main-bug-tracking": "https://x/browse/PROJ-1"},
            "roadmap": [{"step": "s1", "owner": "me"}],
            "history": [{"action": "groomed", "timestamp": "2026-07-01", "by": "pm"}],
        }}
        wip, backlog = U.upsert_wip(
            {}, backlog, sid="PROJ-1", goal="ignored when moving", now=NOW)
        self.assertNotIn("PROJ-1", backlog)              # removed from backlog
        item = wip["PROJ-1"]
        self.assertEqual(item["status"], "in progress")   # flipped
        self.assertEqual(item["title"], "Groomed")        # groomed fields kept
        self.assertEqual(item["roadmap"], [{"step": "s1", "owner": "me"}])
        # history is append-only: prior entry kept, session-started appended
        actions = [h["action"] for h in item["history"]]
        self.assertEqual(actions, ["groomed", "session started"])


class Idempotency(unittest.TestCase):
    def test_existing_wip_entry_left_untouched(self):
        existing = {"PROJ-1": {
            "title": "in flight", "status": "in progress",
            "current_state": {"description": "half done", "is_blocked": False},
            "history": [{"action": "session started", "timestamp": "t0", "by": "x"}],
        }}
        wip, backlog = U.upsert_wip(
            dict(existing), {}, sid="PROJ-1", goal="new goal", now=NOW)
        self.assertEqual(wip["PROJ-1"], existing["PROJ-1"])   # no dup history, no clobber

    def test_does_not_touch_other_entries(self):
        other = {"OTHER-1": {"title": "someone else", "status": "in progress"}}
        wip, _ = U.upsert_wip(dict(other), {}, sid="NEW-1", goal="g", now=NOW)
        self.assertEqual(wip["OTHER-1"], other["OTHER-1"])
        self.assertIn("NEW-1", wip)


if __name__ == "__main__":
    unittest.main()
