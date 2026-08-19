"""End-to-end tests for scripts/migrate-items-v2.sh — the one-time
migration from backlog.json/wip.json to work/items/<id>.json.

Pure migration logic is covered in test_migrate_items.py; this file covers
only what a subprocess/filesystem test can — --dry-run writing nothing,
--commit's staging/verify/move sequence and refusal/idempotency rules,
--commit-cleanup's renames, and standalone --verify.

Runs under pytest or `python -m unittest discover -s scripts/tests`.

IMPORTANT: never run this script against the real work-sessions repo — every
test here builds its own throwaway work-sessions repo via
make_work_sessions_repo() / _sessions_state_with_row().
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import script, make_work_sessions_repo, TempRepoCase  # noqa: E402

SCRIPT = script("migrate-items-v2.sh")

BACKLOG = {
    "ADH-009": {
        "title": "Build local AI-agent control plane",
        "description": "Self-hosted orchestration stack",
        "status": "grooming",
        "started": "16 August 2026",
        "tickets": {},
    },
}

WIP = {
    "ADH-001-autonomous-workflows": {
        "title": "Build an autonomous multi-agent coding system",
        "description": "Design and incrementally build it",
        "status": "in progress",
        "started": "12 July 2026",
        "history": [{"action": "session started", "timestamp": "2026-07-12T14:19:00Z", "by": "claude"}],
    },
}

_SESSIONS_STATE_WITH_ROWS = """# Sessions State

