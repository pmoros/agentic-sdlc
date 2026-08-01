"""Subscription-lane window guard (ADH-003 subscription pivot, design rev 2.1).

The advisory layer of the two-layer reactive window model (D3): a per-tier
rolling-window burn ledger over run-records plus committed (in-flight) burn
from the fan-out manifest, checked against self-imposed estimated-USD
allotments {5h, 7d, 7d_sonnet}. The authoritative layer is limit-error
detection (`parse_limit_error`) — callers must enforce the D3.2
preconditions (attempt the parse only on a CLI-signalled error, and only on
CLI error channels: stderr, or the result event's text when that event has
is_error=true; never a success event's model-authored result).

Pure logic only — no I/O, no clock reads (`now` is always an argument), no
subprocess. The api lane's guard is `budget.py`, deliberately untouched (D2).
"""
import re
from datetime import datetime

WINDOW_5H = 5 * 3600
WINDOW_7D = 7 * 24 * 3600

# Self-imposed worker share of the account's shared windows (D3.1/D4);
# estimated-USD proxy units, env-overridable at the run-worker layer.
DEFAULT_ALLOTMENTS = {"5h": 5.0, "7d": 40.0, "7d_sonnet": 25.0, "7d_fable": 20.0}

# Below this remaining est-USD, a family's window is "tight" (ADH-005 D5). Env-tunable.
HEADROOM_TIGHT_MARGIN = 1.0

# Windows each family is metered against (ADH-005 §2): everyone shares 5h + 7d(all);
# Sonnet also has its own weekly cap; Fable is ceilinged at <=50% weekly. Opus/Haiku
# have no own weekly cap (assumed pending /usage) -> only the shared windows apply.
_FAMILY_WINDOWS = {
    "opus":   (("5h", WINDOW_5H, None), ("7d", WINDOW_7D, None)),
    "haiku":  (("5h", WINDOW_5H, None), ("7d", WINDOW_7D, None)),
    "sonnet": (("5h", WINDOW_5H, None), ("7d", WINDOW_7D, None), ("7d_sonnet", WINDOW_7D, "sonnet")),
    "fable":  (("5h", WINDOW_5H, None), ("7d", WINDOW_7D, None), ("7d_fable", WINDOW_7D, "fable")),
}

_FAMILIES = ("opus", "sonnet", "haiku", "fable")

# Strict, documented limit strings only (D3.2) — loose paraphrases must not
# match, or a task merely quoting the concept could pause the fleet.
_LIMIT_RE = re.compile(r"You've hit your (session|weekly) limit")
_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T[0-9:.]+(?:[+-]\d{2}:\d{2}|Z)?")


def _parse(ts):
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _family(record_or_agent):
    model = record_or_agent.get("model") or ""
    for fam in _FAMILIES:
        if fam in model:
            return fam
    return "other"


def tier(record):
    """Model-family tier of a run-record: opus|sonnet|haiku|other.

    Pinned contract (rev 2 F1): a substring match on record["model"], NOT an
    inversion of routing.ROLE_MODEL — the two diverge the day a second
    variant of a family ships.
    """
    return _family(record)


def _subscription_estimated(record):
    # Lane filter (rev 2 A4): only subscription-lane estimated burn belongs
    # in the window ledger. Legacy records (no lane/cost_basis) are billed
    # api spend by definition (rev 2.1 N1) and never touch the windows.
    return (record.get("lane") == "subscription"
            and record.get("cost_basis") == "estimated")


def window_burn(records, now, window_s, tier=None):
    """Sum estimated-USD burn of subscription records started inside the
    rolling window (now - window_s, now]. Attribution is by started_at —
    optimistic near window edges for long runs (accepted bias, rev 2 A5).
    """
    now_dt = _parse(now)
    total = 0.0
    for r in records:
        if not _subscription_estimated(r):
            continue
        if tier is not None and _family(r) != tier:
            continue
        started = _parse(r.get("started_at"))
        if started is None or now_dt is None:
            continue
        age = (now_dt - started).total_seconds()
        if 0 <= age < window_s:
            total += float(r.get("cost_usd") or 0.0)
    return total


