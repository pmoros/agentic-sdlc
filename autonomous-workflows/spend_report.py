"""Concise human-readable budget status line, built on the Phase-2 budget
guard (budget.py). Intended for quick CLI/log output, not machine parsing.
"""
from __future__ import annotations

import budget


def format_status(spend: float, cap: float | None = None) -> str:
    """One-line status: level, spend/cap in dollars, percent used, dollars remaining."""
    cap = budget.MONTHLY_CAP_USD if cap is None else cap
    level = budget.status(spend, cap)
    pct_used = budget.fraction(spend, cap) * 100
    left = budget.remaining(spend, cap)
    return (
        f"[{level}] ${spend:.2f} / ${cap:.2f} "
        f"({pct_used:.1f}% used, ${left:.2f} remaining)"
    )
