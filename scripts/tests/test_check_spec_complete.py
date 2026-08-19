"""Unit tests for the pure Impact Analysis completeness-checking logic
(scripts/lib/check_spec_complete.py).

Tests the decision-making function directly against plain SPEC.md text — no
filesystem, no subprocess. The end-to-end wiring through
check-spec-complete.sh (CLI parsing, locating a session's SPEC.md) is covered
in test_check_spec_complete_sh.py.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import check_spec_complete as C  # noqa: E402

COMPLETE = """# Spec

## Approach

Some approach text.

## Impact analysis

- **Stakeholders:** who to notify or get approval from
- **Components:** services/repos/modules touched
- **Data dependencies:** schemas/datastores/queues read or written
- **Side effects:** anything outside the stated change surface (cost, other
  pipelines, shared infra)

## Test scenarios

- Given/when/then.
"""


class FindMissingFields(unittest.TestCase):
    def test_all_four_fields_present_and_non_empty_reports_nothing_missing(self):
        self.assertEqual(C.find_missing_fields(COMPLETE), [])

    def test_heading_absent_reports_all_four_fields_missing(self):
        text = "# Spec\n\n## Approach\n\nNo impact analysis section at all.\n"
        missing = C.find_missing_fields(text)
        self.assertEqual(
            set(missing),
            {"Stakeholders", "Components", "Data dependencies", "Side effects"},
        )

    def test_field_entirely_absent_from_section_is_reported_missing(self):
        text = COMPLETE.replace(
            "- **Side effects:** anything outside the stated change surface (cost, other\n"
            "  pipelines, shared infra)\n",
            "",
        )
        self.assertEqual(C.find_missing_fields(text), ["Side effects"])

    def test_field_present_but_empty_is_reported_missing(self):
        text = COMPLETE.replace(
            "- **Stakeholders:** who to notify or get approval from",
            "- **Stakeholders:**",
        )
        self.assertEqual(C.find_missing_fields(text), ["Stakeholders"])

    def test_field_present_but_only_whitespace_is_reported_missing(self):
        text = COMPLETE.replace(
            "- **Components:** services/repos/modules touched",
            "- **Components:**    ",
        )
        self.assertEqual(C.find_missing_fields(text), ["Components"])

    def test_multiple_missing_fields_are_all_reported(self):
        text = COMPLETE.replace(
            "- **Stakeholders:** who to notify or get approval from",
            "- **Stakeholders:**",
        ).replace(
            "- **Data dependencies:** schemas/datastores/queues read or written",
            "- **Data dependencies:**",
        )
        self.assertEqual(C.find_missing_fields(text), ["Stakeholders", "Data dependencies"])

    def test_section_scoped_to_next_heading_a_later_heading_field_does_not_count(self):
        # A bullet that merely LOOKS like a field, but lives under a later
        # heading, must not satisfy the Impact analysis section's own field.
        text = COMPLETE.replace(
            "- **Stakeholders:** who to notify or get approval from\n", ""
        ).replace(
            "## Test scenarios\n",
            "## Test scenarios\n\n- **Stakeholders:** this is not the impact analysis field\n",
        )
        self.assertEqual(C.find_missing_fields(text), ["Stakeholders"])

    def test_ignores_field_order_in_the_source_document(self):
        text = COMPLETE.replace(
            "- **Stakeholders:** who to notify or get approval from\n"
            "- **Components:** services/repos/modules touched\n",
            "- **Components:** services/repos/modules touched\n"
            "- **Stakeholders:** who to notify or get approval from\n",
        )
        self.assertEqual(C.find_missing_fields(text), [])


if __name__ == "__main__":
    unittest.main()
