"""Window-/strength-aware model selection for the subscription lane (ADH-005 D4).

A thin PURE layer above `routing.select_model`: the strength map picks the base
model; this decides whether the live per-family window headroom (from
`window_guard.window_headroom`) should **upgrade** that choice, leave it, or
**defer** it — never downgrade it.

Fail-closed invariant: the returned model is either the strength-map model, a
*strictly stronger* family with its own headroom, or a defer — never a weaker
model, and Fable is never reached by rebalancing (it's the `architect` role only).
The only upgrade ladder is **Sonnet -> Opus 5**; Opus never climbs to Fable.

Pure logic only — no I/O, no clock; `window` is precomputed by the caller.
"""
from __future__ import annotations

import window_guard

# The single upgrade target (D4 rule 3). No ladder step above Opus.
UPGRADE_MODEL = "claude-opus-5"

# Which task types may be rebalanced / escalated (D3/D4). Deterministic, human-set.
DEFAULT_ELIGIBILITY = {
    "upgrade_sonnet_to_opus": {
        "code", "coding", "implement", "fix", "refactor", "feat",
        "build", "test", "qa", "verify", "validate", "chore", "docs",
    },
    # architect/escalation types (Fable) — informational; Fable is reached only via
    # the `architect` role in routing.py, never auto-escalated here (D3).
    "escalate_to_fable": {"architect", "hard-debug", "deep-research"},
}


def choose_model(spec: dict, window: dict | None, *,
                 eligibility: dict = DEFAULT_ELIGIBILITY,
                 allotments: dict | None = None) -> dict:
    """Return {"model", "reason", "action"} for a subscription-lane spec.

    `spec` carries the strength-map `model` (from `routing.select_model`) and its
    `task_type`. `window` is `{family: {"headroom", "tight"}}` (window_guard). With
    no `window`, the strength-map model is used unchanged. `action` is "route" or
    "defer_window" (the worker waits for the window to reset, à la supervisor)."""
    base = spec.get("model")
    task_type = (spec.get("task_type") or "").lower()
    if not window:
        return {"model": base, "reason": "no_window", "action": "route"}

    fam = window_guard.tier({"model": base})

    # Fable base (an `architect` task): gate on the fable ceiling; never downgrade.
    if fam == "fable":
        if window.get("fable", {}).get("tight"):
            return {"model": base, "reason": "fable_ceiling", "action": "defer_window"}
        return {"model": base, "reason": "architect", "action": "route"}

    # Sonnet base, its weekly window tight: upgrade to Opus *only* if Opus has its
    # own headroom; if Opus is also tight (or the shared cap is binding), defer.
    if fam == "sonnet" and window.get("sonnet", {}).get("tight"):
        eligible = task_type in eligibility["upgrade_sonnet_to_opus"]
        if not eligible:
            return {"model": base, "reason": "sonnet_tight_not_eligible", "action": "route"}
        if window.get("opus", {}).get("tight"):
            return {"model": base, "reason": "sonnet_and_opus_tight", "action": "defer_window"}
        return {"model": UPGRADE_MODEL, "reason": "sonnet_tight_upgraded_to_opus", "action": "route"}

    # Opus/Haiku base, or Sonnet not tight: the strength-map model stands. A tight
    # Opus/Haiku window is an admission concern (can_start/supervisor), not selection.
    return {"model": base, "reason": "strength_map", "action": "route"}
