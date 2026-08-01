"""Phase-3 orchestrator decision core — the pure planning/join logic for fan-out.

Turns decomposed sub-tasks into per-worker run specs (role->model via routing,
own branch, own budget), admission-controls the fan-out against the $200 cap, and
decides the N-branch JOIN (the part the proposal underspecified). No subprocess,
no git — the parallel launch + real git merge are a thin shell around this
(see docs/phase-3-orchestrator.md).
"""
from __future__ import annotations

import budget
import model_router
import policy
import routing
import window_guard


def plan_runs(subtasks: list[dict], session_id: str, per_worker_budget: float = 3.0,
              lane: str = "subscription", per_worker_window_est_usd: float = 1.0,
              *, records: list[dict] | None = None, manifest: dict | None = None,
              now: str | None = None, allotments: dict | None = None) -> list[dict]:
    """One run spec per sub-task: role->model (routing), own agent id, branch, and
    the lane-appropriate guard field.

    Each sub-task has a `task_id` and either a `role` or a `task_type` (and an
    optional `goal`). Model is chosen for the task — the tiering, applied.

    Lane-pinned spec schema (rev 2 F7 / rev 2.1 N6): `lane` defaults to
    `"subscription"` (the D1 default). Subscription specs carry
    `window_est_usd` (fed to `fanout_windows_ok` / the manifest's tier-aware
    committed burn) and **no** `budget` key; api specs keep `budget` (the
    `fanout_budget_ok` contract `float(s["budget"])`) and no window field.

    Window-aware routing (ADH-005 D4/D6): on the **subscription** lane, when the
    caller supplies the window ledger (`records`/`now`), each spec's strength-map
    model is passed through `model_router.choose_model` against the live per-family
    headroom — upgrading Sonnet->Opus under pressure or deferring, never
    downgrading. Without those inputs (or on the api lane) the strength map stands.
    """
    window = (window_guard.window_headroom(records or [], manifest, now, allotments)
              if lane == "subscription" and now is not None else None)
    specs = []
    for st in subtasks:
        tid = st["task_id"]
        role = st.get("role")
        task_type = st.get("task_type")
        model = routing.select_model(role=role, task_type=task_type)
        if not role:
            role = routing.role_for_task_type(task_type) if task_type else routing.DEFAULT_ROLE
        spec = {
            "task_id": tid,
            "agent_id": f"agent-{session_id}-{tid}",
            "role": role,
            "model": model,
            "task_type": task_type,
            "branch": f"auto/{session_id}/{tid}",
            "lane": lane,
            "goal": st.get("goal"),
        }
        if window is not None:
            decision = model_router.choose_model(spec, window, allotments=allotments)
            spec["model"] = decision["model"]
            spec["route_reason"] = decision["reason"]
            spec["route_action"] = decision["action"]
        if lane == "api":
            spec["budget"] = per_worker_budget
        else:
            spec["window_est_usd"] = per_worker_window_est_usd
        specs.append(spec)
    return specs


def fanout_budget_ok(specs: list[dict], spend: float, cap: float = budget.MONTHLY_CAP_USD) -> bool:
    """Api-lane admission control: even if every worker key maxed out, the fan-out
    can't breach the global cap. (Each worker key is still individually capped too.)
    Only api specs carry `budget`; subscription specs contribute 0 here and are
    admitted by `fanout_windows_ok` instead."""
    total = spend + sum(float(s.get("budget", 0) or 0) for s in specs)
    return total <= cap


def fanout_windows_ok(specs: list[dict], records: list[dict], manifest: dict | None,
                      now: str, allotments: dict | None = None) -> bool:
    """Subscription-lane admission (D4): the new subscription specs' per-worker
    window allotments, added on top of the completed-record ledger and the
    already-committed in-flight burn, must still fit every window (5h, 7d,
    7d_sonnet). Mirrors `fanout_budget_ok`'s shape for the api lane.

    The new specs are treated as if already `running` (conservative reservation)
    and handed to `window_guard.can_start`, which owns the three-window/per-tier
    logic. Api specs consume no window allotment and are ignored here."""
    existing = (manifest or {}).get("agents") or {}
    existing_agents = list(existing.values()) if isinstance(existing, dict) else list(existing)
    pending = [
        {"status": "running", "lane": "subscription",
         "model": s.get("model"), "window_est_usd": s.get("window_est_usd")}
        for s in specs if s.get("lane", "subscription") == "subscription"
    ]
    merged = {"agents": existing_agents + pending}
    return window_guard.can_start(records or [], merged, now, allotments)


def join_decision(results: list[dict]) -> str:
    """Decide the N-branch join.

    Precedence (D3.3, rev 2.1 N3):
        halt_violation > partial_review(failed) > waiting_rate_limit
                       > needs_human_merge > ready_for_final_review
    A rate-limit pause among the workers can never let the fan-out be declared
    ready OR handed to a human merge (waiting outranks both), but a hard failure
    or a guardrail violation still dominates the pause. This deliberately ranks
    failure above merge-conflict — required by `waiting > merge` + `failed >
    waiting` — a change from the original conflict-over-failure order.

    Each result: {task_id, outcome, guardrail_violations, conflict}. `outcome`
    == "paused" is the guarded pause emitted by `join_input` (D3.3). Returns one
    of halt_violation | partial_review | waiting_rate_limit | needs_human_merge
    | ready_for_final_review.
    """
    if any((r.get("guardrail_violations", 0) or 0) > 0 for r in results):
        return "halt_violation"
    if any(r.get("outcome") == "failed" for r in results):
        return "partial_review"
    if any(r.get("outcome") == "paused" for r in results):
        return "waiting_rate_limit"
    if any(r.get("conflict") for r in results):
        return "needs_human_merge"
    return "ready_for_final_review"


