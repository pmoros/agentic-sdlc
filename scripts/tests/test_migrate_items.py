"""Unit tests for the pure migration logic (scripts/lib/migrate_items.py).

Tests the decision-making functions directly with plain dicts/strings — no
filesystem, no subprocess. The end-to-end wiring through migrate-items-v2.sh
(staging, --commit refusal/cleanup, atomic move, --commit-cleanup) is
covered in test_migrate_items_sh.py.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import migrate_items as M  # noqa: E402


class MergeSources(unittest.TestCase):
    def test_merges_backlog_and_wip_into_one_dict(self):
        backlog = {"A": {"title": "a", "status": "grooming"}}
        wip = {"B": {"title": "b", "status": "in progress"}}
        merged = M.merge_sources(backlog, wip)
        self.assertEqual(set(merged), {"A", "B"})

    def test_empty_sources_merge_to_empty(self):
        self.assertEqual(M.merge_sources({}, {}), {})

    def test_raises_on_id_present_in_both_backlog_and_wip(self):
        backlog = {"A": {"title": "a", "status": "grooming"}}
        wip = {"A": {"title": "a", "status": "in progress"}}
        with self.assertRaises(ValueError):
            M.merge_sources(backlog, wip)


class ParseSessionsState(unittest.TestCase):
    TABLE = """# Sessions State

| Session ID | Title | Tmux Session | Session Folder | Created | Last Change | Status |
|---|---|---|---|---|---|---|
| ADH-001-autonomous-workflows | Build a thing | cw-ADH-001 | sessions/ADH-001-autonomous-workflows | 2026-07-12 | 2026-08-02 | done |
| ADH-005-subscription-model-routing | Route models | cw-ADH-005 | sessions/ADH-005-subscription-model-routing | 2026-08-01 | 2026-08-01 | active |
"""

    def test_parses_data_rows_keyed_by_session_id(self):
        rows = M.parse_sessions_state(self.TABLE)
        self.assertEqual(set(rows), {
            "ADH-001-autonomous-workflows", "ADH-005-subscription-model-routing"})

    def test_row_fields(self):
        rows = M.parse_sessions_state(self.TABLE)
        row = rows["ADH-001-autonomous-workflows"]
        self.assertEqual(row["folder"], "sessions/ADH-001-autonomous-workflows")
        self.assertEqual(row["created"], "2026-07-12")
        self.assertEqual(row["last_change"], "2026-08-02")
        self.assertEqual(row["status"], "done")

    def test_skips_header_and_separator_rows(self):
        rows = M.parse_sessions_state(self.TABLE)
        self.assertNotIn("Session ID", rows)
        self.assertNotIn("---", rows)

    def test_skips_none_yet_placeholder_row(self):
        table = """| Session ID | Title | Tmux Session | Session Folder | Created | Last Change | Status |
