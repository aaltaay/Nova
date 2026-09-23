"""The Five Pillars at the moment a setup arms, and the grade they give it.

Read from what HOD Momo already enriched for the symbol (IBKR price, % change,
relative volume, float) and the catalyst classifier (ADR 024): the News pillar
passes only for a real, company-specific catalyst published since the prior
close -- the same verdict the backfilled history uses, never "any article". A
pillar Nova does not know is ``None`` and never counts as a pass.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from constants_catalysts import CATALYST_UNCLASSIFIED, CATALYST_VERDICT_CATALYST
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


def _finite(value: Any) -> float | None:
    """A snapshot number, or None when it is missing or not finite (unknown, never failed)."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


_CATALYST_KEYS = ("verdict", "category", "strength", "title", "source", "published_ts", "url", "negative_too",
                  "rules_version", "sources_answered", "news_pending", "halt_code")


def news_pillar(catalyst: dict[str, Any] | None) -> bool | None:
    """True for a classified catalyst; None when unknown -- nothing read, news pending behind a halt, or
    only an unclassified company headline (right about half the time on the labelled samples); else False."""
    if catalyst is None:
        return None
    if catalyst.get("verdict") == CATALYST_VERDICT_CATALYST:
        return None if catalyst.get("category") == CATALYST_UNCLASSIFIED else True
    return None if catalyst.get("news_pending") else False


def read_pillars(symbol: str, now: float | None = None) -> dict[str, Any]:
    snap = None
    try:
        import hod_momo

        snap = hod_momo.get_ticker_snapshot(symbol)
    except Exception:
        logger.debug("setup grade: no HOD snapshot for %s", symbol, exc_info=True)
    catalyst = None
    try:
        from catalysts import live as catalyst_live

        catalyst = catalyst_live.verdict_for(symbol, now)
    except Exception:
        logger.warning("setup grade: catalyst verdict failed for %s", symbol, exc_info=True)
    return {
        "price": _finite(getattr(snap, "price", None)) or None,
        "change_pct": _finite(getattr(snap, "change_pct", None)),
        "rvol": _finite(getattr(snap, "rvol", None)),
        "float": _finite(getattr(snap, "float_shares", None)),
        "news": news_pillar(catalyst),
        "headline": (catalyst or {}).get("title"),
        "catalyst": None if catalyst is None else {k: catalyst.get(k) for k in _CATALYST_KEYS},
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
