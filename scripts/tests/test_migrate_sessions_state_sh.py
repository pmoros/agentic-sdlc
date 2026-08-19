"""End-to-end tests for scripts/migrate-sessions-state-episode-column.sh --
dry-run/commit/verify over a real SESSIONS_STATE.md file.

Pure transformation logic is covered in test_migrate_sessions_state.py;
this file covers only what a subprocess/filesystem test can.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, script, make_work_sessions_repo, TempRepoCase  # noqa: E402

SCRIPT = script("migrate-sessions-state-episode-column.sh")


class MigrateSessionsStateSh(TempRepoCase):
    def setUp(self):
        super().setUp()
        self.ws = make_work_sessions_repo(self.tmp)
        self.state = os.path.join(self.ws, "SESSIONS_STATE.md")
        # Seed two real rows (pre-migration 7-column shape), matching what
        # the real live SESSIONS_STATE.md looks like before this migration.
        with open(self.state, "w") as fh:
            fh.write(
                "# Sessions State\n\n"
                "| Session ID | Title | Tmux Session | Session Folder | Created | Last Change | Status |\n"
                "|---|---|---|---|---|---|---|\n"
                "| ADH-4 | Some title | cw-ADH-4 | sessions/ADH-4 | 2026-08-01 | 2026-08-01 | done |\n"
                "| IO-234 | Another title | cw-IO-234 | sessions/IO-234 | 2026-08-13 | 2026-08-18 | active |\n"
            )

    def m(self, extra=()):
        return run([SCRIPT, "--work-sessions-repo", self.ws, *extra], check=False)

    def test_dry_run_does_not_write(self):
        before = open(self.state).read()
        r = self.m(["--dry-run"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(open(self.state).read(), before)

    def test_commit_adds_item_column_and_backs_up_original(self):
        before = open(self.state).read()
        r = self.m(["--commit"])
        self.assertEqual(r.returncode, 0, r.stderr)

        after = open(self.state).read()
        self.assertIn("| Session ID | Item | Title |", after)
        self.assertIn("| ADH-4 | ADH-4 |", after)
        self.assertIn("| IO-234 | IO-234 |", after)

        backups = [f for f in os.listdir(self.ws) if f.startswith("SESSIONS_STATE.md.bak.")]
        self.assertEqual(len(backups), 1)
        self.assertEqual(open(os.path.join(self.ws, backups[0])).read(), before)

    def test_commit_preserves_the_trailing_newline(self):
        # Regression: routing the migrated content through a bash $(...)
        # capture on the write path silently stripped the file's final
        # newline (command substitution always strips trailing newlines).
        self.assertTrue(open(self.state).read().endswith("\n"))
        self.assertEqual(self.m(["--commit"]).returncode, 0)
        self.assertTrue(open(self.state).read().endswith("\n"))

    def test_commit_is_idempotent(self):
        self.assertEqual(self.m(["--commit"]).returncode, 0)
        once = open(self.state).read()
        r2 = self.m(["--commit"])
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("already migrated", r2.stderr.lower())
        self.assertEqual(open(self.state).read(), once)

    def test_verify_fails_before_commit(self):
        r = self.m(["--verify"])
        self.assertNotEqual(r.returncode, 0)

    def test_verify_passes_after_commit(self):
        self.assertEqual(self.m(["--commit"]).returncode, 0)
        r = self.m(["--verify"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_verify_ignores_prose_lines_that_merely_contain_a_pipe(self):
        # Regression: a legend line like the real file's
        # "**Status values:** `active | paused | done | stopped`" is not a
        # table row and must not be parsed as one by --verify.
        with open(self.state) as fh:
            content = fh.read()
        content = content.replace(
            "# Sessions State\n\n",
            "# Sessions State\n\n**Status values:** `active | paused | done | stopped`\n\n")
        with open(self.state, "w") as fh:
            fh.write(content)
        self.assertEqual(self.m(["--commit"]).returncode, 0)
        r = self.m(["--verify"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_verify_catches_a_mismatched_item_cell(self):
        self.assertEqual(self.m(["--commit"]).returncode, 0)
        content = open(self.state).read().replace(
            "| ADH-4 | ADH-4 |", "| ADH-4 | WRONG-ID |")
        with open(self.state, "w") as fh:
            fh.write(content)
        r = self.m(["--verify"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("MISMATCH", r.stderr)


if __name__ == "__main__":
    unittest.main()
