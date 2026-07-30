"""Tests for the subscription-lane window guard (ADH-003 subscription pivot,
design rev 2.1 D3/D4 + Contracts). The advisory layer of the two-layer
reactive window model: per-tier rolling-window burn ledger over run-records,
committed (in-flight) burn from the fan-out manifest, strict limit-error
parsing (the authoritative layer's detector), and pre-flight admission vs
the {5h, 7d, 7d_sonnet} allotments.

Run: python3 scripts/tests/test_window_guard.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/ on path
import window_guard  # noqa: E402

NOW = "2026-07-30T12:00:00+00:00"


def _rec(cost, started, model="claude-sonnet-5", lane="subscription",
         cost_basis="estimated", **extra):
    r = {"cost_usd": cost, "started_at": started, "model": model,
         "lane": lane, "cost_basis": cost_basis}
    r.update(extra)
    return r


def _agent(status="running", lane="subscription", model="claude-sonnet-5",
           window_est_usd=1.0, **extra):
    a = {"status": status, "lane": lane, "model": model,
         "window_est_usd": window_est_usd}
    a.update(extra)
    return a


class TierTest(unittest.TestCase):
    def test_model_families(self):
        self.assertEqual(window_guard.tier({"model": "claude-opus-4-8"}), "opus")
        self.assertEqual(window_guard.tier({"model": "claude-sonnet-5"}), "sonnet")
        self.assertEqual(window_guard.tier({"model": "claude-haiku-4-5-20251001"}), "haiku")

    def test_unknown_or_missing_model_is_other(self):
        self.assertEqual(window_guard.tier({"model": "deepseek-v3"}), "other")
        self.assertEqual(window_guard.tier({}), "other")


class WindowBurnTest(unittest.TestCase):
    def test_only_subscription_estimated_records_count(self):
        recs = [
            _rec(1.0, "2026-07-30T11:00:00+00:00"),                              # counts
            _rec(9.0, "2026-07-30T11:00:00+00:00", lane="api", cost_basis="billed"),  # api -> no
            _rec(9.0, "2026-07-30T11:00:00+00:00", lane=None, cost_basis=None),  # legacy -> no
        ]
        # legacy records have neither key at all
        del recs[2]["lane"]; del recs[2]["cost_basis"]
        self.assertAlmostEqual(
            window_guard.window_burn(recs, NOW, window_guard.WINDOW_5H), 1.0, places=6)

    def test_rolling_window_bounds(self):
        recs = [
            _rec(1.0, "2026-07-30T08:00:00+00:00"),  # 4h ago -> in 5h window
            _rec(2.0, "2026-07-30T06:59:00+00:00"),  # ~5h01m ago -> out
            _rec(4.0, "2026-07-29T12:30:00+00:00"),  # ~23.5h ago -> out of 5h, in 7d
        ]
        self.assertAlmostEqual(
            window_guard.window_burn(recs, NOW, window_guard.WINDOW_5H), 1.0, places=6)
        self.assertAlmostEqual(
            window_guard.window_burn(recs, NOW, window_guard.WINDOW_7D), 7.0, places=6)

    def test_tier_filter(self):
        recs = [
            _rec(1.0, "2026-07-30T11:00:00+00:00", model="claude-sonnet-5"),
            _rec(2.0, "2026-07-30T11:00:00+00:00", model="claude-opus-4-8"),
        ]
        self.assertAlmostEqual(
            window_guard.window_burn(recs, NOW, window_guard.WINDOW_5H, tier="sonnet"),
            1.0, places=6)

    def test_bad_timestamp_ignored(self):
        recs = [_rec(1.0, "2026-07-30T11:00:00+00:00"), _rec(9.0, None)]
        self.assertAlmostEqual(
            window_guard.window_burn(recs, NOW, window_guard.WINDOW_5H), 1.0, places=6)


class CommittedBurnTest(unittest.TestCase):
    def test_sums_running_subscription_agents_only(self):
        manifest = {"agents": [
            _agent(status="running", window_est_usd=1.5),
            _agent(status="running", window_est_usd=2.0),
            _agent(status="queued", window_est_usd=9.0),    # not running -> no
            _agent(status="done", window_est_usd=9.0),      # not running -> no
            _agent(status="running", lane="api", window_est_usd=9.0),  # api -> no
        ]}
        self.assertAlmostEqual(window_guard.committed_burn(manifest), 3.5, places=6)

    def test_missing_est_falls_back_to_default(self):
        a = _agent(status="running"); del a["window_est_usd"]
        self.assertAlmostEqual(
            window_guard.committed_burn({"agents": [a]}, default_est_usd=0.75),
            0.75, places=6)

    def test_tier_filter_uses_agent_model(self):
        manifest = {"agents": [
            _agent(status="running", model="claude-sonnet-5", window_est_usd=1.0),
            _agent(status="running", model="claude-opus-4-8", window_est_usd=2.0),
        ]}
        self.assertAlmostEqual(
            window_guard.committed_burn(manifest, tier="sonnet"), 1.0, places=6)

    def test_agents_dict_form_accepted(self):
        manifest = {"agents": {
            "t1": _agent(status="running", window_est_usd=1.0),
            "t2": _agent(status="running", window_est_usd=0.5),
        }}
        self.assertAlmostEqual(window_guard.committed_burn(manifest), 1.5, places=6)


SESSION_MSG = "You've hit your session limit · resets 2026-07-30T15:00:00+00:00"
WEEKLY_MSG = "You've hit your weekly limit · resets 2026-08-03T00:00:00+00:00"


class ParseLimitErrorTest(unittest.TestCase):
    def test_session_limit_parsed(self):
        hit = window_guard.parse_limit_error(SESSION_MSG, "stderr")
        self.assertEqual(hit["kind"], "session")
        self.assertEqual(hit["resets_at"], "2026-07-30T15:00:00+00:00")
        self.assertEqual(hit["channel"], "stderr")
        self.assertIn("session limit", hit["matched_text"])

    def test_weekly_limit_parsed(self):
        hit = window_guard.parse_limit_error(WEEKLY_MSG, "result_error")
        self.assertEqual(hit["kind"], "weekly")
        self.assertEqual(hit["resets_at"], "2026-08-03T00:00:00+00:00")

    def test_unparseable_reset_time_yields_null_resets_at(self):
        hit = window_guard.parse_limit_error(
            "You've hit your session limit · resets 3pm", "stderr")
        self.assertEqual(hit["kind"], "session")
        self.assertIsNone(hit["resets_at"])

    def test_non_matching_error_is_none(self):
        self.assertIsNone(window_guard.parse_limit_error("500 upstream error", "stderr"))

    def test_loose_mentions_do_not_match(self):
        # A task quoting the concept must not trip the strict parser (D3.2).
        self.assertIsNone(window_guard.parse_limit_error(
            "the doc discusses what happens when you hit your session limit", "stderr"))
        self.assertIsNone(window_guard.parse_limit_error(
            "rate limit exceeded, resets soon", "stderr"))


class CanStartTest(unittest.TestCase):
    def setUp(self):
        self.allot = {"5h": 5.0, "7d": 40.0, "7d_sonnet": 25.0}
        self.empty = {"agents": []}

    def test_under_all_windows(self):
        recs = [_rec(1.0, "2026-07-30T11:00:00+00:00")]
        self.assertTrue(window_guard.can_start(recs, self.empty, NOW, self.allot))

    def test_5h_exceeded_by_completed_burn(self):
        recs = [_rec(5.5, "2026-07-30T11:00:00+00:00")]
        self.assertFalse(window_guard.can_start(recs, self.empty, NOW, self.allot))

    def test_committed_burn_pushes_over(self):
        recs = [_rec(4.0, "2026-07-30T11:00:00+00:00")]
        manifest = {"agents": [_agent(status="running", window_est_usd=1.5)]}
        self.assertFalse(window_guard.can_start(recs, manifest, NOW, self.allot))

    def test_sonnet_weekly_cap_trips_alone(self):
        # all-models 7d fine (40), sonnet-specific (25) exceeded -> False (F1)
        recs = [_rec(26.0, "2026-07-28T12:00:00+00:00", model="claude-sonnet-5")]
        self.assertFalse(window_guard.can_start(recs, self.empty, NOW, self.allot))
        # same burn on opus passes the sonnet cap (and stays under 5h/7d)
        recs2 = [_rec(26.0, "2026-07-28T12:00:00+00:00", model="claude-opus-4-8")]
        self.assertTrue(window_guard.can_start(recs2, self.empty, NOW, self.allot))

    def test_api_lane_records_do_not_count(self):
        recs = [_rec(99.0, "2026-07-30T11:00:00+00:00", lane="api", cost_basis="billed")]
        self.assertTrue(window_guard.can_start(recs, self.empty, NOW, self.allot))


class NextResumeAtTest(unittest.TestCase):
    def test_earliest_future_reset_wins(self):
        recs = [
            _rec(0.1, "2026-07-30T10:00:00+00:00", outcome="paused_rate_limit",
                 limit={"kind": "session", "resets_at": "2026-07-30T16:00:00+00:00"}),
            _rec(0.1, "2026-07-30T10:30:00+00:00", outcome="paused_rate_limit",
                 limit={"kind": "session", "resets_at": "2026-07-30T14:00:00+00:00"}),
        ]
        self.assertEqual(window_guard.next_resume_at(recs, NOW),
                         "2026-07-30T14:00:00+00:00")

    def test_past_resets_and_null_skipped(self):
        recs = [
            _rec(0.1, "2026-07-30T06:00:00+00:00", outcome="paused_rate_limit",
                 limit={"kind": "session", "resets_at": "2026-07-30T11:00:00+00:00"}),  # past
            _rec(0.1, "2026-07-30T10:00:00+00:00", outcome="paused_rate_limit",
                 limit={"kind": "weekly", "resets_at": None}),                          # null
            _rec(0.1, "2026-07-30T10:00:00+00:00", outcome="review_ready"),             # not paused
        ]
        self.assertIsNone(window_guard.next_resume_at(recs, NOW))


if __name__ == "__main__":
    unittest.main()
