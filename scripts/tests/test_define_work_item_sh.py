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

    def test_parent_flag_links_item_to_an_existing_top_level_item(self):
        self.define("ADH-20", ["--description", "epic"])
        r = self.define("ADH-21", ["--description", "sub-item", "--parent", "ADH-20"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_item("ADH-21")["parent_id"], "ADH-20")
        self.assertNotIn("parent_id", self.read_item("ADH-20"))

    def test_parent_flag_refuses_self_parent_and_writes_no_file(self):
        r = self.define("ADH-20", ["--description", "d", "--parent", "ADH-20"])
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.items_dir, "ADH-20.json")))

    def test_parent_flag_refuses_nonexistent_target(self):
        r = self.define("ADH-21", ["--description", "d", "--parent", "ADH-999-nope"])
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.items_dir, "ADH-21.json")))

    def test_parent_flag_does_not_execute_code_embedded_in_the_value(self):
        # A `--parent` value crafted to break out of the (now env-var-passed)
        # python3 -c string context must be treated as inert data, not
        # executed. Regression test for the injection a fresh-context
        # reviewer demonstrated when this validation call still
        # interpolated $PARENT directly into Python source text.
        marker = os.path.join(self.tmp, "PWNED_PARENT_MARKER")
        evil_parent = f"ADH100'+__import__('os').system('touch {marker}')+'y"
        r = self.define("ADH-100", ["--description", "d", "--parent", evil_parent])
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(marker))

    def test_parent_flag_refuses_a_two_level_chain(self):
        self.define("ADH-20", ["--description", "epic"])
        self.define("ADH-21", ["--description", "sub", "--parent", "ADH-20"])
        r = self.define("ADH-22", ["--description", "grandchild", "--parent", "ADH-21"])
        self.assertNotEqual(r.returncode, 0)

    def test_promote_flag_clears_parent_and_preserves_history(self):
        self.define("ADH-20", ["--description", "epic"])
        self.define("ADH-21", ["--description", "sub", "--parent", "ADH-20",
                                "--record-event", "linked", "--by", "test"])
        r = self.define("ADH-21", ["--promote"])
        self.assertEqual(r.returncode, 0, r.stderr)
        item = self.read_item("ADH-21")
        self.assertNotIn("parent_id", item)
        self.assertTrue(any(h["action"] == "linked" for h in item["history"]))

    def test_promote_flag_refuses_when_item_has_no_parent(self):
        self.define("ADH-21", ["--description", "d"])
        r = self.define("ADH-21", ["--promote"])
        self.assertNotEqual(r.returncode, 0)

    def test_parent_and_promote_together_rejected(self):
        r = self.define("ADH-21", ["--description", "d", "--parent", "ADH-20", "--promote"])
        self.assertNotEqual(r.returncode, 0)

    def test_parent_link_releases_the_shared_lock_after_success(self):
        self.define("ADH-20", ["--description", "epic"])
        self.define("ADH-21", ["--description", "sub", "--parent", "ADH-20"])
        self.assertFalse(os.path.isdir(os.path.join(self.items_dir, ".parent-link.lock")))

    def test_parent_link_releases_the_shared_lock_after_validation_failure(self):
        # The lock is acquired BEFORE validation runs -- a refusal must
        # still release it, or every subsequent --parent/--promote call
        # would hang until the stale-lock timeout.
        r = self.define("ADH-20", ["--description", "d", "--parent", "ADH-20"])  # self-parent
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.isdir(os.path.join(self.items_dir, ".parent-link.lock")))

    def test_promote_releases_the_shared_lock_after_validation_failure(self):
        self.define("ADH-21", ["--description", "d"])  # no parent to clear
        r = self.define("ADH-21", ["--promote"])
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.isdir(os.path.join(self.items_dir, ".parent-link.lock")))

    def test_concurrent_parent_links_on_different_items_never_produce_a_multi_level_chain(self):
        # The exact race Gate A round 1 traced by hand: item P is
        # top-level, X and Y are top-level. Launched concurrently:
        #   call 1: X --parent P
        #   call 2: Y --parent X
        # An unguarded validation read lets both pass (neither's write has
        # landed yet), producing a live P -> X -> Y chain. The shared
        # work/items/.parent-link.lock/ must serialize these so exactly
        # one succeeds and the other is refused, whichever order wins.
        self.define("ADH-P", ["--description", "top"])
        self.define("ADH-X", ["--description", "middle"])
        self.define("ADH-Y", ["--description", "leaf"])

        procs = [
            subprocess.Popen(
                [SCRIPT, "ADH-X", "--work-sessions-repo", self.ws, "--parent", "ADH-P"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ),
            subprocess.Popen(
                [SCRIPT, "ADH-Y", "--work-sessions-repo", self.ws, "--parent", "ADH-X"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ),
        ]
        results = [p.communicate(timeout=15) for p in procs]
        returncodes = [p.returncode for p in procs]

        # Exactly one of the two links must have gone through -- whichever
        # order the shared lock serialized them in, the other must have
        # been refused by validate_parent_link once it saw the first
        # write's result.
        self.assertEqual(
            sorted(returncodes), [0, 1],
            f"expected exactly one success and one refusal, got {returncodes}: {results}")

        # No matter which one won, the final state must be at most one
        # level deep -- never a live 3-level chain.
        x_parent = self.read_item("ADH-X").get("parent_id")
        y_parent = self.read_item("ADH-Y").get("parent_id")
        self.assertFalse(
            x_parent == "ADH-P" and y_parent == "ADH-X",
            "a live P -> X -> Y chain formed -- the race was not actually closed")

    def test_reparenting_to_a_different_parent_is_allowed(self):
        self.define("ADH-20", ["--description", "epic1"])
        self.define("ADH-30", ["--description", "epic2"])
        self.define("ADH-21", ["--description", "sub", "--parent", "ADH-20"])
        r = self.define("ADH-21", ["--parent", "ADH-30"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_item("ADH-21")["parent_id"], "ADH-30")

    def test_open_episode_flag_appends_a_new_episode(self):
        self.define("ADH-4", ["--description", "d", "--status", "done"])
        r = self.define("ADH-4", ["--open-episode", "ADH-4--e2"])
        self.assertEqual(r.returncode, 0, r.stderr)
        item = self.read_item("ADH-4")
        self.assertEqual(len(item["sessions"]), 2)
        self.assertEqual(item["sessions"][1]["episode_id"], "ADH-4--e2")
        self.assertEqual(item["status"], "in progress")

    def test_close_episode_requires_outcome(self):
        self.define("ADH-4", ["--description", "d"])
        r = self.define("ADH-4", ["--close-episode", "ADH-4"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--outcome", r.stderr)

    def test_close_episode_flag_sets_outcome_and_status(self):
        self.define("ADH-4", ["--description", "d", "--status", "in progress"])
        r = self.define("ADH-4", ["--close-episode", "ADH-4", "--outcome", "done"])
        self.assertEqual(r.returncode, 0, r.stderr)
        item = self.read_item("ADH-4")
        self.assertEqual(item["status"], "done")
        self.assertEqual(item["sessions"][0]["outcome"], "done")
        self.assertIn("ADH-4", self.read_view("archive.json"))

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

    # --- ADH-014: roadmap_step -----------------------------------------

    def test_roadmap_step_appends_with_defaults(self):
        self.define("ADH-20", ["--description", "d"])
        r = self.define("ADH-20", ["--roadmap-step", "Do the thing", "--roadmap-owner", "pmoros"])
        self.assertEqual(r.returncode, 0, r.stderr)
        roadmap = self.read_item("ADH-20")["roadmap"]
        self.assertEqual(roadmap, [
            {"step": "Do the thing", "owner": "pmoros",
             "target_date": "TBD", "type": "standard"},
        ])

    def test_roadmap_owner_without_step_refused(self):
        self.define("ADH-20", ["--description", "d"])
        r = self.define("ADH-20", ["--roadmap-owner", "pmoros"])
        self.assertNotEqual(r.returncode, 0)

    def test_roadmap_step_without_owner_refused(self):
        self.define("ADH-20", ["--description", "d"])
        r = self.define("ADH-20", ["--roadmap-step", "Do the thing"])
        self.assertNotEqual(r.returncode, 0)

    def test_roadmap_target_date_without_step_refused(self):
        self.define("ADH-20", ["--description", "d"])
        r = self.define("ADH-20", ["--roadmap-target-date", "2026-09-01"])
        self.assertNotEqual(r.returncode, 0)

    def test_roadmap_type_without_step_refused(self):
        self.define("ADH-20", ["--description", "d"])
        r = self.define("ADH-20", ["--roadmap-type", "milestone"])
        self.assertNotEqual(r.returncode, 0)

    def test_roadmap_step_combines_with_parent(self):
        self.define("ADH-20", ["--description", "epic"])
        r = self.define("ADH-21", [
            "--description", "sub", "--parent", "ADH-20",
            "--roadmap-step", "First step", "--roadmap-owner", "pmoros",
        ])
        self.assertEqual(r.returncode, 0, r.stderr)
        item = self.read_item("ADH-21")
        self.assertEqual(item["parent_id"], "ADH-20")
        self.assertEqual(item["roadmap"][0]["step"], "First step")

    def test_roadmap_step_combines_with_open_episode(self):
        self.define("ADH-20", ["--description", "d"])
        self.define("ADH-20", ["--close-episode", "ADH-20", "--outcome", "stopped"])
        r = self.define("ADH-20", [
            "--open-episode", "ADH-20--e2",
            "--roadmap-step", "Next step", "--roadmap-owner", "pmoros",
        ])
        self.assertEqual(r.returncode, 0, r.stderr)
        item = self.read_item("ADH-20")
        self.assertEqual(item["sessions"][-1]["episode_id"], "ADH-20--e2")
        self.assertIsNone(item["sessions"][-1]["closed"])
        self.assertEqual(item["roadmap"][0]["step"], "Next step")

    # --- ADH-014: Tier 1 -- --status done vs. an open episode ----------

    def test_status_done_with_close_episode_together_refused(self):
        self.define("ADH-20", ["--description", "d", "--status", "in progress"])
        r = self.define("ADH-20", ["--status", "done", "--close-episode", "ADH-20", "--outcome", "done"])
        self.assertNotEqual(r.returncode, 0)

    def test_status_done_refused_when_episode_still_open(self):
        self.define("ADH-20", ["--description", "d"])
        self.define("ADH-20", ["--close-episode", "ADH-20", "--outcome", "done"])  # episode 1 closed
        self.define("ADH-20", ["--open-episode", "ADH-20--e2"])  # now open again
        r = self.define("ADH-20", ["--status", "done"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("open episode", r.stderr)
        self.assertEqual(self.read_item("ADH-20")["status"], "in progress")

    def test_status_done_allowed_when_no_episode_ever_opened(self):
        self.define("ADH-20", ["--description", "d"])
        r = self.define("ADH-20", ["--status", "done"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_item("ADH-20")["status"], "done")

    def test_status_done_allowed_when_last_episode_already_closed(self):
        self.define("ADH-20", ["--description", "d"])
        self.define("ADH-20", ["--close-episode", "ADH-20", "--outcome", "stopped"])
        r = self.define("ADH-20", ["--status", "done"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_item("ADH-20")["status"], "done")

    def test_concurrent_status_done_and_open_episode_never_corrupt_the_item(self):
        # Gate A round 2's own scenario: two racing subprocesses on the
        # SAME item -- `--status done` (no --close-episode) and
        # `--open-episode` -- must never together produce status: done
        # with an open sessions[] entry, whichever wins the item's lock.
        #
        # Gate B: a brand-new item's synthesized episode 1 is always open
        # (_ensure_episode_1 derives `closed` from `status`, and a fresh
        # item defaults to "grooming", not a closed-like status) -- so
        # --open-episode always refuses outright regardless of timing,
        # making the race structurally unreachable. Close episode 1 first
        # so --open-episode can actually succeed and the race is real.
        self.define("ADH-20", ["--description", "d"])
        self.define("ADH-20", ["--close-episode", "ADH-20", "--outcome", "stopped"])

        procs = [
            subprocess.Popen(
                [SCRIPT, "ADH-20", "--work-sessions-repo", self.ws, "--status", "done"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ),
            subprocess.Popen(
                [SCRIPT, "ADH-20", "--work-sessions-repo", self.ws,
                 "--open-episode", "ADH-20--e2"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ),
        ]
        results = [p.communicate(timeout=15) for p in procs]

        item = self.read_item("ADH-20")
        sessions = item.get("sessions") or []
        has_open_episode = bool(sessions) and sessions[-1].get("closed") is None
        self.assertFalse(
            item.get("status") == "done" and has_open_episode,
            f"corrupted state: status=done with an open episode -- results: {results}")


if __name__ == "__main__":
    unittest.main()
