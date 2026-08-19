"""Unit tests for validate_parent_link (scripts/lib/define_work_item.py).

Unlike test_define_work_item.py (plain dicts, no I/O — see its own
docstring), this function genuinely reads other items' files off disk to
check the one-level-deep invariant, so it gets its own I/O-touching test
file against a real tmp directory. ADH-012 SPEC.md sec.4.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import define_work_item as D  # noqa: E402


class ValidateParentLink(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.items_dir = self._tmp.name

    def write(self, item_id, **fields):
        item = {"id": item_id, "title": "t", "status": "grooming"}
        item.update(fields)
        with open(os.path.join(self.items_dir, f"{item_id}.json"), "w") as fh:
            json.dump(item, fh)

    def test_valid_link_passes(self):
        self.write("ADH-20")
        self.assertIsNone(D.validate_parent_link(self.items_dir, "ADH-21", "ADH-20"))

    def test_refuses_self_parent(self):
        with self.assertRaises(ValueError):
            D.validate_parent_link(self.items_dir, "ADH-20", "ADH-20")

    def test_refuses_nonexistent_parent_target(self):
        with self.assertRaises(ValueError):
            D.validate_parent_link(self.items_dir, "ADH-21", "ADH-999-does-not-exist")

    def test_refuses_when_target_parent_already_has_a_parent(self):
        # ADH-20 is itself a child of ADH-10 -- linking ADH-21 under ADH-20
        # would make a 2-level chain.
        self.write("ADH-10")
        self.write("ADH-20", parent_id="ADH-10")
        with self.assertRaises(ValueError):
            D.validate_parent_link(self.items_dir, "ADH-21", "ADH-20")

    def test_refuses_when_item_is_already_a_parent_to_something_else(self):
        # ADH-20 already has a child (ADH-21) -- it can't also become
        # someone else's child.
        self.write("ADH-20")
        self.write("ADH-21", parent_id="ADH-20")
        self.write("ADH-99")
        with self.assertRaises(ValueError):
            D.validate_parent_link(self.items_dir, "ADH-20", "ADH-99")

    def test_reparenting_an_existing_child_to_a_different_parent_is_allowed(self):
        # Moving a sub-item from one epic to another is a normal operation,
        # not a violation of the one-level rule.
        self.write("ADH-20")
        self.write("ADH-30")
        self.write("ADH-21", parent_id="ADH-20")
        self.assertIsNone(D.validate_parent_link(self.items_dir, "ADH-21", "ADH-30"))

    def test_a_fresh_not_yet_created_item_can_still_be_linked(self):
        # define-work-item.sh supports creating a brand-new item and
        # --parent in the same call -- item_id need not already exist.
        self.write("ADH-20")
        self.assertIsNone(D.validate_parent_link(self.items_dir, "ADH-brand-new", "ADH-20"))


class ValidatePromote(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.items_dir = self._tmp.name

    def write(self, item_id, **fields):
        item = {"id": item_id, "title": "t", "status": "grooming"}
        item.update(fields)
        with open(os.path.join(self.items_dir, f"{item_id}.json"), "w") as fh:
            json.dump(item, fh)

    def test_passes_when_item_has_a_parent_to_clear(self):
        self.write("ADH-21", parent_id="ADH-20")
        self.assertIsNone(D.validate_promote(self.items_dir, "ADH-21"))

    def test_refuses_when_item_has_no_parent(self):
        self.write("ADH-21")
        with self.assertRaises(ValueError):
            D.validate_promote(self.items_dir, "ADH-21")

    def test_refuses_when_item_does_not_exist(self):
        with self.assertRaises(ValueError):
            D.validate_promote(self.items_dir, "ADH-nonexistent")


if __name__ == "__main__":
    unittest.main()
