"""Tests for the end-to-end fan-out driver (execute_fanout).

The turnkey shell that ties the pure decision cores into one run:
  plan_runs -> admit -> new_manifest -> [runnable_now -> launch -> set_status]
  -> join_input -> join_decision -> (if ready) merge -> teardown_plan -> metrics.

The real launch (run-worker.sh subprocess) and merge (integrate.integration_merge)
are INJECTED, so the whole orchestration is testable offline with fakes — no
`claude`, no git, no spend. Run: python3 -m pytest autonomous-workflows/tests/test_fanout_run.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # autonomous-workflows/ on path
import fanout_run  # noqa: E402

NOW = "2026-08-01T12:00:00Z"


def rec(tid, outcome="review_ready", *, lane="subscription", cost=0.02, guard=0,
        error=False, exit_code=0, limit=None, model="claude-sonnet-5"):
    r = {"task_id": tid, "outcome": outcome, "lane": lane,
         "cost_basis": "estimated" if lane == "subscription" else "billed",
         "cost_usd": cost, "model": model, "guardrail_violations": guard,
         "is_error": error, "exit_code": exit_code, "started_at": NOW}
    if limit is not None:
        r["limit"] = limit
    return r


class FakeLauncher:
    """Injected launch: records call order, returns a canned record per task."""
    def __init__(self, records):
        self.records = records
        self.calls = []

    def __call__(self, spec):
        self.calls.append(spec["task_id"])
        return self.records[spec["task_id"]]


def clean_merge(repo, base_ref, branches):
    return {"integration_branch": "auto/_integration", "order": list(branches),
            "merged": list(branches), "conflict": False, "conflicting_branch": None}


TWO = [{"task_id": "t1", "role": "coder"}, {"task_id": "t2", "role": "coder"}]


class ExecuteFanoutTest(unittest.TestCase):
    def _run(self, subtasks, launch, **kw):
        kw.setdefault("now", NOW)
        kw.setdefault("merge", clean_merge)
        return fanout_run.execute_fanout(subtasks, "S", launch=launch, **kw)

    # --- happy path -----------------------------------------------------------
    def test_all_ready_merges_and_passes_gate(self):
        launch = FakeLauncher({"t1": rec("t1"), "t2": rec("t2")})
        res = self._run(TWO, launch, gate_phase="subscription-pivot")
        self.assertTrue(res["admitted"])
        self.assertEqual(res["decision"], "ready_for_final_review")
        self.assertIsNotNone(res["merge"])
        self.assertFalse(res["merge"]["conflict"])
        self.assertEqual(sorted(launch.calls), ["t1", "t2"])  # both launched (order not guaranteed under parallelism)
        self.assertGreater(res["metrics"]["estimated_savings_usd"], 0)
        self.assertTrue(res["gate"]["passed"])
        self.assertTrue(res["teardown_plan"])                 # teardown computed

    # --- failure dominates: no merge -----------------------------------------
    def test_a_failure_yields_partial_review_and_no_merge(self):
        launch = FakeLauncher({"t1": rec("t1"), "t2": rec("t2", "failed", error=True, exit_code=1)})
        merge_calls = []
        res = self._run(TWO, launch, merge=lambda *a: merge_calls.append(a) or clean_merge(*a))
        self.assertEqual(res["decision"], "partial_review")
        self.assertIsNone(res["merge"])
        self.assertEqual(merge_calls, [])                     # merge never attempted

    # --- pause: waiting, never merged ----------------------------------------
    def test_a_pause_yields_waiting_rate_limit_and_no_merge(self):
        limit = {"kind": "session", "resets_at": "2026-08-01T16:00:00Z",
                 "channel": "stderr", "matched_text": "You've hit your session limit"}
        launch = FakeLauncher({"t1": rec("t1"),
                               "t2": rec("t2", "paused_rate_limit", error=True, exit_code=1, limit=limit)})
        res = self._run(TWO, launch)
        self.assertEqual(res["decision"], "waiting_rate_limit")
        self.assertIsNone(res["merge"])

    # --- guardrail violation halts -------------------------------------------
    def test_guardrail_violation_halts_and_no_merge(self):
        launch = FakeLauncher({"t1": rec("t1", guard=1), "t2": rec("t2")})
        res = self._run(TWO, launch)
        self.assertEqual(res["decision"], "halt_violation")
        self.assertIsNone(res["merge"])

    # --- real merge conflict flips ready -> needs_human_merge ----------------
    def test_ready_but_real_merge_conflict_needs_human_merge(self):
        launch = FakeLauncher({"t1": rec("t1"), "t2": rec("t2")})
        conflict = lambda *a: {"integration_branch": "auto/_integration", "order": [],
                               "merged": [], "conflict": True, "conflicting_branch": "auto/S/t2"}
        res = self._run(TWO, launch, merge=conflict)
        self.assertEqual(res["decision"], "needs_human_merge")
        self.assertTrue(res["merge"]["conflict"])

    # --- admission control: refuse before launching --------------------------
    def test_subscription_admission_refused_over_window(self):
        launch = FakeLauncher({"t1": rec("t1"), "t2": rec("t2")})
        # 2 workers x $3 window each = $6 > default 5h allotment ($5)
        res = self._run(TWO, launch, per_worker_window_est_usd=3.0)
        self.assertFalse(res["admitted"])
        self.assertIsNone(res["decision"])
        self.assertEqual(launch.calls, [])                    # nothing launched

    def test_api_admission_refused_over_cap(self):
        launch = FakeLauncher({"t1": rec("t1", lane="api"), "t2": rec("t2", lane="api")})
        res = self._run(TWO, launch, lane="api", per_worker_budget=3.0, spend=195.0, cap=200.0)
        self.assertFalse(res["admitted"])
        self.assertEqual(launch.calls, [])

    # --- a batch of independent workers actually launches in parallel ---------
    def test_launches_a_batch_in_parallel(self):
        import threading
        # A Barrier(3) only releases when all 3 workers are in-flight at once. If
        # launch ran sequentially, the first .wait() would time out (BrokenBarrier)
        # and this test would error — so passing proves real concurrency.
        barrier = threading.Barrier(3, timeout=5)

        def launch(spec):
            barrier.wait()
            return rec(spec["task_id"])

        subtasks = [{"task_id": f"t{i}", "role": "coder"} for i in range(3)]
        res = fanout_run.execute_fanout(subtasks, "S", launch=launch, merge=clean_merge,
                                        now=NOW, max_concurrent=3)
        self.assertEqual(res["decision"], "ready_for_final_review")

    # --- deps drive launch + merge order -------------------------------------
    def test_deps_drive_launch_and_merge_order(self):
        launch = FakeLauncher({"t1": rec("t1"), "t2": rec("t2")})
        seen = {}
        def merge(repo, base, branches):
            seen["branches"] = list(branches)
            return clean_merge(repo, base, branches)
        res = self._run(TWO, launch, deps={"t2": ["t1"]}, merge=merge)
        self.assertEqual(launch.calls, ["t1", "t2"])          # t1 before its dependent t2
        self.assertEqual(seen["branches"], ["auto/S/t1", "auto/S/t2"])
        self.assertEqual(res["decision"], "ready_for_final_review")


if __name__ == "__main__":
    unittest.main()
