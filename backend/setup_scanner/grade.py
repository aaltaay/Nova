"""The Five Pillars at the moment a setup arms, and the grade they give it.

Read from what HOD Momo already enriched for the symbol (IBKR price, % change,
relative volume, float) and the scanner's news badge (a headline today). A
pillar Nova does not know is ``None`` and never counts as a pass.
"""
from __future__ import annotations

import logging
from typing import Any

from constants_setups import (
    SETUPS_GRADE_A,
    SETUPS_GRADE_B,
    SETUPS_GRADE_C,
    SETUPS_PILLAR_MAX_FLOAT,
    SETUPS_PILLAR_MAX_PRICE,
    SETUPS_PILLAR_MIN_CHANGE_PCT,
    SETUPS_PILLAR_MIN_PRICE,
    SETUPS_PILLAR_MIN_RVOL,
)

logger = logging.getLogger(__name__)


def read_pillars(symbol: str) -> dict[str, Any]:
    snap = None
    try:
        import hod_momo

        snap = hod_momo.get_ticker_snapshot(symbol)
    except Exception:
        logger.debug("setup grade: no HOD snapshot for %s", symbol, exc_info=True)
    headline = None
    try:
        import scanner_news_badge

        headline = scanner_news_badge.headline_for(symbol)
    except Exception:
        logger.debug("setup grade: no news badge for %s", symbol, exc_info=True)
    return {
        "price": getattr(snap, "price", None) or None,
        "change_pct": getattr(snap, "change_pct", None),
        "rvol": getattr(snap, "rvol", None),
        "float": getattr(snap, "float_shares", None),
        "news": headline is not None,
        "headline": headline,
    }


def grade(p: dict[str, Any]) -> tuple[str, dict[str, bool | None]]:
    def ok(value, test):
        return None if value is None else bool(test(value))
    checks = {
        "price": ok(p.get("price"), lambda v: SETUPS_PILLAR_MIN_PRICE <= v <= SETUPS_PILLAR_MAX_PRICE),
        "change": ok(p.get("change_pct"), lambda v: v >= SETUPS_PILLAR_MIN_CHANGE_PCT),
        "rvol": ok(p.get("rvol"), lambda v: v >= SETUPS_PILLAR_MIN_RVOL),
        "news": p.get("news"),
        "float": ok(p.get("float"), lambda v: 0 < v <= SETUPS_PILLAR_MAX_FLOAT),
    }
    passed = sum(1 for v in checks.values() if v)
    known = all(v is not None for v in checks.values())
    if known and passed == 5:
        return SETUPS_GRADE_A, checks
    if passed == 4:
        return SETUPS_GRADE_B, checks
    return SETUPS_GRADE_C, checks
