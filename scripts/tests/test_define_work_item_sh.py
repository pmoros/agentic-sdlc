"""End-to-end tests for scripts/define-work-item.sh — the canonical Work
Item constructor: CLI parsing, per-item `mkdir`-lock (contention, timeout,
PID-liveness stale-break), and the resulting item file.

Pure item-shaping logic is covered in test_define_work_item.py; this file
covers only what a subprocess/filesystem test can — locking and I/O.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import json
import os
import subprocess
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, script, make_work_sessions_repo, TempRepoCase  # noqa: E402

SCRIPT = script("define-work-item.sh")


class DefineWorkItem(TempRepoCase):
    def setUp(self):
        super().setUp()
        self.ws = make_work_sessions_repo(self.tmp)
        self.items_dir = os.path.join(self.ws, "work", "items")

    def define(self, item_id, extra=(), env=None):
        full_env = {**os.environ, **(env or {})}
        return subprocess.run(
            [SCRIPT, item_id, "--work-sessions-repo", self.ws, *extra],
            capture_output=True, text=True, env=full_env,
        )

    def read_item(self, item_id):
        with open(os.path.join(self.items_dir, f"{item_id}.json")) as fh:
            return json.load(fh)

    def read_view(self, name):
        with open(os.path.join(self.ws, "work", name)) as fh:
            return json.load(fh)

    # --- happy path ---------------------------------------------------

    def test_regenerates_views_after_writing_the_item(self):
        r = self.define("ADH-9", ["--description", "d"])  # defaults to status "grooming"
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ADH-9", self.read_view("backlog.json"))
        self.assertNotIn("ADH-9", self.read_view("wip.json"))

    def test_moving_status_moves_the_item_between_views(self):
        self.define("ADH-9", ["--description", "d", "--status", "grooming"])
        self.define("ADH-9", ["--status", "in progress"])
        self.assertNotIn("ADH-9", self.read_view("backlog.json"))
        self.assertIn("ADH-9", self.read_view("wip.json"))

    def test_creates_item_file(self):
        r = self.define("ADH-9", ["--description", "Do a thing", "--task-type", "feat"])
        self.assertEqual(r.returncode, 0, r.stderr)
        item = self.read_item("ADH-9")
        self.assertEqual(item["id"], "ADH-9")
        self.assertEqual(item["title"], "[feat] Do a thing")
        self.assertEqual(item["status"], "grooming")

    def test_reshapes_existing_item_without_losing_history(self):
        self.assertEqual(self.define("ADH-9", ["--description", "d"]).returncode, 0)
        r = self.define("ADH-9", ["--status", "ready", "--scope", "M"])
        self.assertEqual(r.returncode, 0, r.stderr)
        item = self.read_item("ADH-9")
        self.assertEqual(item["status"], "ready")
        self.assertEqual(item["scope"], "M")
        self.assertEqual(len(item["history"]), 1)  # still just the original "item defined"

    def test_record_event_appends_history_on_reshape(self):
        self.define("ADH-9", ["--description", "d"])  # "item defined"
        r = self.define("ADH-9", ["--status", "in progress",
                                   "--record-event", "session started", "--by", "init-session.sh"])
        self.assertEqual(r.returncode, 0, r.stderr)
        item = self.read_item("ADH-9")
        actions = [h["action"] for h in item["history"]]
        self.assertEqual(actions, ["item defined", "session started"])
        self.assertEqual(item["history"][-1]["by"], "init-session.sh")

    def test_current_state_flag_sets_description_and_blocked(self):
        self.define("ADH-9", ["--description", "d"])
        r = self.define("ADH-9", ["--current-state", "waiting on review", "--blocked"])
        self.assertEqual(r.returncode, 0, r.stderr)
        item = self.read_item("ADH-9")
        self.assertEqual(item["current_state"], {"description": "waiting on review", "is_blocked": True})

    def test_last_synced_flag_sets_the_watermark(self):
        self.define("ADH-9", ["--description", "d"])
        r = self.define("ADH-9", ["--last-synced", "2026-08-19T00:00:00Z"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_item("ADH-9")["last_synced"], "2026-08-19T00:00:00Z")

    def test_releases_lock_after_success(self):
        self.define("ADH-9", ["--description", "d"])
        self.assertFalse(os.path.exists(os.path.join(self.items_dir, "ADH-9.json.lock")))

    # --- argument validation -------------------------------------------

    def test_requires_item_id(self):
        r = subprocess.run([SCRIPT, "--work-sessions-repo", self.ws],
                            capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)

    def test_rejects_invalid_scope_and_leaves_no_file(self):
        r = self.define("ADH-9", ["--description", "d", "--scope", "HUGE"])
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.items_dir, "ADH-9.json")))

    def test_rejects_unknown_flag(self):
        r = self.define("ADH-9", ["--not-a-real-flag", "x"])
        self.assertNotEqual(r.returncode, 0)

    # --- locking: stale lock (dead holder) is broken --------------------

    def test_stale_lock_with_dead_pid_is_broken_not_waited_out(self):
        lock_dir = os.path.join(self.items_dir, "ADH-9.json.lock")
        os.makedirs(lock_dir)
        # a pid that is essentially guaranteed not to be running
        with open(os.path.join(lock_dir, "pid"), "w") as fh:
            fh.write("999999")

        start = time.time()
        r = self.define("ADH-9", ["--description", "d"],
                         env={"DEFINE_ITEM_LOCK_STALE_SECS": "0",
                              "DEFINE_ITEM_LOCK_TIMEOUT_SECS": "5"})
        elapsed = time.time() - start

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(elapsed, 4, "should break the stale lock immediately, not wait out the timeout")
        self.assertIn("stale lock", r.stderr.lower())

    # --- locking: a live holder is never preempted, times out cleanly ---

    def test_live_holder_lock_is_never_preempted_and_wrapper_times_out(self):
        lock_dir = os.path.join(self.items_dir, "ADH-9.json.lock")
        os.makedirs(lock_dir)
        with open(os.path.join(lock_dir, "pid"), "w") as fh:
            fh.write(str(os.getpid()))  # this test process — genuinely alive

        r = self.define("ADH-9", ["--description", "d"],
                         env={"DEFINE_ITEM_LOCK_STALE_SECS": "0",
                              "DEFINE_ITEM_LOCK_TIMEOUT_SECS": "1"})

        self.assertNotEqual(r.returncode, 0)
        self.assertIn("timed out", r.stderr.lower())
        self.assertFalse(os.path.exists(os.path.join(self.items_dir, "ADH-9.json")))

    # --- locking: same-item concurrent writers never corrupt the file ---

    def test_concurrent_writes_to_same_item_never_corrupt_the_file(self):
        procs = [
            subprocess.Popen(
                [SCRIPT, "ADH-9", "--work-sessions-repo", self.ws,
                 "--description", f"from writer {i}", "--priority", "Minor"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for i in range(5)
        ]
        results = [p.communicate(timeout=15) for p in procs]
        for p, (_, stderr) in zip(procs, results):
            self.assertEqual(p.returncode, 0, stderr)

        item = self.read_item("ADH-9")  # must parse cleanly — no interleaved/partial write
        self.assertEqual(item["id"], "ADH-9")
        self.assertTrue(item["description"].startswith("from writer"))

    def test_concurrent_writes_to_different_items_do_not_block_each_other(self):
        start = time.time()
        procs = [
            subprocess.Popen(
                [SCRIPT, f"ADH-{i}", "--work-sessions-repo", self.ws, "--description", "d"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for i in range(5)
        ]
        results = [p.communicate(timeout=15) for p in procs]
        elapsed = time.time() - start

        for p, (_, stderr) in zip(procs, results):
            self.assertEqual(p.returncode, 0, stderr)
        for i in range(5):
            self.assertTrue(os.path.exists(os.path.join(self.items_dir, f"ADH-{i}.json")))
        self.assertLess(elapsed, 5, "different items must not contend for the same lock")


if __name__ == "__main__":
    unittest.main()
