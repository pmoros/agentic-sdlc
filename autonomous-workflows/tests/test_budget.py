"""Tests for the Phase-2 budget guard — the local, pre-flight enforcement of the
$200/month hard ceiling ("no surprises"). This is layer 4 of the defense-in-depth
budget design (gap-analysis §6 Hard budget); the gateway monthly cap is layer 1.

Run: python3 autonomous-workflows/tests/test_budget.py
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # autonomous-workflows/ on path
import budget  # noqa: E402

NOW = datetime(2026, 7, 15, tzinfo=timezone.utc)


def _rec(cost, started="2026-07-10T09:00:00+00:00"):
    return {"cost_usd": cost, "started_at": started}


class DefaultCapTest(unittest.TestCase):
    def test_monthly_cap_is_200(self):
        self.assertEqual(budget.MONTHLY_CAP_USD, 200.0)


class MonthToDateTest(unittest.TestCase):
    def test_only_current_calendar_month_counts(self):
        recs = [
            _rec(10.0, "2026-07-01T00:00:00+00:00"),  # July -> counts
            _rec(5.0, "2026-07-14T23:00:00+00:00"),   # July -> counts
            _rec(99.0, "2026-06-30T23:59:00+00:00"),  # June -> excluded
            _rec(99.0, "2026-08-01T00:00:00+00:00"),  # August -> excluded
        ]
        self.assertAlmostEqual(budget.month_to_date_spend(recs, NOW), 15.0, places=6)

    def test_missing_or_bad_timestamp_ignored(self):
        recs = [_rec(10.0, "2026-07-05T00:00:00+00:00"), {"cost_usd": 50.0, "started_at": None}]
        self.assertAlmostEqual(budget.month_to_date_spend(recs, NOW), 10.0, places=6)


class StatusThresholdsTest(unittest.TestCase):
    def test_ok_below_notice(self):
        self.assertEqual(budget.status(0.0), "ok")
        self.assertEqual(budget.status(99.99), "ok")

    def test_notice_at_50pct(self):
        self.assertEqual(budget.status(100.0), "notice")  # 0.50 * 200

    def test_warn_at_80pct(self):
        self.assertEqual(budget.status(160.0), "warn")     # 0.80 * 200

    def test_halt_at_90pct_and_above(self):
        self.assertEqual(budget.status(180.0), "halt")     # 0.90 * 200
        self.assertEqual(budget.status(200.0), "halt")
        self.assertEqual(budget.status(250.0), "halt")


class RemainingTest(unittest.TestCase):
    def test_remaining_and_fraction(self):
        self.assertAlmostEqual(budget.remaining(50.0), 150.0, places=6)
        self.assertAlmostEqual(budget.fraction(50.0), 0.25, places=6)


class CanStartTest(unittest.TestCase):
    def test_allows_run_with_headroom(self):
        # 100 spent + 10 est = 110, under the 0.9*200=180 reserve
        self.assertTrue(budget.can_start(spend=100.0, est_cost=10.0))

    def test_blocks_run_that_would_cross_reserve(self):
        # 175 + 10 = 185 > 180 reserve -> block (leave headroom below the hard cap)
        self.assertFalse(budget.can_start(spend=175.0, est_cost=10.0))

    def test_blocks_when_already_past_reserve(self):
        self.assertFalse(budget.can_start(spend=185.0, est_cost=0.0))

    def test_custom_cap(self):
        self.assertFalse(budget.can_start(spend=9.0, est_cost=2.0, cap=10.0))  # 11 > 9 reserve


class ReconcileSpendTest(unittest.TestCase):
    """§3.5 (must-fix 1): the gateway's /global/spend meter is authoritative;
    the local estimate is only a fallback when the gateway is unreachable."""

    def test_gateway_value_wins_when_higher(self):
        self.assertAlmostEqual(budget.reconcile_spend(local_estimate=5.0, gateway_spend=12.0), 12.0, places=6)

    def test_local_estimate_used_when_gateway_unavailable(self):
        self.assertAlmostEqual(budget.reconcile_spend(local_estimate=5.0, gateway_spend=None), 5.0, places=6)

    def test_local_estimate_wins_when_gateway_lags_behind(self):
        # fail-safe: never let a stale/low gateway read mask real local spend
        self.assertAlmostEqual(budget.reconcile_spend(local_estimate=8.0, gateway_spend=3.0), 8.0, places=6)


class FetchGlobalSpendTest(unittest.TestCase):
    """Network call isolated behind an injectable opener — no real HTTP in tests."""

    def test_parses_spend_field_from_response(self):
        class _Resp:
            def read(self):
                return b'{"spend": 1.4625, "max_budget": 200.0}'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        got = budget.fetch_global_spend("http://localhost:4000", "master-key", opener=lambda req: _Resp())
        self.assertAlmostEqual(got, 1.4625, places=6)

    def test_returns_none_on_any_error(self):
        def _boom(req):
            raise OSError("connection refused")
        self.assertIsNone(budget.fetch_global_spend("http://localhost:4000", "master-key", opener=_boom))

    def test_sends_bearer_auth_header(self):
        seen = {}

        class _Resp:
            def read(self):
                return b'{"spend": 0.0, "max_budget": 200.0}'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def _capture(req):
            seen["auth"] = req.get_header("Authorization")
            seen["url"] = req.full_url
            return _Resp()

        budget.fetch_global_spend("http://localhost:4000", "master-key", opener=_capture)
        self.assertEqual(seen["auth"], "Bearer master-key")
        self.assertEqual(seen["url"], "http://localhost:4000/global/spend")


class OvershootTest(unittest.TestCase):
    """review-2 nit A1: the gateway cap is a *soft* ceiling under concurrency —
    it can overshoot by ~one in-flight request per key. These helpers turn that
    into a concrete, testable sizing rule rather than "confirm it eventually
    blocks"."""

    def test_worst_case_overshoot_scales_with_concurrency(self):
        # 3 in-flight requests against a $0.10 key can each slip past the meter
        # before it updates -> worst case ~= 0.10 * 3
        self.assertAlmostEqual(budget.worst_case_overshoot(per_key_budget=0.10, concurrent_requests=3), 0.30, places=6)

    def test_safe_concurrency_cap_stays_under_reserve_headroom(self):
        # per-key budget $30, cap $200 -> spend-to-halt budget = $180 (cap x HALT);
        # the cap keeps worst-case overshoot under 50% of that ($90)
        n = budget.safe_concurrency_cap(per_key_budget=30.0, cap=200.0, safety_margin=0.5)
        self.assertLessEqual(30.0 * n, 200.0 * budget.HALT * 0.5)
        self.assertGreaterEqual(n, 1)

    def test_safe_concurrency_cap_never_zero_for_positive_budget(self):
        self.assertGreaterEqual(budget.safe_concurrency_cap(per_key_budget=190.0, cap=200.0), 1)


if __name__ == "__main__":
    unittest.main()
