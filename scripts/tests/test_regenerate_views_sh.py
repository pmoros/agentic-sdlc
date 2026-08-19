"""End-to-end tests for scripts/regenerate-views.sh — scans work/items/*.json
and writes backlog.json/wip.json/archive.json, or (in --check mode) verifies
they already match without writing.

Pure partitioning logic is covered in test_regenerate_views.py; this file
covers only what a subprocess/filesystem test can — the directory scan,
--check drift detection, and CI-style fail-the-build behavior.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import script, make_work_sessions_repo, TempRepoCase  # noqa: E402

SCRIPT = script("regenerate-views.sh")


class RegenerateViews(TempRepoCase):
    def setUp(self):
        super().setUp()
        self.ws = make_work_sessions_repo(self.tmp)
        self.items_dir = os.path.join(self.ws, "work", "items")
        os.makedirs(self.items_dir)

    def write_item(self, item_id, status, **extra):
        with open(os.path.join(self.items_dir, f"{item_id}.json"), "w") as fh:
            json.dump({"id": item_id, "title": item_id, "status": status, **extra}, fh)

    def run_regen(self, extra=()):
        return subprocess.run(
            [SCRIPT, "--work-sessions-repo", self.ws, *extra],
            capture_output=True, text=True,
        )

    def read_view(self, name):
        with open(os.path.join(self.ws, "work", name)) as fh:
            return json.load(fh)

    # --- regeneration ----------------------------------------------------

    def test_partitions_items_into_the_three_views(self):
        self.write_item("A", "grooming")
        self.write_item("B", "in progress")
        self.write_item("C", "done")
        r = self.run_regen()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("A", self.read_view("backlog.json"))
        self.assertIn("B", self.read_view("wip.json"))
        self.assertIn("C", self.read_view("archive.json"))

    def test_empty_items_dir_produces_empty_views(self):
        r = self.run_regen()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_view("backlog.json"), {})
        self.assertEqual(self.read_view("wip.json"), {})
        self.assertEqual(self.read_view("archive.json"), {})

    def test_does_not_touch_scratchpad_json(self):
        scratchpad = os.path.join(self.ws, "work", "scratchpad.json")
        with open(scratchpad, "w") as fh:
            json.dump({"NOTE-1": {"note": "untouched"}}, fh)
        self.write_item("A", "grooming")
        self.run_regen()
        with open(scratchpad) as fh:
            self.assertEqual(json.load(fh), {"NOTE-1": {"note": "untouched"}})

    def test_rerunning_is_idempotent(self):
        self.write_item("A", "ready")
        self.run_regen()
        first = self.read_view("backlog.json")
        r = self.run_regen()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_view("backlog.json"), first)

    def test_bad_status_fails_loudly_rather_than_dropping_the_item(self):
        self.write_item("A", "not-a-real-status")
        r = self.run_regen()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("A", r.stderr)

    # --- --check mode ------------------------------------------------------

    def test_check_passes_when_views_already_match(self):
        self.write_item("A", "grooming")
        self.assertEqual(self.run_regen().returncode, 0)
        r = self.run_regen(["--check"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_check_fails_on_drift_and_does_not_write(self):
        self.write_item("A", "grooming")
        self.run_regen()
        before = self.read_view("backlog.json")

        self.write_item("B", "ready")  # new item, views not regenerated yet
        r = self.run_regen(["--check"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("drift", r.stderr.lower())
        self.assertEqual(self.read_view("backlog.json"), before)  # --check never writes

    def test_check_fails_on_a_hand_edited_view(self):
        self.write_item("A", "grooming")
        self.run_regen()
        with open(os.path.join(self.ws, "work", "wip.json"), "w") as fh:
            json.dump({"hand-added": {"title": "sneaky"}}, fh)
        r = self.run_regen(["--check"])
        self.assertNotEqual(r.returncode, 0)

    # --- concurrency: multiple invocations racing to write the SAME view
    #     files (the views themselves have no per-item isolation — unlike
    #     work/items/, this is a genuinely shared target). Regression test:
    #     an earlier version used a fixed tmp filename and crashed with
    #     FileNotFoundError when two invocations' os.replace() raced.

    def test_concurrent_invocations_never_crash_on_shared_tmp_file(self):
        for i in range(8):
            self.write_item(f"A{i}", "grooming")
        procs = [subprocess.Popen(
            [SCRIPT, "--work-sessions-repo", self.ws],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ) for _ in range(8)]
        results = [p.communicate(timeout=15) for p in procs]
        for p, (_, stderr) in zip(procs, results):
            self.assertEqual(p.returncode, 0, stderr)
        # every view file must still parse cleanly — no partial/interleaved write
        for name in ("backlog.json", "wip.json", "archive.json"):
            self.read_view(name)


if __name__ == "__main__":
    unittest.main()
