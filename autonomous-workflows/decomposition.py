"""Decomposition contract (fan-out build §3.2).

The planner emits sub-tasks; this validates them BEFORE `orchestrator.plan_runs`
so the fan-out never launches on a bad plan. Each sub-task:
    {"task_id", "role"|"task_type", "goal", "deps": [task_id...], "touched_paths": [glob...]}
Rules: unique task_ids; deps reference known ids and are acyclic; and NO two
sub-tasks' touched_paths overlap (two workers editing the same package would
guarantee a conflict). `touched_paths` also drives sparse-checkout (§7) later.
"""
from __future__ import annotations

import os

import orchestrator  # reuse merge_order for the acyclic check


def _norm(path: str) -> str:
    """Normalize a path/glob to a plain directory-ish path for overlap checks."""
    p = str(path).strip().rstrip("/")
    for suffix in ("/**", "/*"):
        if p.endswith(suffix):
            p = p[: -len(suffix)]
    return os.path.normpath(p)


def _one_overlaps(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    return a == b or a.startswith(b + os.sep) or b.startswith(a + os.sep)


def _paths_overlap(paths_a: list[str], paths_b: list[str]) -> bool:
    return any(_one_overlaps(a, b) for a in paths_a for b in paths_b)


def find_path_overlaps(subtasks: list[dict]) -> list[tuple]:
    """Pairs of task_ids whose touched_paths overlap (empty if none)."""
    out = []
    for i in range(len(subtasks)):
        for j in range(i + 1, len(subtasks)):
            a = subtasks[i].get("touched_paths") or []
            b = subtasks[j].get("touched_paths") or []
            if a and b and _paths_overlap(a, b):
                out.append((subtasks[i]["task_id"], subtasks[j]["task_id"]))
    return out


def validate_decomposition(subtasks: list[dict]) -> list[dict]:
    """Return `subtasks` if valid; raise ValueError (with a clear message) otherwise."""
    if not isinstance(subtasks, list) or not subtasks:
        raise ValueError("decomposition must be a non-empty list of sub-tasks")

    ids: set[str] = set()
    for st in subtasks:
        tid = st.get("task_id")
        if not tid or not isinstance(tid, str):
            raise ValueError(f"sub-task missing a string task_id: {st!r}")
        if tid in ids:
            raise ValueError(f"duplicate task_id: {tid!r}")
        ids.add(tid)
        if not st.get("goal"):
            raise ValueError(f"sub-task {tid!r} missing a goal")
        if not (st.get("role") or st.get("task_type")):
            raise ValueError(f"sub-task {tid!r} needs a role or task_type")

    for st in subtasks:
        for dep in (st.get("deps") or []):
            if dep not in ids:
                raise ValueError(f"sub-task {st['task_id']!r} depends on unknown id {dep!r}")

    # Acyclic check — reuse the tested topological sort (raises on a cycle).
    deps = {st["task_id"]: (st.get("deps") or []) for st in subtasks}
    orchestrator.merge_order([{"task_id": t} for t in ids], deps)

    overlaps = find_path_overlaps(subtasks)
    if overlaps:
        raise ValueError(
            f"touched_paths overlap between sub-tasks {overlaps} — merge or serialize them"
        )
    return subtasks
