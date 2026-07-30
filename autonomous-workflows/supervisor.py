"""Worker-supervisor decision core (Phase 2).

The pure "brain" of the supervisor: it composes the budget guard (budget.py) and
the authorization policy (policy.py) with the worker's state into the next control
action. No subprocess, no I/O — the `claude -p` subprocess/steer wiring is a thin
shell around this and is built once the gateway is live (see
docs/phase-2-worker-and-budget.md → Verified mechanics).
"""
from __future__ import annotations

import budget
import policy


def next_action(state: dict, session_root: str) -> str:
    """Return the next supervisor action for a worker turn.

    Priority — no-spend actions first, so the budget never blocks finishing or gating:
      "final_review"  worker signalled done -> stop at Final Review (local git diff, no spend)
      "gate"          worker wants a GATED action -> emit input-request (§7), no spend
      "execute"       worker wants an ALLOWED action -> run it unattended
      "continue"      take the next (spending) model turn -- only if within the reserve/window
      "halt_budget"   (api lane) the next turn would cross the budget reserve -> stop taking new work
      "halt_rate_limit" (subscription lane) an authoritative parsed limit -> pause until resets_at
      "defer_window"    (subscription lane) advisory allotment exceeded, no reset time -> back off and retry

    `state` keys (all optional): `worker_done` (bool), `pending_action` (dict for
    policy.classify_action), `lane` ("api" | "subscription"), plus a precomputed
    per-lane guard summary (the shell precomputes it — `next_action` stays pure,
    state never grows a record list or a clock):
      api lane:          `budget` = {"spend", "est_cost", "cap"} (`spend` is the
                         GATEWAY meter, not the CLI's total_cost_usd).
      subscription lane: `window` = {"can_start": bool, "resets_at": iso|None,
                         "authoritative": bool} (from window_guard, D7/F2).
    Lane dispatch reads `state["lane"]` (N5); an absent lane keeps the api/budget
    branch so pre-pivot callers are unchanged.
    """
    if state.get("worker_done"):
        return "final_review"

    pending = state.get("pending_action")
    if pending is not None:
        return "gate" if policy.classify_action(pending, session_root) == policy.GATED else "execute"

    if state.get("lane") == "subscription":
        w = state.get("window", {})
        if w.get("can_start"):
            return "continue"
        # cannot start: an authoritative parsed limit (resets_at present) is a real
        # pause; an advisory-only stop is a back-off, never an indefinite pause.
        return "halt_rate_limit" if w.get("authoritative") else "defer_window"

    b = state.get("budget", {})
    if budget.can_start(b.get("spend", 0.0), b.get("est_cost", 0.0), b.get("cap", budget.MONTHLY_CAP_USD)):
        return "continue"
    return "halt_budget"