def _agents(manifest):
    agents = (manifest or {}).get("agents") or []
    if isinstance(agents, dict):
        return list(agents.values())
    return list(agents)


def committed_burn(manifest, tier=None, default_est_usd=1.0):
    """In-flight reservation (rev 2 A4): the per-worker window allotments of
    manifest-`running` subscription workers count as already-spent — the
    `budget.worst_case_overshoot` precedent carried over. Agents carry their
    own `window_est_usd` + `model` (rev 2.1 N2); a missing estimate falls
    back to `default_est_usd` (conservative: reserves something, never
    nothing).
    """
    total = 0.0
    for a in _agents(manifest):
        if a.get("status") != "running":
            continue
        if a.get("lane") != "subscription":
            continue
        if tier is not None and _family(a) != tier:
            continue
        est = a.get("window_est_usd")
        total += float(est) if est is not None else float(default_est_usd)
    return total


def parse_limit_error(text, channel):
    """Strict detector for the two documented limit strings (D3.2).

    Returns {"kind","resets_at","channel","matched_text"} or None. The
    caller enforces the preconditions: only call this on a CLI-signalled
    error, and only with CLI error-channel text. resets_at is the ISO
    timestamp in the message when one is present, else None (the pause is
    then visible-but-unscheduled; next_resume_at skips it).
    """
    if not text or not isinstance(text, str):
        return None
    m = _LIMIT_RE.search(text)
    if not m:
        return None
    line = next((ln for ln in text.splitlines() if m.group(0) in ln), text)
    iso = _ISO_RE.search(line)
    resets_at = iso.group(0) if iso and _parse(iso.group(0)) else None
    return {"kind": m.group(1), "resets_at": resets_at,
            "channel": channel, "matched_text": line.strip()}


def can_start(records, manifest, now, allotments=None):
    """Advisory pre-flight (D3.1): completed + committed burn must fit inside
    every window — 5h all-models, 7d all-models, 7d sonnet-specific (the two
    weekly caps Discovery documents). Advisory only; the authoritative
    backstop is the limit-error path.
    """
    allot = dict(DEFAULT_ALLOTMENTS)
    allot.update(allotments or {})
    checks = (
        (WINDOW_5H, None, allot["5h"]),
        (WINDOW_7D, None, allot["7d"]),
        (WINDOW_7D, "sonnet", allot["7d_sonnet"]),
        (WINDOW_7D, "fable", allot["7d_fable"]),
    )
    for window_s, fam, cap in checks:
        burn = (window_burn(records, now, window_s, tier=fam)
                + committed_burn(manifest, tier=fam))
        if burn > cap:
            return False
    return True


def window_headroom(records, manifest, now, allotments=None, margin=HEADROOM_TIGHT_MARGIN):
    """Per-family remaining est-USD headroom (ADH-005 D5): for each family, the MIN
    over its applicable windows of `allot[window] - (completed_burn + committed_burn)`.
    Opus/Haiku see only the shared 5h + 7d(all), so a binding shared cap drives their
    headroom down too — this is what lets the router gate a Sonnet->Opus upgrade on
    Opus's *own* number. Returns {family: {"headroom": float, "tight": bool}}."""
    allot = dict(DEFAULT_ALLOTMENTS)
    allot.update(allotments or {})
    out = {}
    for fam, windows in _FAMILY_WINDOWS.items():
        headroom = min(
            allot[key] - (window_burn(records, now, window_s, tier=filt)
                          + committed_burn(manifest, tier=filt))
            for (key, window_s, filt) in windows
        )
        out[fam] = {"headroom": headroom, "tight": headroom < margin}
    return out


def next_resume_at(records, now):
    """Earliest future resets_at among paused runs (feeds runnable_now's
    paused_until filter, rev 2 F5). Past resets and null resets_at are
    skipped — a null-reset pause stays visible via its record, it just has
    no schedulable resume time.
    """
    now_dt = _parse(now)
    best = None
    for r in records:
        if r.get("outcome") != "paused_rate_limit":
            continue
        resets = _parse((r.get("limit") or {}).get("resets_at"))
        if resets is None or now_dt is None or resets <= now_dt:
            continue
        if best is None or resets < best:
            best = resets
    return best.isoformat() if best else None
