"""The targets of a trade you hold (#845, operator decisions 2026-10-09 and 2026-10-12). Pure.

The same menu every setup scanner and the plan take their targets from (``setup_scanner/targets.py``),
read from the position: the menu's defaults from your average cost, today's map (the read's intraday
zones) and the high of day (a short: the low of day). ``target`` is the first part's sell, ``target2`` the
rest's (or None: everything at target 1) and ``target1_fraction`` the share sold at target 1 -- the keys
the held block carries for Nova's exits (``stock_mode``) and the held card. Each target says when a
1-minute candle since you held reached it (``traded_at``).
"""
from __future__ import annotations

from typing import Any

from constants_setups import SETUPS_TARGET_FIXED
from setup_scanner import targets as menu
from stock_read.level_map import EPS, hhmm, px
from stock_read.level_notes import _cents

MIN = 60


def build(*, side: str, avg: float, bars: list[dict[str, Any]], intraday: list[dict[str, Any]],
          since: float | None, price: float | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None, float]:
    """``(target, target2, target1_fraction)``: each target ``{price, kind, rule, traded_at}``."""
    short = side == "short"
    seen = [float(b["l"] if short else b["h"]) for b in bars] + ([float(price)] if price is not None else [])
    extreme = (min(seen) if short else max(seen)) if seen else None
    got = menu.plan(None, side="short" if short else "long", entry=avg, levels=intraday, hod=extreme)
    after = [b for b in bars if since is not None and float(b["t"]) + MIN > since]

    def one(leg: menu.Leg | None) -> dict[str, Any] | None:
        if leg is None:
            return None
        hit = next((float(b["t"]) for b in after
                    if (float(b["l"]) <= leg.price + EPS if short else float(b["h"]) >= leg.price - EPS)), None)
        rule = f"your average {leg.why}" if leg.kind == SETUPS_TARGET_FIXED else leg.why
        return {"price": round(leg.price, 4), "kind": leg.kind, "rule": rule, "traded_at": hit}

    return one(got.first), one(got.second), got.fraction


def note(target: dict[str, Any] | None, price: float | None, *, short: bool, name: str) -> dict[str, Any] | None:
    """The card's line for one target: past it (a candle since you held reached it), or how far it is."""
    if target is None:
        return None
    if target.get("traded_at"):
        return {"state": "ok", "text": f"{name} {px(target['price'])} traded at {hhmm(target['traded_at'])}: "
                                      "you are past it", "detail": target["rule"]}
    if price is None:
        return None
    gap = (price - target["price"]) if short else (target["price"] - price)
    where = "below" if short else "above"
    return {"state": "info", "text": f"{name} {px(target['price'])} is {_cents(gap)} {where}", "detail": target["rule"]}
