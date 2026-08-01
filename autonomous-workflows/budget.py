"""Phase-2 budget guard — local, pre-flight enforcement of the $200/month cap.

Layer 4 of the defense-in-depth budget design (the local pre-flight
guard that stops runs gracefully below the gateway's hard cap):
the worker supervisor calls `can_start()` before every run/turn and
`status()` for alerts, so runs stop *gracefully below* the hard cap rather
than dying when the gateway (layer 1) refuses traffic at $200.

Trusts the `cost_usd` recorded on each run-record (the actual gateway-reported
spend). Pure functions, no external deps.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime

MONTHLY_CAP_USD = 200.0

# Fractions of the cap. HALT leaves headroom below the gateway hard cap so any
# in-flight run can finish without tripping the $200 wall mid-task.
NOTICE, WARN, HALT = 0.5, 0.8, 0.9


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def month_to_date_spend(records: list[dict], now: datetime, ts_field: str = "started_at") -> float:
    """Sum recorded cost for runs in `now`'s calendar month (year+month match)."""
    total = 0.0
    for r in records:
        ts = _parse(r.get(ts_field))
        if ts and ts.year == now.year and ts.month == now.month:
            total += float(r.get("cost_usd", 0) or 0)
    return total


def remaining(spend: float, cap: float = MONTHLY_CAP_USD) -> float:
    return cap - spend


def fraction(spend: float, cap: float = MONTHLY_CAP_USD) -> float:
    return spend / cap if cap else 0.0


def status(spend: float, cap: float = MONTHLY_CAP_USD) -> str:
    """'ok' | 'notice' (>=50%) | 'warn' (>=80%) | 'halt' (>=90%) — drives alerts."""
    f = fraction(spend, cap)
    if f >= HALT:
        return "halt"
    if f >= WARN:
        return "warn"
    if f >= NOTICE:
        return "notice"
    return "ok"


def can_start(spend: float, est_cost: float = 0.0, cap: float = MONTHLY_CAP_USD, reserve: float = HALT) -> bool:
    """True iff starting a run of ~`est_cost` keeps month-to-date spend at or
    below the reserve threshold (default 90% of cap). Fail-safe: block on doubt."""
    return (spend + est_cost) <= cap * reserve


def reconcile_spend(local_estimate: float, gateway_spend: float | None) -> float:
    """The value budget decisions should use: the gateway's `/global/spend`
    meter is the authoritative, shared, server-side ceiling (design §1) — prefer
    it over the local estimate. Fail-safe when the two disagree or the gateway
    is unreachable: never let a stale/low/missing gateway read mask real local
    spend, so take the larger of the two."""
    if gateway_spend is None:
        return local_estimate
    return max(local_estimate, gateway_spend)


def fetch_global_spend(base_url: str, api_key: str, timeout: float = 5.0, opener=None) -> float | None:
    """GET {base_url}/global/spend -> the gateway's authoritative month-to-date
    spend, or None on any failure (network, non-200, bad payload) so callers
    fall back via `reconcile_spend`. `opener` is injectable for tests — it must
    take a `urllib.request.Request` and return a context-managed response with
    `.read()`; defaults to `urllib.request.urlopen`."""
    opener = opener or (lambda req: urllib.request.urlopen(req, timeout=timeout))
    req = urllib.request.Request(
        f"{base_url}/global/spend",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with opener(req) as resp:
            data = json.loads(resp.read())
        return float(data["spend"])
    except Exception:
        return None


def worst_case_overshoot(per_key_budget: float, concurrent_requests: int) -> float:
    """Approximate worst-case overshoot past a per-key budget: the gateway's
    cap is a *soft* ceiling under concurrency (review-2 nit A1) — up to
    `concurrent_requests` in-flight requests can each slip past the meter
    before it updates, so worst case ~= per_key_budget * concurrent_requests."""
    return per_key_budget * concurrent_requests


def safe_concurrency_cap(per_key_budget: float, cap: float = MONTHLY_CAP_USD, safety_margin: float = 0.5) -> int:
    """Largest worker concurrency whose `worst_case_overshoot` stays within
    `safety_margin` of the spend-to-halt budget (`cap * HALT`) — a conservative
    fraction of what may be spent before the local guard halts, leaving the
    remainder as slack for in-flight runs to finish cleanly."""
    if per_key_budget <= 0:
        return 0
    headroom = cap * HALT * safety_margin
    return max(1, int(headroom // per_key_budget))
