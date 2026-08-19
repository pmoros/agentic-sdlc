"""Unit tests for the pure SESSIONS_STATE.md `Item`-column migration logic
(scripts/lib/migrate_sessions_state.py). ADH-011 SPEC.md sec.7.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import migrate_sessions_state as M  # noqa: E402

REAL_TABLE = """# Sessions State

Registry prose here, untouched by this migration.

**Status values:** `active | paused | done | stopped`
- `active` — running

| Session ID | Title | Tmux Session | Session Folder | Created | Last Change | Status |
|---|---|---|---|---|---|---|
| ADH-4 | Some title | cw-ADH-4 | sessions/ADH-4 | 2026-08-01 | 2026-08-01 | done |
| IO-234 | Another title | cw-IO-234 | sessions/IO-234 | 2026-08-13 | 2026-08-18 | active |

<!-- trailer comment, untouched -->
"""

PLACEHOLDER_TABLE = """# Sessions State

| Session ID | Title | Tmux Session | Session Folder | Created | Last Change | Status |
|---|---|---|---|---|---|---|
| _none yet_ | | | | | | |
"""


class AddItemColumn(unittest.TestCase):
    def test_header_gets_item_as_second_column(self):
        out = M.add_item_column(REAL_TABLE)
        header = next(l for l in out.splitlines() if l.startswith("| Session ID |"))
        self.assertEqual(header, "| Session ID | Item | Title | Tmux Session | Session Folder | Created | Last Change | Status |")

    def test_separator_row_gets_a_matching_extra_column(self):
        out = M.add_item_column(REAL_TABLE)
        lines = out.splitlines()
        header_i = next(i for i, l in enumerate(lines) if l.startswith("| Session ID |"))
        self.assertEqual(lines[header_i + 1], "|---|---|---|---|---|---|---|---|")

    def test_item_value_equals_own_session_id_for_normal_rows(self):
        out = M.add_item_column(REAL_TABLE)
        row = next(l for l in out.splitlines() if l.startswith("| ADH-4 |"))
        cells = [c.strip() for c in row.strip("|").split("|")]
        self.assertEqual(cells[0], "ADH-4")
        self.assertEqual(cells[1], "ADH-4")

    def test_every_real_row_gets_its_own_id_as_item(self):
        out = M.add_item_column(REAL_TABLE)
        for sid in ("ADH-4", "IO-234"):
            row = next(l for l in out.splitlines() if l.startswith(f"| {sid} |"))
            cells = [c.strip() for c in row.strip("|").split("|")]
            self.assertEqual(cells[1], sid)

    def test_placeholder_row_gets_empty_item_cell_not_the_placeholder_text(self):
        out = M.add_item_column(PLACEHOLDER_TABLE)
        row = next(l for l in out.splitlines() if l.startswith("| _none yet_ |"))
        cells = [c.strip() for c in row.strip("|").split("|")]
        self.assertEqual(cells[0], "_none yet_")
        self.assertEqual(cells[1], "")

    def test_preserves_non_table_prose_unchanged(self):
        out = M.add_item_column(REAL_TABLE)
        self.assertIn("Registry prose here, untouched by this migration.", out)
        self.assertIn("**Status values:** `active | paused | done | stopped`", out)
        self.assertIn("<!-- trailer comment, untouched -->", out)

    def test_row_count_unchanged(self):
        out = M.add_item_column(REAL_TABLE)
        self.assertEqual(
            len([l for l in out.splitlines() if l.startswith("|")]),
            len([l for l in REAL_TABLE.splitlines() if l.startswith("|")]),
        )

    def test_idempotent_second_call_is_a_no_op(self):
        once = M.add_item_column(REAL_TABLE)
        twice = M.add_item_column(once)
        self.assertEqual(once, twice)

    def test_no_table_found_returns_text_unchanged(self):
        text = "# Just prose\n\nNo table here.\n"
        self.assertEqual(M.add_item_column(text), text)


if __name__ == "__main__":
    unittest.main()
