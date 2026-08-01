"""Conflict detection + merged-tree QA (fan-out build §3.3).

The faithful N-branch join the Gate-A review required: merge worker branches one
at a time (in `merge_order`) onto a disposable integration branch, so conflicts
are detected on the *cumulative* tree — two branches clean vs base can still
conflict with each other. The first conflicting merge is aborted and reported
(→ `join_decision` returns `needs_human_merge`); if all merge cleanly, QA runs on
the integrated tree (not per-branch). Side-effectful (git); tested against
throwaway fixtures per the Script Testing Standard.
"""
from __future__ import annotations

import subprocess


def _git(repo: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r


def integration_merge(repo: str, base_ref: str, branches: list[str],
                      integration_branch: str = "auto/_integration") -> dict:
    """Sequentially merge `branches` (already in `merge_order`) onto a fresh
    integration branch off `base_ref`. Stops and aborts at the first conflicting
    merge. Returns:
        {integration_branch, order, merged: [...], conflict: bool, conflicting_branch}
    """
    _git(repo, "checkout", "-B", integration_branch, base_ref)
    merged: list[str] = []
    conflict = False
    conflicting = None
    for b in branches:
        r = _git(repo, "merge", "--no-ff", "-m", f"integrate {b}", b, check=False)
        if r.returncode != 0:
            _git(repo, "merge", "--abort", check=False)   # leave the tree clean
            conflict = True
            conflicting = b
            break
        merged.append(b)
    return {
        "integration_branch": integration_branch,
        "order": list(branches),
        "merged": merged,
        "conflict": conflict,
        "conflicting_branch": conflicting,
    }


def run_check(cwd: str, command: list[str]) -> dict:
    """Run a QA command (e.g. the test suite) on the integrated tree; report pass/fail.
    QA runs on the MERGED tree, not per-branch — this is what catches semantic
    incompatibilities git can't see."""
    r = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return {"ok": r.returncode == 0, "returncode": r.returncode,
            "stdout": r.stdout, "stderr": r.stderr}
