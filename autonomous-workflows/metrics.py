"""Evaluation-metrics harness for the autonomous-workflows initiative (ADH-001).

Operationalizes the evaluation-metrics framework in this session's SPEC.md:
aggregates per-task run-records into the cost / quality / autonomy / throughput /
safety metrics, and evaluates the per-phase go/no-go gates.

Pure functions, no external deps — importable and testable in isolation
(see autonomous-workflows/tests/test_metrics.py). Run:
    python3 autonomous-workflows/tests/test_metrics.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import window_guard

# USD per 1M tokens. Cache reads bill at 0.1x input; cache writes at 1.25x input
# (5-minute TTL). Bedrock non-Anthropic prices are added once the Bedrock
# evaluation lands (see ../bedrock-model-evaluation.md).
PRICES = {
    "claude-fable-5": {"input": 10.00, "output": 50.00},   # ADH-005: hardest-reasoning tier
    "claude-opus-5": {"input": 5.00, "output": 25.00},     # ADH-005: current Opus (planner)
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},   # legacy Opus (still a valid override)
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}
CACHE_READ_MULT = 0.1
CACHE_WRITE_MULT = 1.25

# Outcomes that count as "reached Final Review" (i.e. a completed task).
REVIEWED = {"review_ready", "changes_requested", "merged"}


def compute_cost(tokens: dict, model: str, prices: dict | None = None) -> float:
    """USD cost of one run from its token counts and the model's price row.

    Raises KeyError for an unknown model (fail loud rather than silently free).
    """
    prices = prices or PRICES
    p = prices[model]  # KeyError on unknown model — intentional
    inp, out = p["input"], p["output"]

    def t(k: str) -> float:
        return (tokens.get(k, 0) or 0)

    total = (
        t("input") * inp
        + t("output") * out
        + t("cache_read") * CACHE_READ_MULT * inp
        + t("cache_write") * CACHE_WRITE_MULT * inp
    )
    return total / 1_000_000


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _tok(rec: dict, key: str) -> float:
    return ((rec.get("tokens") or {}).get(key, 0) or 0)


# Subscription pivot (ADH-003 design rev 2.1 D6). A record with no lane /
# cost_basis is a legacy pre-pivot record: every one of those was API-billed,
# so both default to the api/billed side (N1) — this is what keeps the
# pre-pivot aggregate numbers (and tests) exactly unchanged.
def _lane(rec: dict) -> str:
    return rec.get("lane") or "api"


def _basis(rec: dict) -> str:
    return rec.get("cost_basis") or "billed"


def _effective_cost(rec: dict) -> float:
    """A record's cost: the recorded `cost_usd` when positive (the meter that
    produced it — gateway for billed, CLI estimate for estimated), else the
    token×PRICES computation (legacy records carry cost_usd 0.0)."""
    recorded = rec.get("cost_usd") or 0.0
    if recorded > 0:
        return float(recorded)
    return compute_cost(rec.get("tokens", {}), rec["model"])


def aggregate(records: list[dict], *, now: str | None = None, allotments: dict | None = None) -> dict:
    """Aggregate run-records into the SPEC metric values.

    Rate denominators use terminal records only — `paused_rate_limit` is
    neither pass nor fail (D6/F4); its burn still counts in the cost sums
    (the spend was real).
    """
    terminal = [r for r in records if r.get("outcome") != "paused_rate_limit"]
    reviewed = [r for r in terminal if r.get("outcome") in REVIEWED]
    completed = len(reviewed)
    merged = sum(1 for r in terminal if r.get("outcome") == "merged")

    billed_cost = sum(_effective_cost(r) for r in records if _basis(r) == "billed")
    estimated_cost = sum(_effective_cost(r) for r in records if _basis(r) == "estimated")
    total_cost = billed_cost + estimated_cost  # combined actual + estimated (D6)
    savings = sum(_effective_cost(r) for r in records
                  if _lane(r) == "subscription" and _basis(r) == "estimated")

    lanes: dict[str, dict] = {}
    for r in records:
        lane = lanes.setdefault(_lane(r), {"runs": 0, "completed_tasks": 0, "cost_usd": 0.0})
        lane["runs"] += 1
        lane["cost_usd"] += _effective_cost(r)
        if r.get("outcome") in REVIEWED:
            lane["completed_tasks"] += 1
    for lane in lanes.values():
        lane["cost_per_completed_task"] = (
            lane["cost_usd"] / lane["completed_tasks"] if lane["completed_tasks"] else 0.0)

    explicit = sum(1 for r in records
                   if r.get("lane") is not None and r.get("cost_basis") is not None)
    lane_coverage = (explicit / len(records)) if records else 0.0

    input_total = sum(_tok(r, "input") for r in records)
    cache_read_total = sum(_tok(r, "cache_read") for r in records)
    cache_denom = input_total + cache_read_total

    def _input_requests(r: dict) -> int:
        return ((r.get("human") or {}).get("input_requests", 0) or 0)

    unattended = (
        sum(1 for r in reviewed if _input_requests(r) == 0) / completed
        if completed else 0.0
    )

    ran = [r for r in terminal if (r.get("tests") or {}).get("ran")]
    passed = sum(1 for r in ran if (r.get("tests") or {}).get("passed"))

    change_requested = sum(1 for r in reviewed if r.get("outcome") == "changes_requested")

    # token share by model
    mix_tokens: dict[str, float] = {}
    for r in records:
        m = r["model"]
        tt = _tok(r, "input") + _tok(r, "output") + _tok(r, "cache_read") + _tok(r, "cache_write")
        mix_tokens[m] = mix_tokens.get(m, 0) + tt
    total_tokens = sum(mix_tokens.values())
    model_mix = {m: (v / total_tokens if total_tokens else 0.0) for m, v in mix_tokens.items()}

    diffs = []
    for r in records:
        fd, st = _parse(r.get("first_diff_at")), _parse(r.get("started_at"))
        if fd and st:
            diffs.append((fd - st).total_seconds())

    return {
        "runs": len(records),
        "runs_paused": len(records) - len(terminal),
        "completed_tasks": completed,
        "total_cost_usd": total_cost,
        "billed_cost_usd": billed_cost,
        "estimated_cost_usd": estimated_cost,
        "estimated_savings_usd": savings,
        "lanes": lanes,
        "lane_coverage": lane_coverage,
        "cost_per_completed_task": (total_cost / completed) if completed else 0.0,
        "cost_per_merged_pr": (total_cost / merged) if merged else None,
        "cache_hit_rate": (cache_read_total / cache_denom) if cache_denom else 0.0,
        "model_mix": model_mix,
        "unattended_completion_rate": unattended,
        "test_pass_rate": (passed / len(ran)) if ran else 0.0,
        "change_request_rate": (change_requested / completed) if completed else 0.0,
        "guardrail_violations_total": sum(r.get("guardrail_violations", 0) or 0 for r in records),
        "mean_time_to_first_diff_s": (sum(diffs) / len(diffs)) if diffs else 0.0,
        # ADH-005: advisory per-family window headroom (present only when `now` given).
        "window_headroom": (window_guard.window_headroom(records, None, now, allotments)
                            if now is not None else None),
    }


def evaluate_gates(m: dict, phase: str) -> dict:
    """Pass/fail the go/no-go gates for a phase (SPEC → Phase go/no-go gates)."""
    if phase == "phase2":
        g = {
            "guardrail_zero": m["guardrail_violations_total"] == 0,
            "cost_captured": m["total_cost_usd"] > 0,
            "tests_green": m["test_pass_rate"] == 1.0,
        }
        g["passed"] = all(g.values())
        return g
    if phase == "subscription-pivot":
        lanes = m.get("lanes", {})
        has_api = lanes.get("api", {}).get("runs", 0) > 0
        has_sub = lanes.get("subscription", {}).get("runs", 0) > 0
        g = {
            "guardrail_zero": m["guardrail_violations_total"] == 0,
            # 100% of records carry explicit lane + cost_basis (D6)
            "lane_captured": m.get("lane_coverage", 0.0) == 1.0,
            # lane-aware predicate (D6, replacing total_cost_usd > 0):
            # each lane present must have registered its kind of cost
            "cost_captured": (
                (not has_api or m["billed_cost_usd"] > 0)
                and (not has_sub or m["estimated_cost_usd"] > 0)
            ),
            "subscription_review_ready":
                lanes.get("subscription", {}).get("completed_tasks", 0) >= 1,
        }
        g["passed"] = all(g.values())
        return g
    # default: only the hard safety gate applies
    g = {"guardrail_zero": m["guardrail_violations_total"] == 0}
    g["passed"] = g["guardrail_zero"]
    return g


def load_records(path: str) -> list[dict]:
    """Load run-records from a .jsonl file, a .json file/array, or a directory of .json."""
    p = Path(path)
    if p.is_dir():
        recs: list[dict] = []
        for f in sorted(p.glob("*.json")):
            data = json.loads(f.read_text())
            recs.extend(data if isinstance(data, list) else [data])
        return recs
    text = p.read_text()
    if p.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    return data if isinstance(data, list) else [data]


def stage_metrics(records: list[dict]) -> dict:
    """Per-stage counts + pass rate for the dev-lifecycle (pass = outcome reached
    review/merged). Records without a `stage` are grouped under 'unstaged'.
    `paused_rate_limit` records are waiting, not failed (D6/F4): excluded from
    count/pass_rate, reported per-stage under `paused`."""
    passed = {"review_ready", "merged"}
    groups: dict[str, list] = {}
    for r in records:
        groups.setdefault(r.get("stage", "unstaged"), []).append(r)
    out = {}
    for stage, rs in groups.items():
        paused = sum(1 for r in rs if r.get("outcome") == "paused_rate_limit")
        terminal = [r for r in rs if r.get("outcome") != "paused_rate_limit"]
        n = len(terminal)
        p = sum(1 for r in terminal if r.get("outcome") in passed)
        out[stage] = {"count": n, "pass_rate": (p / n if n else 0.0), "paused": paused}
    return out
