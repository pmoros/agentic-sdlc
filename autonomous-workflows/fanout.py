"""Fan-out scheduler + run manifest + teardown plan (build §3.4).

The pure/file-level core the parallel launcher is built on:
  - `runnable_now` — a dep-aware, bounded-concurrency scheduler (gives "in parallel"
    a hard cap — Gate-A must-fix 2).
  - the run manifest — aggregate observability (which of N workers is where).
  - `teardown_plan` — idempotent, manifest-driven cleanup (revoke keys, remove
    worktrees, prune branches), safe to re-run after a crash (Gate-A must-fix 7).
The actual subprocess launch and the git/key calls are thin wrappers around these.
"""
from __future__ import annotations

import json
from datetime import datetime


def _parse(ts):
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def runnable_now(task_ids: list[str], deps: dict, done: set, running: set,
                 max_concurrent: int, now: str | None = None,
                 paused_until: dict | None = None) -> list[str]:
    """Task ids that may start now: deps satisfied (all in `done`), not already
    done/running, not paused, up to the free slots (`max_concurrent - running`).
    Deterministic (sorted).

    `paused_until` (D7/F5) maps task_id -> ISO time until which the task is not
    runnable — a rate-limit `resets_at` (`halt_rate_limit`) or a churn-breaker
    backoff (`defer_window`). Once `now` reaches that time the task is re-admitted
    (the 5h resume lifecycle). With no `paused_until`/`now`, behaviour is unchanged."""
    slots = max_concurrent - len(running)
    if slots <= 0:
        return []
    now_dt = _parse(now)
    paused_until = paused_until or {}

    def _paused(t):
        until = _parse(paused_until.get(t))
        return until is not None and now_dt is not None and now_dt < until

    ready = [
        t for t in task_ids
        if t not in done and t not in running
        and all(d in done for d in deps.get(t, []))
        and not _paused(t)
    ]
    return sorted(ready)[:slots]


def new_manifest(run_id: str, specs: list[dict]) -> dict:
    """A fresh run manifest: one entry per spec, status `pending`.

    Each agent carries `lane` + per-agent `model`/`window_est_usd` (rev 2.1 N2 —
    the subscription lane's tier-aware `committed_burn` needs both). `key_id`
    stays None; a gateway key is only ever minted on the api lane, so
    `teardown_plan` (key_id-guarded) revokes nothing for subscription workers."""
    return {
        "run_id": run_id,
        "agents": {
            s["task_id"]: {
                "branch": s.get("branch"),
                "worktree": s.get("worktree"),
                "lane": s.get("lane", "subscription"),
                "model": s.get("model"),
                "window_est_usd": s.get("window_est_usd"),
                "key_id": None,
                "pid": None,
                "status": "pending",
                "trace": None,
            }
            for s in specs
        },
    }


def set_status(manifest: dict, task_id: str, status: str, **fields) -> dict:
    a = manifest["agents"][task_id]
    a["status"] = status
    a.update(fields)
    return manifest


def write_manifest(path: str, manifest: dict) -> None:
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)


def read_manifest(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def teardown_plan(manifest: dict, keep=()) -> list[dict]:
    """Idempotent teardown actions from a manifest: revoke keys, remove worktrees,
    delete branches (except those in `keep`, retained for an approved merge).
    Ordered keys → worktrees → branches."""
    keep = set(keep)
    revoke, worktrees, branches = [], [], []
    for tid, a in manifest["agents"].items():
        if a.get("key_id"):
            revoke.append({"action": "revoke_key", "key_id": a["key_id"], "task_id": tid})
        if a.get("worktree"):
            worktrees.append({"action": "remove_worktree", "path": a["worktree"], "task_id": tid})
        if a.get("branch") and tid not in keep:
            branches.append({"action": "delete_branch", "branch": a["branch"], "task_id": tid})
    return revoke + worktrees + branches
