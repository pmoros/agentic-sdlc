"""Unit tests for the pure view-partitioning logic
(scripts/lib/regenerate_views.py).

Tests the decision-making function directly with plain dicts — no
filesystem, no subprocess. The end-to-end wiring through regenerate-views.sh
(directory scan, --check mode, file writes) is covered in
test_regenerate_views_sh.py.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import regenerate_views as R  # noqa: E402


def item(status, title="t", **extra):
    return {"title": title, "status": status, **extra}


class PartitionByStatus(unittest.TestCase):
    def test_grooming_and_ready_land_in_backlog(self):
        items = {"A": item("grooming"), "B": item("ready")}
        views = R.partition_items(items)
        self.assertEqual(set(views["backlog"]), {"A", "B"})
        self.assertEqual(views["wip"], {})
        self.assertEqual(views["archive"], {})

    def test_in_progress_on_hold_in_review_land_in_wip(self):
        items = {"A": item("in progress"), "B": item("on hold"), "C": item("in review")}
        views = R.partition_items(items)
        self.assertEqual(set(views["wip"]), {"A", "B", "C"})
        self.assertEqual(views["backlog"], {})
        self.assertEqual(views["archive"], {})

    def test_done_lands_in_archive(self):
        items = {"A": item("done")}
        views = R.partition_items(items)
        self.assertEqual(set(views["archive"]), {"A"})
        self.assertEqual(views["backlog"], {})
        self.assertEqual(views["wip"], {})

    def test_unknown_status_raises_rather_than_silently_dropping_the_item(self):
        items = {"A": item("bogus-status")}
        with self.assertRaises(ValueError):
            R.partition_items(items)

    def test_every_partition_present_even_when_empty(self):
        views = R.partition_items({})
        self.assertEqual(views, {"backlog": {}, "wip": {}, "archive": {}})


class ViewEntryShape(unittest.TestCase):
    def test_entry_has_title_and_status(self):
        items = {"A": item("ready", title="My title")}
        entry = R.partition_items(items)["backlog"]["A"]
        self.assertEqual(entry["title"], "My title")
        self.assertEqual(entry["status"], "ready")

    def test_entry_includes_priority_and_scope_when_present(self):
        items = {"A": item("ready", priority="Major", scope="M")}
        entry = R.partition_items(items)["backlog"]["A"]
        self.assertEqual(entry["priority"], "Major")
        self.assertEqual(entry["scope"], "M")

    def test_entry_omits_priority_and_scope_when_absent(self):
        items = {"A": item("ready")}
        entry = R.partition_items(items)["backlog"]["A"]
        self.assertNotIn("priority", entry)
        self.assertNotIn("scope", entry)

    def test_entry_is_lightweight_not_the_full_item(self):
        items = {"A": item("ready", history=[{"action": "x"}], sessions=[{"episode_id": "A"}],
                            description="long description text", current_state={"is_blocked": False})}
        entry = R.partition_items(items)["backlog"]["A"]
        self.assertNotIn("history", entry)
        self.assertNotIn("sessions", entry)
        self.assertNotIn("description", entry)
        self.assertNotIn("current_state", entry)


if __name__ == "__main__":
    unittest.main()
