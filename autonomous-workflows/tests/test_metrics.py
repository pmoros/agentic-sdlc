"""Tests for the autonomous-workflows evaluation metrics harness.

Runner-agnostic: plain unittest, no pytest fixtures (mirrors the agentic-sdlc
Script Testing Standard). Run with:
    python3 -m unittest discover -s autonomous-workflows/tests -t autonomous-workflows
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # autonomous-workflows/ on path
import metrics  # noqa: E402


def _rec(**over):
    """A minimal valid run-record; override fields per test."""
    base = {
        "run_id": "r1", "session_id": "ADH-001", "task_id": "t1",
        "agent_id": "agent-ADH-001-t1", "role": "coder", "model": "claude-sonnet-5",
        "started_at": "2026-07-12T10:00:00+00:00", "ended_at": "2026-07-12T10:05:00+00:00",
        "first_diff_at": "2026-07-12T10:02:00+00:00", "outcome": "review_ready",
        "tokens": {"input": 1000, "output": 500, "cache_read": 2000, "cache_write": 0},
        "cost_usd": 0.0, "turns": 3, "tool_calls": 7,
        "tests": {"ran": True, "passed": True, "count": 4},
        "doctrine": {"test_before_impl": True, "conventional_commits": True},
        "human": {"input_requests": 0, "steers": 0, "approvals": 1, "answer_latencies_s": []},
        "guardrail_violations": 0,
    }
    base.update(over)
    return base


class ComputeCostTest(unittest.TestCase):
    def test_input_output_and_cache_read_multiplier(self):
        # sonnet-5: in=$3, out=$15/1M; cache_read = 0.1x input
        # (1000*3 + 500*15 + 2000*0.1*3)/1e6 = (3000+7500+600)/1e6 = 0.0111
        cost = metrics.compute_cost(
            {"input": 1000, "output": 500, "cache_read": 2000, "cache_write": 0},
            "claude-sonnet-5",
        )
        self.assertAlmostEqual(cost, 0.0111, places=6)

    def test_cache_write_multiplier(self):
        # cache_write = 1.25x input; opus-4-8 input $5/1M -> 1000*1.25*5/1e6 = 0.00625
        cost = metrics.compute_cost(
            {"input": 0, "output": 0, "cache_read": 0, "cache_write": 1000},
            "claude-opus-4-8",
        )
        self.assertAlmostEqual(cost, 0.00625, places=6)

    def test_unknown_model_raises(self):
        with self.assertRaises(KeyError):
            metrics.compute_cost({"input": 1}, "no-such-model")


class AggregateTest(unittest.TestCase):
    def setUp(self):
        self.records = [
            _rec(run_id="a", outcome="review_ready",
                 human={"input_requests": 0, "steers": 0, "approvals": 1, "answer_latencies_s": []}),
            _rec(run_id="b", outcome="changes_requested", model="claude-opus-4-8",
                 tokens={"input": 2000, "output": 1000, "cache_read": 0, "cache_write": 0},
                 tests={"ran": True, "passed": False, "count": 3},
                 human={"input_requests": 2, "steers": 1, "approvals": 0, "answer_latencies_s": [30, 90]}),
            _rec(run_id="c", outcome="failed", model="claude-haiku-4-5",
                 first_diff_at=None,
                 tokens={"input": 1000, "output": 500, "cache_read": 0, "cache_write": 0},
                 tests={"ran": False, "passed": False, "count": 0},
                 guardrail_violations=0),
        ]
        self.m = metrics.aggregate(self.records)

    def test_completed_counts_reviewed_not_failed(self):
        # review_ready + changes_requested reached Final Review; failed did not
        self.assertEqual(self.m["completed_tasks"], 2)

    def test_cost_per_completed_task_is_total_over_completed(self):
        total = sum(metrics.compute_cost(r["tokens"], r["model"]) for r in self.records)
        self.assertAlmostEqual(self.m["total_cost_usd"], total, places=6)
        self.assertAlmostEqual(self.m["cost_per_completed_task"], total / 2, places=6)

    def test_cache_hit_rate(self):
        # only record 'a' has cache_read=2000, input=1000 across a/b/c inputs=1000+2000+1000=4000
        # cache_read total=2000 -> 2000/(4000+2000)=0.3333
        self.assertAlmostEqual(self.m["cache_hit_rate"], 2000 / 6000, places=4)

    def test_unattended_completion_rate(self):
        # among reviewed (a,b): a has 0 input_requests, b has 2 -> 1/2
        self.assertAlmostEqual(self.m["unattended_completion_rate"], 0.5, places=6)

    def test_test_pass_rate_over_runs_that_ran_tests(self):
        # tests ran on a(pass) and b(fail); c didn't run -> 1/2
        self.assertAlmostEqual(self.m["test_pass_rate"], 0.5, places=6)

    def test_change_request_rate(self):
        # reviewed=2, changes_requested=1 -> 0.5
        self.assertAlmostEqual(self.m["change_request_rate"], 0.5, places=6)

    def test_guardrail_violations_total_zero(self):
        self.assertEqual(self.m["guardrail_violations_total"], 0)

    def test_model_mix_present_for_each_model(self):
        self.assertIn("claude-sonnet-5", self.m["model_mix"])
        self.assertIn("claude-opus-4-8", self.m["model_mix"])
        self.assertAlmostEqual(sum(self.m["model_mix"].values()), 1.0, places=6)

    def test_time_to_first_diff_ignores_nulls(self):
        # a and b have first_diff_at 2 min after start = 120s each; c is null
        self.assertAlmostEqual(self.m["mean_time_to_first_diff_s"], 120.0, places=6)


class GatesTest(unittest.TestCase):
    def test_phase2_fails_on_guardrail_violation(self):
        recs = [_rec(guardrail_violations=1)]
        gates = metrics.evaluate_gates(metrics.aggregate(recs), "phase2")
        self.assertFalse(gates["guardrail_zero"])
        self.assertFalse(gates["passed"])

    def test_phase2_passes_clean(self):
        recs = [_rec()]  # review_ready, tests passed, 0 violations, cost>0
        gates = metrics.evaluate_gates(metrics.aggregate(recs), "phase2")
        self.assertTrue(gates["guardrail_zero"])
        self.assertTrue(gates["passed"])


class StageMetricsTest(unittest.TestCase):
    def test_pass_rate_per_stage(self):
        recs = [
            {"stage": "qa", "outcome": "review_ready"},
            {"stage": "qa", "outcome": "failed"},
            {"stage": "design", "outcome": "review_ready"},
        ]
        sm = metrics.stage_metrics(recs)
        self.assertEqual(sm["qa"]["count"], 2)
        self.assertAlmostEqual(sm["qa"]["pass_rate"], 0.5, places=6)
        self.assertEqual(sm["design"]["count"], 1)
        self.assertAlmostEqual(sm["design"]["pass_rate"], 1.0, places=6)

    def test_records_without_stage_grouped_as_unstaged(self):
        sm = metrics.stage_metrics([{"outcome": "merged"}])
        self.assertIn("unstaged", sm)
        self.assertEqual(sm["unstaged"]["count"], 1)


class LoadRecordsTest(unittest.TestCase):
    def test_reads_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "runs.jsonl"
            p.write_text("\n".join(json.dumps(_rec(run_id=str(i))) for i in range(3)) + "\n")
            recs = metrics.load_records(str(p))
            self.assertEqual(len(recs), 3)


class LaneCostSplitTest(unittest.TestCase):
    """ADH-003 subscription pivot, design rev 2.1 D6: billed/estimated split,
    legacy default, per-lane aggregation, paused-record denominators."""

    def setUp(self):
        legacy = _rec(run_id="legacy")  # no lane/cost_basis, cost_usd 0.0
        del_keys = ()  # legacy fixture already lacks lane/cost_basis
        api = _rec(run_id="api", lane="api", cost_basis="billed", cost_usd=1.07)
        sub = _rec(run_id="sub", lane="subscription", cost_basis="estimated",
                   cost_usd=0.5)
        self.legacy_computed = metrics.compute_cost(legacy["tokens"], legacy["model"])
        self.records = [legacy, api, sub]
        self.m = metrics.aggregate(self.records)

    def test_legacy_defaults_to_billed_with_computed_fallback(self):
        # legacy record: cost_basis missing -> "billed"; cost_usd 0.0 -> falls
        # back to token-computed cost (preserves the pre-pivot invariant)
        self.assertAlmostEqual(
            self.m["billed_cost_usd"], self.legacy_computed + 1.07, places=6)

    def test_estimated_and_savings(self):
        self.assertAlmostEqual(self.m["estimated_cost_usd"], 0.5, places=6)
        self.assertAlmostEqual(self.m["estimated_savings_usd"], 0.5, places=6)

    def test_total_is_billed_plus_estimated(self):
        self.assertAlmostEqual(
            self.m["total_cost_usd"],
            self.m["billed_cost_usd"] + self.m["estimated_cost_usd"], places=6)

    def test_lanes_split_and_legacy_grouped_as_api(self):
        self.assertEqual(self.m["lanes"]["api"]["runs"], 2)  # legacy + api
        self.assertEqual(self.m["lanes"]["subscription"]["runs"], 1)
        self.assertAlmostEqual(
            self.m["lanes"]["subscription"]["cost_usd"], 0.5, places=6)

    def test_lane_coverage_fraction(self):
        self.assertAlmostEqual(self.m["lane_coverage"], 2 / 3, places=6)


class PausedRecordTest(unittest.TestCase):
    def test_paused_excluded_from_rate_denominators(self):
        recs = [
            _rec(run_id="ok", lane="subscription", cost_basis="estimated"),
            _rec(run_id="paused", lane="subscription", cost_basis="estimated",
                 outcome="paused_rate_limit", cost_usd=0.2,
                 tests={"ran": True, "passed": False, "count": 1},
                 limit={"kind": "session", "resets_at": None}),
        ]
        m = metrics.aggregate(recs)
        self.assertEqual(m["runs"], 2)
        self.assertEqual(m["runs_paused"], 1)
        # the paused record's failing test run must not drag the pass rate
        self.assertAlmostEqual(m["test_pass_rate"], 1.0, places=6)
        # but its burn is real and counts in the cost/window ledger side
        self.assertGreater(m["estimated_cost_usd"], 0.0)

    def test_paused_excluded_from_stage_pass_rates(self):
        sm = metrics.stage_metrics([
            {"stage": "qa", "outcome": "review_ready"},
            {"stage": "qa", "outcome": "paused_rate_limit"},
        ])
        self.assertEqual(sm["qa"]["count"], 1)          # terminal only
        self.assertAlmostEqual(sm["qa"]["pass_rate"], 1.0, places=6)
        self.assertEqual(sm["qa"]["paused"], 1)


class SubscriptionPivotGateTest(unittest.TestCase):
    def test_gate_passes_with_subscription_completion(self):
        recs = [
            _rec(run_id="s1", lane="subscription", cost_basis="estimated",
                 cost_usd=0.4, outcome="review_ready"),
            _rec(run_id="a1", lane="api", cost_basis="billed", cost_usd=1.0),
        ]
        g = metrics.evaluate_gates(metrics.aggregate(recs), "subscription-pivot")
        self.assertTrue(g["guardrail_zero"])
        self.assertTrue(g["lane_captured"])
        self.assertTrue(g["cost_captured"])
        self.assertTrue(g["subscription_review_ready"])
        self.assertTrue(g["passed"])

    def test_gate_fails_without_subscription_completion(self):
        recs = [_rec(run_id="a1", lane="api", cost_basis="billed", cost_usd=1.0)]
        g = metrics.evaluate_gates(metrics.aggregate(recs), "subscription-pivot")
        self.assertFalse(g["subscription_review_ready"])
        self.assertFalse(g["passed"])

    def test_gate_fails_on_legacy_records_without_lane(self):
        recs = [
            _rec(run_id="s1", lane="subscription", cost_basis="estimated",
                 cost_usd=0.4, outcome="review_ready"),
            _rec(run_id="legacy"),  # no lane/cost_basis -> coverage < 1.0
        ]
        g = metrics.evaluate_gates(metrics.aggregate(recs), "subscription-pivot")
        self.assertFalse(g["lane_captured"])
        self.assertFalse(g["passed"])


if __name__ == "__main__":
    unittest.main()