| Session ID | Title | Tmux Session | Session Folder | Created | Last Change | Status |
|---|---|---|---|---|---|---|
| ADH-001-autonomous-workflows | Build a thing | cw-ADH-001 | sessions/ADH-001-autonomous-workflows | 2026-07-12 | 2026-08-02 | active |
"""


class MigrateItemsBase(TempRepoCase):
    def setUp(self):
        super().setUp()
        self.ws = make_work_sessions_repo(self.tmp, backlog=BACKLOG, wip=WIP)
        self.work_dir = os.path.join(self.ws, "work")
        self.items_dir = os.path.join(self.work_dir, "items")
        with open(os.path.join(self.ws, "SESSIONS_STATE.md"), "w") as fh:
            fh.write(_SESSIONS_STATE_WITH_ROWS)

    def migrate(self, extra=(), env=None):
        full_env = {**os.environ, **(env or {})}
        return subprocess.run(
            [SCRIPT, "--work-sessions-repo", self.ws, *extra],
            capture_output=True, text=True, env=full_env,
        )

    def read_item(self, item_id):
        with open(os.path.join(self.items_dir, f"{item_id}.json")) as fh:
            return json.load(fh)

    def read_json(self, rel):
        with open(os.path.join(self.work_dir, rel)) as fh:
            return json.load(fh)


class DryRun(MigrateItemsBase):
    def test_default_mode_is_dry_run_and_writes_nothing(self):
        r = self.migrate()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.items_dir))

    def test_explicit_dry_run_flag_writes_nothing(self):
        r = self.migrate(["--dry-run"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.items_dir))

    def test_prints_a_per_item_diff(self):
        r = self.migrate()
        self.assertIn("ADH-009", r.stdout)
        self.assertIn("ADH-001-autonomous-workflows", r.stdout)

    def test_backlog_and_wip_are_left_untouched(self):
        self.migrate()
        self.assertEqual(self.read_json("backlog.json"), BACKLOG)
        self.assertEqual(self.read_json("wip.json"), WIP)

    def test_safe_to_run_repeatedly(self):
        first = self.migrate()
        second = self.migrate()
        self.assertEqual(first.returncode, 0)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)


class Commit(MigrateItemsBase):
    def test_writes_one_file_per_item(self):
        r = self.migrate(["--commit"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.items_dir, "ADH-009.json")))
        self.assertTrue(os.path.exists(os.path.join(self.items_dir, "ADH-001-autonomous-workflows.json")))

    def test_every_pre_existing_field_is_preserved(self):
        self.migrate(["--commit"])
        item = self.read_item("ADH-009")
        for key, value in BACKLOG["ADH-009"].items():
            self.assertEqual(item[key], value)

    def test_adds_id_and_sessions_fields(self):
        self.migrate(["--commit"])
        item = self.read_item("ADH-001-autonomous-workflows")
        self.assertEqual(item["id"], "ADH-001-autonomous-workflows")
        self.assertEqual(len(item["sessions"]), 1)
        self.assertEqual(item["sessions"][0]["episode_id"], "ADH-001-autonomous-workflows")

    def test_item_never_registered_as_a_session_gets_empty_sessions(self):
        self.migrate(["--commit"])
        item = self.read_item("ADH-009")  # not in SESSIONS_STATE.md
        self.assertEqual(item["sessions"], [])

    def test_no_staging_dir_left_behind_on_success(self):
        self.migrate(["--commit"])
        self.assertFalse(os.path.exists(os.path.join(self.work_dir, ".items-migration-staging")))
        # and it wasn't left nested inside items_dir either (old, non-atomic layout)
        self.assertFalse(os.path.exists(os.path.join(self.items_dir, ".staging")))

    def test_backlog_and_wip_left_in_place_after_commit(self):
        self.migrate(["--commit"])
        self.assertTrue(os.path.exists(os.path.join(self.work_dir, "backlog.json")))
        self.assertTrue(os.path.exists(os.path.join(self.work_dir, "wip.json")))
        self.assertEqual(self.read_json("backlog.json"), BACKLOG)

    def test_verification_pass_runs_automatically_and_reports_success(self):
        r = self.migrate(["--commit"])
        self.assertIn("migrated", r.stdout.lower())

    # --- refusal / idempotency -------------------------------------------

    def test_refuses_when_items_dir_already_has_real_content(self):
        os.makedirs(self.items_dir)
        with open(os.path.join(self.items_dir, "PRE-EXISTING.json"), "w") as fh:
            json.dump({"id": "PRE-EXISTING"}, fh)

        r = self.migrate(["--commit"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already", r.stderr.lower())
        # untouched
        self.assertTrue(os.path.exists(os.path.join(self.items_dir, "PRE-EXISTING.json")))
        self.assertFalse(os.path.exists(os.path.join(self.items_dir, "ADH-009.json")))

    def test_clears_stale_staging_from_interrupted_attempt_and_proceeds(self):
        staging = os.path.join(self.work_dir, ".items-migration-staging")
        os.makedirs(staging)
        with open(os.path.join(staging, "LEFTOVER.json"), "w") as fh:
            fh.write("not valid json {{{")

        r = self.migrate(["--commit"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(staging, "LEFTOVER.json")))
        self.assertTrue(os.path.exists(os.path.join(self.items_dir, "ADH-009.json")))

    # --- failure: no partial state visible --------------------------------

    def test_one_item_failing_verification_aborts_the_whole_commit(self):
        r = self.migrate(["--commit"], env={"MIGRATE_FAULT_CORRUPT_ID_ENV": "ADH-009"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("verification failed", r.stderr.lower())
        self.assertIn("ADH-009", r.stderr)

    def test_failed_commit_leaves_no_items_dir_at_all(self):
        self.migrate(["--commit"], env={"MIGRATE_FAULT_CORRUPT_ID_ENV": "ADH-009"})
        self.assertFalse(os.path.exists(self.items_dir))

    def test_failed_commit_leaves_backlog_and_wip_untouched(self):
        self.migrate(["--commit"], env={"MIGRATE_FAULT_CORRUPT_ID_ENV": "ADH-009"})
        self.assertEqual(self.read_json("backlog.json"), BACKLOG)
        self.assertEqual(self.read_json("wip.json"), WIP)

    def test_retry_after_a_failed_commit_succeeds_cleanly(self):
        first = self.migrate(["--commit"], env={"MIGRATE_FAULT_CORRUPT_ID_ENV": "ADH-009"})
        self.assertNotEqual(first.returncode, 0)
        second = self.migrate(["--commit"])
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.items_dir, "ADH-009.json")))

    # --- failure of the final atomic move itself (ADH-008 Gate B QA finding:
    #     the old per-file move loop wasn't atomic as a whole — a crash
    #     mid-loop could leave work/items/ with a real subset of items. A
    #     genuine OS-level failure of a single `os.replace` can't be
    #     reliably triggered black-box, hence the fault-injection hook,
    #     mirroring the existing MIGRATE_FAULT_CORRUPT_ID_ENV pattern.) ---

    def test_final_move_failure_leaves_no_items_dir_at_all(self):
        r = self.migrate(["--commit"], env={"MIGRATE_FAULT_FAIL_FINAL_MOVE_ENV": "1"})
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.items_dir))

    def test_final_move_failure_cleans_up_staging(self):
        self.migrate(["--commit"], env={"MIGRATE_FAULT_FAIL_FINAL_MOVE_ENV": "1"})
        self.assertFalse(os.path.exists(os.path.join(self.work_dir, ".items-migration-staging")))

    def test_final_move_failure_leaves_backlog_and_wip_untouched(self):
        self.migrate(["--commit"], env={"MIGRATE_FAULT_FAIL_FINAL_MOVE_ENV": "1"})
        self.assertEqual(self.read_json("backlog.json"), BACKLOG)
        self.assertEqual(self.read_json("wip.json"), WIP)

    def test_retry_after_a_final_move_failure_succeeds_cleanly(self):
        first = self.migrate(["--commit"], env={"MIGRATE_FAULT_FAIL_FINAL_MOVE_ENV": "1"})
        self.assertNotEqual(first.returncode, 0)
        second = self.migrate(["--commit"])
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.items_dir, "ADH-009.json")))


class Verify(MigrateItemsBase):
    def test_verify_passes_after_a_clean_commit(self):
        self.migrate(["--commit"])
        r = self.migrate(["--verify"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_verify_fails_if_an_item_file_is_missing(self):
        self.migrate(["--commit"])
        os.remove(os.path.join(self.items_dir, "ADH-009.json"))
        r = self.migrate(["--verify"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ADH-009", r.stderr)

    def test_verify_fails_if_an_item_file_was_hand_edited_since_commit(self):
        self.migrate(["--commit"])
        item = self.read_item("ADH-009")
        item["title"] = "hand-edited"
        with open(os.path.join(self.items_dir, "ADH-009.json"), "w") as fh:
            json.dump(item, fh)
        r = self.migrate(["--verify"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ADH-009", r.stderr)


class CommitCleanup(MigrateItemsBase):
    def test_renames_backlog_and_wip_to_bak(self):
        self.migrate(["--commit"])
        r = self.migrate(["--commit-cleanup"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.work_dir, "backlog.json")))
        self.assertFalse(os.path.exists(os.path.join(self.work_dir, "wip.json")))
        self.assertTrue(os.path.exists(os.path.join(self.work_dir, "backlog.json.pre-migration.bak")))
        self.assertTrue(os.path.exists(os.path.join(self.work_dir, "wip.json.pre-migration.bak")))

    def test_bak_files_preserve_original_content_never_deleted(self):
        self.migrate(["--commit"])
        self.migrate(["--commit-cleanup"])
        with open(os.path.join(self.work_dir, "backlog.json.pre-migration.bak")) as fh:
            self.assertEqual(json.load(fh), BACKLOG)

    def test_refuses_before_a_successful_commit(self):
        r = self.migrate(["--commit-cleanup"])
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(self.work_dir, "backlog.json")))

    def test_refuses_to_overwrite_an_existing_bak_file(self):
        self.migrate(["--commit"])
        self.migrate(["--commit-cleanup"])
        # re-seed backlog.json as if someone recreated it, then try again
        with open(os.path.join(self.work_dir, "backlog.json"), "w") as fh:
            json.dump(BACKLOG, fh)
        r = self.migrate(["--commit-cleanup"])
        self.assertNotEqual(r.returncode, 0)


class CliValidation(MigrateItemsBase):
    def test_rejects_multiple_modes_at_once(self):
        r = self.migrate(["--commit", "--verify"])
        self.assertNotEqual(r.returncode, 0)

    def test_rejects_unknown_flag(self):
        r = self.migrate(["--not-a-real-flag"])
        self.assertNotEqual(r.returncode, 0)

    def test_rejects_missing_work_sessions_repo(self):
        r = subprocess.run(
            [SCRIPT, "--work-sessions-repo", os.path.join(self.tmp, "does-not-exist")],
            capture_output=True, text=True,
        )
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
