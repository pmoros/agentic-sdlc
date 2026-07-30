"""E2E logic replay (ADH-003 step 7): a rate-limit exhaustion carried from the raw
CLI error string all the way to a not-runnable-until-reset scheduling decision —
proving the subscription lane PAUSES rather than fails, end to end, with no spend.

Chain under test (the whole D3 reactive model stitched together):
  window_guard.parse_limit_error (D3.2, authoritative signal)
    -> a paused_rate_limit run-record
    -> orchestrator.join_input guarded pause recognition (D3.3)
    -> orchestrator.join_decision -> waiting_rate_limit (never ready / never merge)
    -> window_guard.next_resume_at + fanout.runnable_now paused_until filter (F5).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/ on path
import fanout        # noqa: E402
import orchestrator  # noqa: E402
import window_guard  # noqa: E402

# The verbatim documented session-limit string (D3.2).
SESSION_LIMIT = "You've hit your session limit · resets 2026-07-30T16:00:00Z"


class PauseNotFailReplayTest(unittest.TestCase):
    def test_full_pause_lifecycle_end_to_end(self):
        # 1. The CLI signalled an error; parse the documented limit string off stderr.
        limit = window_guard.parse_limit_error(SESSION_LIMIT, channel="stderr")
        self.assertIsNotNone(limit)
        self.assertEqual(limit["kind"], "session")
        self.assertEqual(limit["resets_at"], "2026-07-30T16:00:00Z")

        # 2. The worker's run-record carries the pause: outcome + limit block + error exit.
        record = {"task_id": "t1", "outcome": "paused_rate_limit", "is_error": True,
                  "exit_code": 1, "limit": limit, "lane": "subscription",
                  "cost_basis": "estimated", "model": "claude-sonnet-5"}

        # 3. join_input recognizes the guarded pause — not a failure, never fail-open.
        ji = orchestrator.join_input(record)
        self.assertEqual(ji["outcome"], "paused")

        # 4. join_decision holds the whole fan-out: waiting, never ready, never merge —
        #    even with a clean sibling that finished review_ready.
        sibling = {"task_id": "t2", "outcome": "review_ready", "guardrail_violations": 0, "conflict": False}
        self.assertEqual(orchestrator.join_decision([ji, sibling]), "waiting_rate_limit")

        # 5. The scheduler won't relaunch t1 before resets_at, and re-admits it after (F5).
        resume = window_guard.next_resume_at([record], now="2026-07-30T14:00:00Z")
        self.assertEqual(window_guard._parse(resume), window_guard._parse("2026-07-30T16:00:00Z"))
        blocked = fanout.runnable_now(["t1"], deps={}, done=set(), running=set(),
                                      max_concurrent=2, now="2026-07-30T15:00:00Z",
                                      paused_until={"t1": resume})
        self.assertEqual(blocked, [], "worker must not relaunch into a still-exhausted window")
        readmitted = fanout.runnable_now(["t1"], deps={}, done=set(), running=set(),
                                         max_concurrent=2, now="2026-07-30T16:30:00Z",
                                         paused_until={"t1": resume})
        self.assertEqual(readmitted, ["t1"], "worker re-admitted once the window reset")

    def test_a_task_merely_quoting_the_limit_string_never_pauses_the_fleet(self):
        # A clean success record (is_error False, exit 0) that mentions the phrase in
        # its output joins normally — the pause path is gated on a real CLI error.
        benign = {"task_id": "t3", "outcome": "review_ready", "is_error": False,
                  "exit_code": 0, "lane": "subscription", "result": SESSION_LIMIT}
        self.assertEqual(orchestrator.join_input(benign)["outcome"], "review_ready")


if __name__ == "__main__":
    unittest.main()