def merge_order(specs: list[dict], deps: dict | None = None) -> list[str]:
    """Deterministic order to merge branches. Sorted by task id, or a topological
    order when `deps` (task_id -> list of prerequisite task_ids) is given.
    Raises ValueError on a dependency cycle."""
    ids = [s["task_id"] for s in specs]
    if not deps:
        return sorted(ids)

    idset = set(ids)
    prereq = {i: [p for p in deps.get(i, []) if p in idset] for i in ids}
    resolved: set[str] = set()
    remaining = set(ids)
    order: list[str] = []
    while remaining:
        ready = sorted(i for i in remaining if all(p in resolved for p in prereq[i]))
        if not ready:
            raise ValueError("dependency cycle in merge_order")
        for i in ready:
            order.append(i)
            resolved.add(i)
            remaining.discard(i)
    return order


# --- Stage runner: the dev-lifecycle state machine ---------------------------
# See .agents/rules/dev-lifecycle.instructions.md (promoted from this session).
STAGES = ["planning", "discovery", "design", "gate_a",
          "implementation", "qa", "gate_b", "deploy", "done"]
GATES = {"gate_a", "gate_b"}          # human decision points
TERMINAL = {"done", "parked"}

# (stage, outcome) -> next stage. Failures/rejections loop back; a blocked
# discovery parks the item rather than designing on a bad assumption.
_TRANSITIONS = {
    ("planning", "pass"): "discovery",
    ("discovery", "pass"): "design",
    ("discovery", "blocked"): "parked",
    ("design", "pass"): "gate_a",
    ("gate_a", "approved"): "implementation",
    ("gate_a", "rejected"): "design",
    ("implementation", "pass"): "qa",
    ("implementation", "fail"): "implementation",
    ("qa", "pass"): "gate_b",
    ("qa", "fail"): "implementation",
    ("gate_b", "approved"): "deploy",
    ("gate_b", "rejected"): "implementation",
    ("deploy", "pass"): "done",
    ("deploy", "fail"): "deploy",
}


def next_stage(stage: str, outcome: str) -> str:
    """Advance the lifecycle: return the next stage for (stage, outcome).
    Fail-closed: an unknown (stage, outcome) raises ValueError."""
    try:
        return _TRANSITIONS[(stage, outcome)]
    except KeyError:
        raise ValueError(f"no transition from stage {stage!r} on outcome {outcome!r}")


def is_gate(stage: str) -> bool:
    return stage in GATES


def is_terminal(stage: str) -> bool:
    return stage in TERMINAL


# --- Join input: run-record -> the dict join_decision consumes -----------------
# Build step §3.1. Fail-closed (F2) and guardrail-populated (F1) per the design.
def join_input(run_record: dict) -> dict:
    """Map a worker's run-record to {task_id, outcome, guardrail_violations, conflict}.

    Fail-closed: an error, a non-zero exit, or an absent/empty outcome (crash,
    gateway 4xx -> `last={}`) becomes `failed` — never a silent `review_ready`.
    `conflict` is set later by the integration-merge (§2).

    Guarded pause recognition (D3.3): a rate-limit pause is recognized as the
    join outcome `"paused"` ONLY when the worker's self-declared
    `outcome=="paused_rate_limit"` is corroborated by BOTH a populated `limit`
    audit block AND the error exit that D3.2 requires (is_error or non-zero
    exit). The outcome alone is never trusted — a worker cannot self-declare a
    pause. A `paused_rate_limit` claim that fails the guard falls to `failed`
    (the safe direction), so a spoofed or half-written pause never fails open."""
    errored = bool(run_record.get("is_error"))
    exit_code = run_record.get("exit_code")
    outcome = run_record.get("outcome")
    error_exit = errored or (exit_code not in (None, 0))
    if outcome == "paused_rate_limit":
        limit_block = run_record.get("limit")
        if error_exit and isinstance(limit_block, dict) and limit_block:
            outcome = "paused"
        else:
            outcome = "failed"
    elif error_exit or not outcome:
        outcome = "failed"
    return {
        "task_id": run_record.get("task_id"),
        "outcome": outcome,
        "guardrail_violations": int(run_record.get("guardrail_violations", 0) or 0),
        "conflict": bool(run_record.get("conflict", False)),
    }


def count_gated_actions(actions: list[dict], worktree_root: str) -> int:
    """Guardrail tally (F1): how many proposed actions `policy` would gate. The
    supervisor calls this (or increments per `gate` decision) so a worker that
    attempted a gated action reports guardrail_violations > 0."""
    return sum(1 for a in actions if policy.classify_action(a, worktree_root) == policy.GATED)
