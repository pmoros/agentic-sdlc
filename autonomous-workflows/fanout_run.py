"""End-to-end fan-out driver — the turnkey shell over the pure decision cores.

`execute_fanout` ties the tested cores into one run:

    plan_runs        -> per-worker specs (role->model, branch, lane guard field)
    admit            -> fanout_windows_ok (subscription) | fanout_budget_ok (api)
    new_manifest     -> aggregate observability
    schedule loop    -> runnable_now -> launch(spec) -> set_status   (deps + concurrency)
    join_input       -> per-worker outcome (guarded pause recognition)
    join_decision    -> halt_violation > partial_review > waiting_rate_limit
                        > needs_human_merge > ready_for_final_review
    merge (if ready) -> real N-branch integration; a conflict flips to needs_human_merge
    teardown_plan    -> idempotent cleanup actions
    metrics          -> aggregate + evaluate_gates

The two side-effecting steps — `launch` (a worker) and `merge` (real git) — are
INJECTED. Tests pass fakes (no `claude`, no git, no spend); the CLI wires the
real `default_launch` (per-worker worktree + run-worker.sh) and `default_merge`
(integrate.integration_merge). Keeping them out of the core is what makes the
whole orchestration unit-testable.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import budget
import fanout
import integrate
import metrics
import orchestrator

# Manifest status for a joined outcome (join_input's mapped outcome -> manifest word).
_STATUS = {"review_ready": "review_ready", "failed": "failed", "paused": "paused"}


def _manifest_status(joined_outcome: str) -> str:
    return _STATUS.get(joined_outcome, joined_outcome)


def execute_fanout(
    subtasks: list[dict],
    session_id: str,
    *,
    launch,                              # callable(spec) -> run_record (REQUIRED, injected)
    merge=None,                          # callable(repo, base_ref, branches) -> merge_result
    lane: str = "subscription",
    records: list[dict] | None = None,   # prior run-records (subscription window ledger)
    allotments: dict | None = None,
    per_worker_window_est_usd: float = 1.0,
    per_worker_budget: float = 3.0,
    spend: float = 0.0,
    cap: float = budget.MONTHLY_CAP_USD,
    max_concurrent: int = 4,
    deps: dict | None = None,
    paused_until: dict | None = None,
    now: str | None = None,
    repo: str | None = None,
    base_ref: str = "main",
    run_id: str | None = None,
    gate_phase: str | None = None,
) -> dict:
    """Run one fan-out end to end and return a structured result. See the module
    docstring for the pipeline. `launch(spec)` must return a run-record dict;
    `merge` defaults to the real integration merge and is only called when the
    join says the fan-out is ready. No side effects live in this function itself."""
    deps = deps or {}
    prior = records or []
    specs = orchestrator.plan_runs(
        subtasks, session_id, per_worker_budget=per_worker_budget,
        lane=lane, per_worker_window_est_usd=per_worker_window_est_usd)

    # --- admission: refuse the whole fan-out before launching anything --------
    if lane == "subscription":
        admitted = orchestrator.fanout_windows_ok(specs, prior, None, now, allotments)
        reason = None if admitted else "subscription window allotment would be exceeded"
    else:
        admitted = orchestrator.fanout_budget_ok(specs, spend, cap)
        reason = None if admitted else "api dollar cap would be exceeded"
    if not admitted:
        return {"admitted": False, "reason": reason, "decision": None, "specs": specs,
                "manifest": None, "records": {}, "merge": None, "teardown_plan": [],
                "metrics": {}, "gate": None}

    manifest = fanout.new_manifest(run_id or f"run-{session_id}", specs)
    spec_by_id = {s["task_id"]: s for s in specs}
    task_ids = [s["task_id"] for s in specs]

    # --- schedule + launch (deps- and concurrency-aware; launch is synchronous
    # here — real parallelism is a future enhancement over the same loop) ------
    done: set = set()
    running: set = set()
    out: dict = {}
    while len(done) < len(task_ids):
        ready = fanout.runnable_now(task_ids, deps, done, running, max_concurrent,
                                    now=now, paused_until=paused_until)
        if not ready:
            break  # nothing runnable (dep cycle, or every remaining worker paused)
        for tid in ready:
            fanout.set_status(manifest, tid, "running")
            record = launch(spec_by_id[tid])
            out[tid] = record
            joined = orchestrator.join_input(record)["outcome"]
            fanout.set_status(manifest, tid, _manifest_status(joined),
                              trace=record.get("trace"))
            done.add(tid)

    # --- join -----------------------------------------------------------------
    results = [orchestrator.join_input(out[tid]) for tid in task_ids if tid in out]
    decision = orchestrator.join_decision(results)

    # --- merge (only when the join says ready); a real conflict downgrades it --
    merge_result = None
    if decision == "ready_for_final_review":
        merge = merge or default_merge
        branches = [spec_by_id[tid]["branch"]
                    for tid in orchestrator.merge_order(specs, deps) if tid in out]
        merge_result = merge(repo, base_ref, branches)
        if merge_result and merge_result.get("conflict"):
            decision = "needs_human_merge"

    # --- teardown plan (keep a cleanly-merged set for the approved merge) ------
    teardown = fanout.teardown_plan(manifest)

    # --- metrics over prior + this run's records ------------------------------
    all_records = prior + list(out.values())
    summary = metrics.aggregate(all_records) if all_records else {}
    gate = (metrics.evaluate_gates(summary, gate_phase)
            if gate_phase and summary else None)

    return {"admitted": True, "reason": None, "decision": decision, "specs": specs,
            "manifest": manifest, "records": out, "merge": merge_result,
            "teardown_plan": teardown, "metrics": summary, "gate": gate}


# --------------------------------------------------------------------------- #
# Real wiring (thin, side-effecting shells — exercised by integration, not unit)
# --------------------------------------------------------------------------- #
_HERE = os.path.dirname(os.path.abspath(__file__))


def default_launch(spec: dict, *, base_ref: str = "main", worktrees_dir: str,
                   run_records_dir: str, lane: str = "subscription",
                   repo: str = ".", extra_env: dict | None = None) -> dict:
    """Provision a per-worker branch + worktree off `base_ref`, run the worker via
    run-worker.sh inside it, and return the run-record. Side-effecting integration
    shell — not unit-tested; the orchestration that calls it is."""
    tid = spec["task_id"]
    branch = spec["branch"]
    wt = os.path.join(worktrees_dir, tid)
    subprocess.run(["git", "-C", repo, "worktree", "add", "-B", branch, wt, base_ref],
                   check=True, capture_output=True, text=True)
    env = dict(os.environ)
    env.update({"LANE": lane, "RUN_RECORDS_DIR": run_records_dir,
                "MODEL": spec.get("model", ""), "WORKER_TOOLS": env.get("WORKER_TOOLS", "Read,Edit,Bash")})
    if extra_env:
        env.update(extra_env)
    subprocess.run(["bash", os.path.join(_HERE, "run-worker.sh"), tid, spec.get("goal") or f"task {tid}"],
                   cwd=wt, env=env, check=False)
    # newest result.json for this task
    traces = sorted(__import__("glob").glob(os.path.join(run_records_dir, "traces", f"{tid}-*.result.json")))
    record = json.load(open(traces[-1])) if traces else {"task_id": tid, "is_error": True, "outcome": None}
    record.setdefault("branch", branch)
    record["worktree"] = wt
    return record


def default_merge(repo: str | None, base_ref: str, branches: list[str]) -> dict:
    """Real N-branch integration merge (integrate.integration_merge)."""
    return integrate.integration_merge(repo or ".", base_ref, branches)


def _main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Run one autonomous fan-out end to end.")
    ap.add_argument("subtasks_json", help="path to a JSON array of subtasks ({task_id, role|task_type, goal, ...})")
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--lane", default="subscription", choices=["subscription", "api"])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base-ref", default="main")
    ap.add_argument("--worktrees-dir", required=True)
    ap.add_argument("--run-records-dir", required=True)
    ap.add_argument("--max-concurrent", type=int, default=4)
    ap.add_argument("--gate-phase", default=None)
    ap.add_argument("--now", default=None, help="ISO time for the window ledger (default: process time)")
    args = ap.parse_args(argv)

    subtasks = json.load(open(args.subtasks_json))
    now = args.now
    if now is None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def launch(spec):
        return default_launch(spec, base_ref=args.base_ref, worktrees_dir=args.worktrees_dir,
                              run_records_dir=args.run_records_dir, lane=args.lane, repo=args.repo)

    result = execute_fanout(
        subtasks, args.session_id, launch=launch, lane=args.lane, repo=args.repo,
        base_ref=args.base_ref, max_concurrent=args.max_concurrent, now=now,
        gate_phase=args.gate_phase)

    if not result["admitted"]:
        print(f"REFUSED: {result['reason']}", file=sys.stderr)
        return 2
    print(json.dumps({"decision": result["decision"],
                      "merge": result["merge"],
                      "gate": result["gate"],
                      "metrics": {k: result["metrics"].get(k) for k in
                                  ("runs", "completed_tasks", "estimated_savings_usd",
                                   "billed_cost_usd", "guardrail_violations_total")},
                      "teardown_actions": len(result["teardown_plan"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
