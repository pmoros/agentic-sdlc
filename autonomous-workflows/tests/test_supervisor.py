"""Tests for the worker-supervisor decision core (Phase 2).

`next_action(state, session_root)` is the pure brain of the supervisor: it
composes the budget guard (budget.py) and the authorization policy (policy.py)
with the worker's state into the next control decision. No subprocess, no I/O —
so it is fully testable offline, independent of the `claude -p` mechanics.

Run: python3 autonomous-workflows/tests/test_supervisor.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # autonomous-workflows/ on path
import supervisor  # noqa: E402

ROOT = "/wt/session"


def decide(**state):
    return supervisor.next_action(state, ROOT)


class NextActionTest(unittest.TestCase):
    def test_done_goes_to_final_review(self):
        self.assertEqual(decide(worker_done=True), "final_review")

    def test_done_takes_priority_even_if_over_budget(self):
        # final review is a local git diff — no spend — so budget must not block it
        self.assertEqual(
            decide(worker_done=True, budget={"spend": 500.0, "cap": 200.0}),
            "final_review",
        )

    def test_pending_gated_action_routes_to_gate(self):
        self.assertEqual(decide(pending_action={"kind": "aws", "subcommand": "s3 cp"}), "gate")
        self.assertEqual(decide(pending_action={"kind": "git", "subcommand": "push"}), "gate")

    def test_pending_allowed_action_executes(self):
        self.assertEqual(
            decide(pending_action={"kind": "edit", "path": "/wt/session/worktrees/code/x.py"}),
            "execute",
        )

    def test_done_beats_pending(self):
        self.assertEqual(
            decide(worker_done=True, pending_action={"kind": "aws"}),
            "final_review",
        )

    def test_continue_when_budget_ok(self):
        self.assertEqual(decide(budget={"spend": 10.0, "est_cost": 1.0, "cap": 200.0}), "continue")

    def test_halt_budget_when_over_reserve(self):
        # 185 + 5 = 190 > 0.9*200 = 180 -> must not start another (spending) turn
        self.assertEqual(decide(budget={"spend": 185.0, "est_cost": 5.0, "cap": 200.0}), "halt_budget")

    def test_empty_state_continues(self):
        # no work done, nothing pending, zero spend -> take the next turn
        self.assertEqual(decide(), "continue")

    # --- D7/F2: subscription-lane dispatch on state["lane"] / state["window"] ---
    def test_subscription_continue_when_window_ok(self):
        self.assertEqual(
            decide(lane="subscription", window={"can_start": True, "resets_at": None, "authoritative": False}),
            "continue",
        )

    def test_subscription_authoritative_limit_halts(self):
        # a parsed limit error (authoritative, resets_at present) -> halt_rate_limit
        self.assertEqual(
            decide(lane="subscription",
                   window={"can_start": False, "resets_at": "2026-07-30T16:00:00Z", "authoritative": True}),
            "halt_rate_limit",
        )

    def test_subscription_advisory_exhaustion_defers(self):
        # advisory allotment exceeded (no resets_at) -> defer_window (back off, not an indefinite pause)
        self.assertEqual(
            decide(lane="subscription",
                   window={"can_start": False, "resets_at": None, "authoritative": False}),
            "defer_window",
        )

    def test_subscription_done_still_final_review(self):
        # no-spend actions stay lane-independent and highest priority
        self.assertEqual(
            decide(lane="subscription", worker_done=True,
                   window={"can_start": False, "authoritative": True, "resets_at": "2026-07-30T16:00:00Z"}),
            "final_review",
        )

    def test_subscription_pending_gated_still_gates(self):
        self.assertEqual(
            decide(lane="subscription", pending_action={"kind": "git", "subcommand": "push"},
                   window={"can_start": False, "authoritative": False}),
            "gate",
        )

    def test_api_lane_explicit_uses_budget_branch(self):
        self.assertEqual(decide(lane="api", budget={"spend": 10.0, "est_cost": 1.0, "cap": 200.0}), "continue")
        self.assertEqual(decide(lane="api", budget={"spend": 185.0, "est_cost": 5.0, "cap": 200.0}), "halt_budget")


if __name__ == "__main__":
    unittest.main()
