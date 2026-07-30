"""Tests for the spend-report formatter — a concise one-line human-readable
budget status string built on top of the Phase-2 budget guard (budget.py).

Run: python3 scripts/tests/test_spend_report.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/ on path
import budget  # noqa: E402
import spend_report  # noqa: E402


class LevelTest(unittest.TestCase):
    def test_ok_level(self):
        line = spend_report.format_status(0.0)
        self.assertIn("ok", line)

    def test_notice_level(self):
        line = spend_report.format_status(100.0)  # 50% of default 200 cap
        self.assertIn("notice", line)

    def test_warn_level(self):
        line = spend_report.format_status(160.0)  # 80% of default 200 cap
        self.assertIn("warn", line)

    def test_halt_level(self):
        line = spend_report.format_status(180.0)  # 90% of default 200 cap
        self.assertIn("halt", line)


class FormattingTest(unittest.TestCase):
    def test_uses_default_cap_when_none(self):
        line = spend_report.format_status(50.0)
        self.assertIn("$200.00", line)

    def test_dollar_amounts_present(self):
        line = spend_report.format_status(50.0)
        self.assertIn("$50.00", line)
        self.assertIn("$200.00", line)

    def test_percent_used_present(self):
        line = spend_report.format_status(100.0)  # 100/200 = 50%
        self.assertIn("50.0%", line)

    def test_remaining_dollars_present(self):
        line = spend_report.format_status(160.0)  # 200-160 = 40 remaining
        self.assertIn("$40.00", line)

    def test_matches_budget_module_computations(self):
        spend = 77.0
        line = spend_report.format_status(spend)
        expected_level = budget.status(spend)
        expected_remaining = budget.remaining(spend)
        expected_pct = budget.fraction(spend) * 100
        self.assertIn(expected_level, line)
        self.assertIn(f"${expected_remaining:.2f}", line)
        self.assertIn(f"{expected_pct:.1f}%", line)


class CustomCapTest(unittest.TestCase):
    def test_custom_cap_changes_level_and_amounts(self):
        # 9 spent of a 10 cap -> 90% -> halt, $1.00 remaining
        line = spend_report.format_status(9.0, cap=10.0)
        self.assertIn("halt", line)
        self.assertIn("$9.00", line)
        self.assertIn("$10.00", line)
        self.assertIn("90.0%", line)
        self.assertIn("$1.00", line)

    def test_custom_cap_does_not_use_default(self):
        line = spend_report.format_status(1.0, cap=2.0)
        self.assertNotIn("$200.00", line)


if __name__ == "__main__":
    unittest.main()
