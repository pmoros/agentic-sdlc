"""Tests for the Phase-3 orchestrator decision core.

The pure planning/join logic for fan-out: turn decomposed sub-tasks into per-worker
run specs (role->model via routing, own branch, own budget), admission-control the
fan-out against the $200 cap, and decide the N-branch JOIN (the hard part the
proposal underspecified): violation > merge-conflict > failure > ready-for-review.
No subprocess, no git — fully testable offline.

Run: python3 scripts/tests/test_orchestrator.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/ on path
import orchestrator  # noqa: E402


class PlanRunsTest(unittest.TestCase):
    def setUp(self):
        self.specs = orchestrator.plan_runs(
            [
                {"task_id": "t1", "role": "planner"},
                {"task_id": "t2", "task_type": "fix"},
                {"task_id": "t3", "role": "classifier"},
            ],
            session_id="S",
            per_worker_budget=3.0,
            lane="api",  # rev 2 F7: this suite pins the api-lane budget spec schema
        )

    def test_one_spec_per_subtask(self):
        self.assertEqual(len(self.specs), 3)

    def test_role_and_task_type_resolve_to_the_right_model(self):
        by_id = {s["task_id"]: s for s in self.specs}
        self.assertEqual(by_id["t1"]["model"], "claude-opus-4-8")   # planner
        self.assertEqual(by_id["t2"]["model"], "claude-sonnet-5")   # fix -> coder
        self.assertEqual(by_id["t2"]["role"], "coder")
        self.assertEqual(by_id["t3"]["model"], "claude-haiku-4-5")  # classifier

    def test_agent_id_branch_and_budget(self):
        s = self.specs[0]
        self.assertEqual(s["agent_id"], "agent-S-t1")
        self.assertEqual(s["branch"], "auto/S/t1")
        self.assertEqual(s["budget"], 3.0)


class FanoutBudgetTest(unittest.TestCase):
    def _specs(self, n, each=3.0):
        return [{"task_id": f"t{i}", "budget": each} for i in range(n)]

    def test_fits_under_cap(self):
        self.assertTrue(orchestrator.fanout_budget_ok(self._specs(3), spend=10.0, cap=200.0))

    def test_rejected_when_sum_would_breach_cap(self):
        # 195 spent + 3*3 = 204 > 200
        self.assertFalse(orchestrator.fanout_budget_ok(self._specs(3), spend=195.0, cap=200.0))


class SubscriptionPlanRunsTest(unittest.TestCase):
    # rev 2 F7 / rev 2.1 N6: lane-pinned spec schema.
    def test_default_lane_is_subscription(self):
        specs = orchestrator.plan_runs([{"task_id": "t1", "role": "coder"}], session_id="S")
        self.assertEqual(specs[0]["lane"], "subscription")
        self.assertIn("window_est_usd", specs[0])
        self.assertNotIn("budget", specs[0])

    def test_subscription_specs_carry_window_est_not_budget(self):
        specs = orchestrator.plan_runs(
            [{"task_id": "t1", "role": "coder"}], session_id="S",
            lane="subscription", per_worker_window_est_usd=1.5)
        s = specs[0]
        self.assertEqual(s["lane"], "subscription")
        self.assertEqual(s["window_est_usd"], 1.5)
        self.assertNotIn("budget", s)
        self.assertEqual(s["model"], "claude-sonnet-5")   # coder -> sonnet (for tiering)

    def test_api_lane_keeps_budget_schema(self):
        specs = orchestrator.plan_runs(
            [{"task_id": "t1", "role": "coder"}], session_id="S",
            lane="api", per_worker_budget=4.0)
        self.assertEqual(specs[0]["lane"], "api")
        self.assertEqual(specs[0]["budget"], 4.0)
        self.assertNotIn("window_est_usd", specs[0])


class FanoutWindowsTest(unittest.TestCase):
    # rev 2 D4: subscription-lane admission — Σ per-worker allotments + committed
    # in-flight burn must fit every window. Default 5h allotment is 5.0.
    def _sub_specs(self, n, each):
        return [{"task_id": f"t{i}", "lane": "subscription",
                 "model": "claude-sonnet-5", "window_est_usd": each} for i in range(n)]

    NOW = "2026-07-30T12:00:00Z"

    def test_fits_under_window(self):
        self.assertTrue(orchestrator.fanout_windows_ok(
            self._sub_specs(3, 1.0), records=[], manifest=None, now=self.NOW))  # 3.0 <= 5.0

    def test_rejected_when_over_5h_window(self):
        self.assertFalse(orchestrator.fanout_windows_ok(
            self._sub_specs(3, 2.0), records=[], manifest=None, now=self.NOW))  # 6.0 > 5.0

    def test_committed_in_flight_burn_counts(self):
        manifest = {"agents": {"r1": {"status": "running", "lane": "subscription",
                    "model": "claude-sonnet-5", "window_est_usd": 2.0}}}
        self.assertFalse(orchestrator.fanout_windows_ok(
            self._sub_specs(2, 2.0), records=[], manifest=manifest, now=self.NOW))  # 4.0 + 2.0 > 5.0

    def test_api_specs_do_not_consume_windows(self):
        specs = self._sub_specs(2, 2.0) + [{"task_id": "a1", "lane": "api", "budget": 50.0}]
        self.assertTrue(orchestrator.fanout_windows_ok(
            specs, records=[], manifest=None, now=self.NOW))   # only the 4.0 subscription burn counts


class JoinDecisionTest(unittest.TestCase):
    def test_all_clean_ready_for_review(self):
        results = [{"task_id": "t1", "outcome": "review_ready", "guardrail_violations": 0, "conflict": False},
                   {"task_id": "t2", "outcome": "review_ready", "guardrail_violations": 0, "conflict": False}]
        self.assertEqual(orchestrator.join_decision(results), "ready_for_final_review")

    def test_guardrail_violation_halts(self):
        results = [{"task_id": "t1", "outcome": "review_ready", "guardrail_violations": 1, "conflict": False}]
        self.assertEqual(orchestrator.join_decision(results), "halt_violation")

    def test_conflict_needs_human_merge(self):
        results = [{"task_id": "t1", "outcome": "review_ready", "guardrail_violations": 0, "conflict": True}]
        self.assertEqual(orchestrator.join_decision(results), "needs_human_merge")

    def test_failure_is_partial_review(self):
        results = [{"task_id": "t1", "outcome": "failed", "guardrail_violations": 0, "conflict": False}]
        self.assertEqual(orchestrator.join_decision(results), "partial_review")

    def test_precedence_violation_over_conflict_over_failure(self):
        results = [{"task_id": "t1", "outcome": "failed", "guardrail_violations": 2, "conflict": True}]
        self.assertEqual(orchestrator.join_decision(results), "halt_violation")

    # --- D3.3 waiting_rate_limit outcome + full precedence (rev 2.1, N3) -------
    # Precedence: halt_violation > partial_review(failed) > waiting_rate_limit
    #             > needs_human_merge > ready_for_final_review
    def test_paused_worker_waits(self):
        results = [{"task_id": "t1", "outcome": "review_ready", "guardrail_violations": 0, "conflict": False},
                   {"task_id": "t2", "outcome": "paused", "guardrail_violations": 0, "conflict": False}]
        self.assertEqual(orchestrator.join_decision(results), "waiting_rate_limit")

    def test_waiting_beats_needs_human_merge(self):
        # a fan-out with a paused worker is never handed to a human merge yet
        results = [{"task_id": "t1", "outcome": "paused", "guardrail_violations": 0, "conflict": False},
                   {"task_id": "t2", "outcome": "review_ready", "guardrail_violations": 0, "conflict": True}]
        self.assertEqual(orchestrator.join_decision(results), "waiting_rate_limit")

    def test_failed_beats_waiting(self):
        results = [{"task_id": "t1", "outcome": "failed", "guardrail_violations": 0, "conflict": False},
                   {"task_id": "t2", "outcome": "paused", "guardrail_violations": 0, "conflict": False}]
        self.assertEqual(orchestrator.join_decision(results), "partial_review")

    def test_violation_beats_waiting(self):
        results = [{"task_id": "t1", "outcome": "paused", "guardrail_violations": 1, "conflict": False}]
        self.assertEqual(orchestrator.join_decision(results), "halt_violation")

    def test_failure_dominates_conflict(self):
        # Deliberate reorder (rev 2.1 N3): the design's waiting>merge + failed>waiting
        # chain forces failed>merge. Previously merge-conflict outranked failure.
        results = [{"task_id": "t1", "outcome": "failed", "guardrail_violations": 0, "conflict": True}]
        self.assertEqual(orchestrator.join_decision(results), "partial_review")


class MergeOrderTest(unittest.TestCase):
    def _specs(self):
        return [{"task_id": "t3"}, {"task_id": "t1"}, {"task_id": "t2"}]

    def test_no_deps_sorts_by_id(self):
        self.assertEqual(orchestrator.merge_order(self._specs()), ["t1", "t2", "t3"])

    def test_topological_when_deps_given(self):
        deps = {"t2": ["t1"], "t3": ["t2"]}
        self.assertEqual(orchestrator.merge_order(self._specs(), deps), ["t1", "t2", "t3"])

    def test_cycle_raises(self):
        deps = {"t1": ["t2"], "t2": ["t1"]}
        with self.assertRaises(ValueError):
            orchestrator.merge_order(self._specs(), deps)


class StageRunnerTest(unittest.TestCase):
    def test_happy_path_advances_through_all_stages(self):
        self.assertEqual(orchestrator.next_stage("planning", "pass"), "discovery")
        self.assertEqual(orchestrator.next_stage("discovery", "pass"), "design")
        self.assertEqual(orchestrator.next_stage("design", "pass"), "gate_a")
        self.assertEqual(orchestrator.next_stage("gate_a", "approved"), "implementation")
        self.assertEqual(orchestrator.next_stage("implementation", "pass"), "qa")
        self.assertEqual(orchestrator.next_stage("qa", "pass"), "gate_b")
        self.assertEqual(orchestrator.next_stage("gate_b", "approved"), "deploy")
        self.assertEqual(orchestrator.next_stage("deploy", "pass"), "done")

    def test_discovery_blocked_parks(self):
        self.assertEqual(orchestrator.next_stage("discovery", "blocked"), "parked")

    def test_gate_a_rejected_loops_back_to_design(self):
        self.assertEqual(orchestrator.next_stage("gate_a", "rejected"), "design")

    def test_qa_fail_loops_back_to_implementation(self):
        self.assertEqual(orchestrator.next_stage("qa", "fail"), "implementation")

    def test_gate_b_rejected_loops_back_to_implementation(self):
        self.assertEqual(orchestrator.next_stage("gate_b", "rejected"), "implementation")

    def test_is_gate(self):
        self.assertTrue(orchestrator.is_gate("gate_a"))
        self.assertTrue(orchestrator.is_gate("gate_b"))
        self.assertFalse(orchestrator.is_gate("design"))

    def test_is_terminal(self):
        self.assertTrue(orchestrator.is_terminal("done"))
        self.assertTrue(orchestrator.is_terminal("parked"))
        self.assertFalse(orchestrator.is_terminal("qa"))

    def test_unknown_stage_or_outcome_raises(self):
        with self.assertRaises(ValueError):
            orchestrator.next_stage("nope", "pass")
        with self.assertRaises(ValueError):
            orchestrator.next_stage("qa", "sideways")


class JoinInputTest(unittest.TestCase):
    def test_review_ready_passthrough(self):
        ji = orchestrator.join_input({"task_id": "t1", "outcome": "review_ready", "guardrail_violations": 0})
        self.assertEqual(ji["task_id"], "t1")
        self.assertEqual(ji["outcome"], "review_ready")
        self.assertEqual(ji["guardrail_violations"], 0)
        self.assertFalse(ji["conflict"])

    def test_is_error_fails_closed(self):
        ji = orchestrator.join_input({"task_id": "t1", "is_error": True, "outcome": "review_ready"})
        self.assertEqual(ji["outcome"], "failed")

    def test_nonzero_exit_fails_closed(self):
        self.assertEqual(orchestrator.join_input({"task_id": "t1", "exit_code": 1, "outcome": "review_ready"})["outcome"], "failed")

    def test_empty_or_missing_outcome_fails_closed(self):
        # F2: an absent/empty result event -> failed, not silently "ready"
        self.assertEqual(orchestrator.join_input({"task_id": "t1"})["outcome"], "failed")
        self.assertEqual(orchestrator.join_input({})["outcome"], "failed")

    def test_guardrail_violations_passthrough(self):
        self.assertEqual(orchestrator.join_input({"task_id": "t1", "outcome": "review_ready", "guardrail_violations": 2})["guardrail_violations"], 2)

    # --- D3.3 guarded pause recognition ---------------------------------------
    def _paused_record(self, **over):
        rec = {
            "task_id": "t1",
            "outcome": "paused_rate_limit",
            "is_error": True,
            "exit_code": 1,
            "limit": {"kind": "session", "resets_at": "2026-07-30T16:00:00Z",
                      "channel": "stderr", "matched_text": "You've hit your session limit"},
        }
        rec.update(over)
        return rec

    def test_pause_recognized_with_full_guard(self):
        # outcome + populated limit block + error exit all present -> "paused"
        self.assertEqual(orchestrator.join_input(self._paused_record())["outcome"], "paused")

    def test_pause_via_nonzero_exit_without_is_error(self):
        # the error exit D3.2 requires can be a non-zero exit code, not only is_error
        rec = self._paused_record(is_error=False, exit_code=1)
        self.assertEqual(orchestrator.join_input(rec)["outcome"], "paused")

    def test_pause_claim_without_limit_block_fails_closed(self):
        # outcome alone is never trusted -> safe failure path
        rec = self._paused_record()
        rec.pop("limit")
        self.assertEqual(orchestrator.join_input(rec)["outcome"], "failed")

    def test_pause_claim_with_empty_limit_block_fails_closed(self):
        self.assertEqual(orchestrator.join_input(self._paused_record(limit={}))["outcome"], "failed")

    def test_pause_claim_without_error_exit_fails_closed(self):
        # clean exit + no is_error: a self-declared pause the CLI never signalled -> failed
        rec = self._paused_record(is_error=False, exit_code=0)
        self.assertEqual(orchestrator.join_input(rec)["outcome"], "failed")

    def test_pause_preserves_guardrail_and_task_id(self):
        ji = orchestrator.join_input(self._paused_record(guardrail_violations=0))
        self.assertEqual(ji["task_id"], "t1")
        self.assertEqual(ji["guardrail_violations"], 0)


class CountGatedActionsTest(unittest.TestCase):
    def test_counts_only_gated(self):
        actions = [
            {"kind": "read"},                                   # allowed
            {"kind": "git", "subcommand": "push"},              # gated
            {"kind": "aws"},                                    # gated
            {"kind": "edit", "path": "/wt/session/x.py"},       # allowed (within root)
            {"kind": "bash", "command": "gh pr create"},        # gated (F1)
        ]
        self.assertEqual(orchestrator.count_gated_actions(actions, "/wt/session"), 3)


if __name__ == "__main__":
    unittest.main()