|---|---|---|---|---|---|---|
| _none yet_ | | | | | | |
"""
        self.assertEqual(M.parse_sessions_state(table), {})

    def test_empty_text_yields_no_rows(self):
        self.assertEqual(M.parse_sessions_state(""), {})


class BuildSessionEntry(unittest.TestCase):
    def test_none_row_yields_none_entry(self):
        self.assertIsNone(M.build_session_entry("ADH-9", None))

    def test_active_row_has_null_closed(self):
        row = {"folder": "sessions/ADH-9", "created": "2026-08-01",
               "last_change": "2026-08-05", "status": "active"}
        entry = M.build_session_entry("ADH-9", row)
        self.assertEqual(entry["episode_id"], "ADH-9")
        self.assertEqual(entry["episode_number"], 1)
        self.assertEqual(entry["folder"], "sessions/ADH-9")
        self.assertEqual(entry["opened"], "2026-08-01T00:00:00Z")
        self.assertIsNone(entry["closed"])

    def test_paused_row_has_null_closed(self):
        row = {"folder": "sessions/ADH-9", "created": "2026-08-01",
               "last_change": "2026-08-05", "status": "paused"}
        entry = M.build_session_entry("ADH-9", row)
        self.assertIsNone(entry["closed"])

    def test_done_row_has_closed_timestamp(self):
        row = {"folder": "sessions/ADH-9", "created": "2026-08-01",
               "last_change": "2026-08-05", "status": "done"}
        entry = M.build_session_entry("ADH-9", row)
        self.assertEqual(entry["closed"], "2026-08-05T00:00:00Z")

    def test_stopped_row_has_closed_timestamp(self):
        row = {"folder": "sessions/ADH-9", "created": "2026-08-01",
               "last_change": "2026-08-05", "status": "stopped"}
        entry = M.build_session_entry("ADH-9", row)
        self.assertEqual(entry["closed"], "2026-08-05T00:00:00Z")


class MigrateItem(unittest.TestCase):
    def test_preserves_every_pre_existing_field(self):
        source = {
            "title": "t", "description": "d", "status": "ready",
            "priority": "Major", "scope": "M", "tickets": {"main-bug-tracking": "X-1"},
            "current_state": {"description": "d", "is_blocked": False},
            "history": [{"action": "a", "timestamp": "t", "by": "me"}],
            "roadmap": [{"step": "s", "owner": "me"}],
        }
        migrated = M.migrate_item("ADH-9", source, None)
        for key, value in source.items():
            self.assertEqual(migrated[key], value)

    def test_adds_id_field(self):
        migrated = M.migrate_item("ADH-9", {"title": "t", "status": "ready"}, None)
        self.assertEqual(migrated["id"], "ADH-9")

    def test_no_registry_row_yields_empty_sessions(self):
        migrated = M.migrate_item("ADH-9", {"title": "t", "status": "ready"}, None)
        self.assertEqual(migrated["sessions"], [])

    def test_registry_row_yields_single_first_episode_entry(self):
        row = {"folder": "sessions/ADH-9", "created": "2026-08-01",
               "last_change": "2026-08-05", "status": "done"}
        migrated = M.migrate_item("ADH-9", {"title": "t", "status": "done"}, row)
        self.assertEqual(len(migrated["sessions"]), 1)
        self.assertEqual(migrated["sessions"][0]["episode_id"], "ADH-9")

    def test_preserves_fields_the_documented_schema_does_not_mention(self):
        # Real backlog/wip.json data has drifted (started/work_items/resources
        # fields not in the SPEC's core list) -- migration must not drop them.
        source = {"title": "t", "status": "ready", "started": "16 August 2026",
                   "work_items": {"session": "sessions/ADH-9/"}, "resources": {}}
        migrated = M.migrate_item("ADH-9", source, None)
        self.assertEqual(migrated["started"], "16 August 2026")
        self.assertEqual(migrated["work_items"], {"session": "sessions/ADH-9/"})


class DiffItem(unittest.TestCase):
    def test_new_fields_are_id_and_sessions(self):
        source = {"title": "t", "status": "ready"}
        migrated = M.migrate_item("ADH-9", source, None)
        d = M.diff_item("ADH-9", source, migrated)
        self.assertEqual(d["new_fields"], ["id", "sessions"])

    def test_unchanged_fields_lists_every_source_field(self):
        source = {"title": "t", "status": "ready", "description": "d"}
        migrated = M.migrate_item("ADH-9", source, None)
        d = M.diff_item("ADH-9", source, migrated)
        self.assertEqual(d["unchanged_fields"], ["description", "status", "title"])


class VerifyItem(unittest.TestCase):
    def test_no_mismatches_when_migration_is_faithful(self):
        source = {"title": "t", "status": "ready", "history": [{"action": "a"}]}
        migrated = M.migrate_item("ADH-9", source, None)
        self.assertEqual(M.verify_item(source, migrated), [])

    def test_reports_every_field_that_differs(self):
        source = {"title": "t", "status": "ready", "description": "d"}
        migrated = {"title": "CHANGED", "status": "ready", "description": "ALSO CHANGED"}
        self.assertEqual(M.verify_item(source, migrated), ["title", "description"])

    def test_reports_a_field_missing_entirely_from_the_migrated_item(self):
        source = {"title": "t", "status": "ready"}
        migrated = {"title": "t"}
        self.assertEqual(M.verify_item(source, migrated), ["status"])


if __name__ == "__main__":
    unittest.main()
