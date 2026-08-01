"""E2E (logic) proof for ADH-005 window-/strength-aware routing.

A subscription fan-out under Sonnet-weekly pressure routes each subtask across
tiers — the coder task escalates Sonnet->Opus 5, the triage task stays on Haiku —
and the resulting run-records aggregate into a model-mix + per-family headroom
that make the rebalancing observable. No claude, no git, no spend.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # autonomous-workflows/ on path
import fanout_run  # noqa: E402
import metrics  # noqa: E402

NOW = "2026-08-01T12:00:00+00:00"


def _rec(tid, model):
    return {"task_id": tid, "outcome": "review_ready", "lane": "subscription",
            "cost_basis": "estimated", "cost_usd": 0.05, "model": model,
            "started_at": NOW, "guardrail_violations": 0,
            "tokens": {"input": 10, "output": 5}}


def _clean_merge(repo, base, branches):
    return {"integration_branch": "auto/_integration", "order": list(branches),
            "merged": list(branches), "conflict": False, "conflicting_branch": None}


class RoutingE2ETest(unittest.TestCase):
    def test_fanout_routes_across_tiers_under_sonnet_pressure(self):
        # $24.5 sonnet burn 6 days ago -> the Sonnet weekly cap is tight, Opus is clear.
        prior = [{"cost_usd": 24.5, "started_at": "2026-07-26T12:00:00+00:00",
                  "model": "claude-sonnet-5", "lane": "subscription", "cost_basis": "estimated"}]
        launched = {}

        def launch(spec):
            launched[spec["task_id"]] = spec["model"]
            return _rec(spec["task_id"], spec["model"])

        res = fanout_run.execute_fanout(
            [{"task_id": "t1", "task_type": "fix"},       # coder -> sonnet, escalated
             {"task_id": "t2", "task_type": "triage"}],   # classifier -> haiku, untouched
            "S", launch=launch, merge=_clean_merge, now=NOW, records=prior)

        self.assertTrue(res["admitted"])
        self.assertEqual(res["decision"], "ready_for_final_review")
        self.assertEqual(launched["t1"], "claude-opus-5")     # escalated under Sonnet pressure
        self.assertEqual(launched["t2"], "claude-haiku-4-5")  # triage stays on the floor

        # The rebalancing is observable in metrics: mixed model-mix + Sonnet tight.
        m = metrics.aggregate(prior + list(res["records"].values()), now=NOW)
        self.assertIn("claude-opus-5", m["model_mix"])
        self.assertIn("claude-haiku-4-5", m["model_mix"])
        self.assertTrue(m["window_headroom"]["sonnet"]["tight"])
        self.assertFalse(m["window_headroom"]["opus"]["tight"])


if __name__ == "__main__":
    unittest.main()
