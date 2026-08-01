"""Tests for the fan-out scheduler + run manifest + teardown plan (build §3.4).

Pure/file-level logic for the launcher: a dep-aware bounded-concurrency scheduler
(so "in parallel" has a hard cap), a run manifest (aggregate observability), and a
manifest-driven teardown plan (revoke keys, remove worktrees, prune branches) that
is idempotent and crash-re-entrant. The actual subprocess launch + git/key calls
are thin wrappers around these.

Run: python3 autonomous-workflows/tests/test_fanout.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # autonomous-workflows/ on path
import fanout  # noqa: E402


class RunnableNowTest(unittest.TestCase):
    def test_respects_concurrency_cap(self):
        self.assertEqual(
            fanout.runnable_now(["t1", "t2", "t3"], deps={}, done=set(), running=set(), max_concurrent=2),
            ["t1", "t2"])

    def test_free_slots_account_for_running(self):
        self.assertEqual(
            fanout.runnable_now(["t1", "t2", "t3"], deps={}, done=set(), running={"t1"}, max_concurrent=2),
            ["t2"])

    def test_no_slots_returns_empty(self):
        self.assertEqual(
            fanout.runnable_now(["t1", "t2"], deps={}, done=set(), running={"t1", "t2"}, max_concurrent=2),
            [])

    def test_deps_gate_start(self):
        # t2 depends on t1 (not done) -> only t1 and t3 are runnable
        self.assertEqual(
            fanout.runnable_now(["t1", "t2", "t3"], deps={"t2": ["t1"]}, done=set(), running=set(), max_concurrent=3),
            ["t1", "t3"])

    def test_deps_satisfied_unblocks(self):
        self.assertEqual(
            fanout.runnable_now(["t1", "t2", "t3"], deps={"t2": ["t1"]}, done={"t1"}, running=set(), max_concurrent=3),
            ["t2", "t3"])


class RunnableNowPausedTest(unittest.TestCase):
    # D7/F5: a rate-limit resets_at or churn-breaker backoff makes a task
    # not-runnable until `now` reaches it.
    def test_paused_until_future_blocks(self):
        self.assertEqual(
            fanout.runnable_now(["t1", "t2"], deps={}, done=set(), running=set(),
                                max_concurrent=3, now="2026-07-30T12:00:00Z",
                                paused_until={"t1": "2026-07-30T16:00:00Z"}),
            ["t2"])

    def test_paused_until_past_re_admits(self):
        # reset time already passed -> t1 runnable again (5h resume lifecycle)
        self.assertEqual(
            fanout.runnable_now(["t1"], deps={}, done=set(), running=set(),
                                max_concurrent=3, now="2026-07-30T17:00:00Z",
                                paused_until={"t1": "2026-07-30T16:00:00Z"}),
            ["t1"])

    def test_no_paused_until_is_unchanged(self):
        self.assertEqual(
            fanout.runnable_now(["t1", "t2"], deps={}, done=set(), running=set(), max_concurrent=3),
            ["t1", "t2"])


class ManifestLaneTest(unittest.TestCase):
    # rev 2.1 N2: manifest carries lane + per-agent model + window_est_usd
    # (tier-aware committed_burn needs both).
    def _sub_spec(self):
        return [{"task_id": "t1", "branch": "auto/S/t1", "worktree": "/wt/t1",
                 "lane": "subscription", "model": "claude-sonnet-5", "window_est_usd": 1.0}]

    def test_manifest_carries_lane_model_window_est(self):
        a = fanout.new_manifest("run-1", self._sub_spec())["agents"]["t1"]
        self.assertEqual(a["lane"], "subscription")
        self.assertEqual(a["model"], "claude-sonnet-5")
        self.assertEqual(a["window_est_usd"], 1.0)
        self.assertIsNone(a["key_id"])   # no gateway key on the subscription lane

    def test_subscription_teardown_has_no_key_revoke(self):
        m = fanout.new_manifest("run-1", self._sub_spec())
        fanout.set_status(m, "t1", "review_ready")   # no key_id minted on subscription
        plan = fanout.teardown_plan(m)
        self.assertFalse(any(x["action"] == "revoke_key" for x in plan))
        self.assertTrue(any(x["action"] == "remove_worktree" for x in plan))


class ManifestTest(unittest.TestCase):
    def _specs(self):
        return [
            {"task_id": "t1", "branch": "auto/S/t1", "worktree": "/wt/t1"},
            {"task_id": "t2", "branch": "auto/S/t2", "worktree": "/wt/t2"},
        ]

    def test_new_manifest_starts_pending(self):
        m = fanout.new_manifest("run-1", self._specs())
        self.assertEqual(m["run_id"], "run-1")
        self.assertEqual(m["agents"]["t1"]["status"], "pending")
        self.assertEqual(m["agents"]["t1"]["branch"], "auto/S/t1")

    def test_set_status_updates_fields(self):
        m = fanout.new_manifest("run-1", self._specs())
        fanout.set_status(m, "t1", "running", pid=123, key_id="k1")
        self.assertEqual(m["agents"]["t1"]["status"], "running")
        self.assertEqual(m["agents"]["t1"]["pid"], 123)
        self.assertEqual(m["agents"]["t1"]["key_id"], "k1")

    def test_roundtrip(self):
        m = fanout.new_manifest("run-1", self._specs())
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / "m.json")
            fanout.write_manifest(p, m)
            self.assertEqual(fanout.read_manifest(p), m)


class TeardownPlanTest(unittest.TestCase):
    def _manifest(self):
        m = fanout.new_manifest("run-1", [
            {"task_id": "t1", "branch": "auto/S/t1", "worktree": "/wt/t1"},
            {"task_id": "t2", "branch": "auto/S/t2", "worktree": "/wt/t2"},
        ])
        fanout.set_status(m, "t1", "review_ready", key_id="k1")
        fanout.set_status(m, "t2", "failed", key_id="k2")
        return m

    def test_plan_revokes_keys_removes_worktrees_deletes_branches(self):
        plan = fanout.teardown_plan(self._manifest())
        actions = {(a["action"], a.get("key_id") or a.get("path") or a.get("branch")) for a in plan}
        self.assertIn(("revoke_key", "k1"), actions)
        self.assertIn(("revoke_key", "k2"), actions)
        self.assertIn(("remove_worktree", "/wt/t1"), actions)
        self.assertIn(("delete_branch", "auto/S/t1"), actions)

    def test_kept_branch_is_not_deleted(self):
        plan = fanout.teardown_plan(self._manifest(), keep={"t1"})
        deleted = {a["branch"] for a in plan if a["action"] == "delete_branch"}
        self.assertNotIn("auto/S/t1", deleted)   # kept for the approved merge
        self.assertIn("auto/S/t2", deleted)
        # but t1's key + worktree are still torn down
        self.assertTrue(any(a["action"] == "remove_worktree" and a["path"] == "/wt/t1" for a in plan))


if __name__ == "__main__":
    unittest.main()
