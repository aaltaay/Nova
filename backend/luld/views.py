"""One stock's LULD view on the wire (ADR 047; AGENTS.md §3 "LULD bands"). Pure.

``tracker_view`` turns a ``Tracker.view`` and its facts into the shape the Level 2 socket and
``GET /api/luld/{symbol}`` send: the bands, the state, how Nova knows, and the words the
desk shows. ``absent_view`` is a stock Nova has no tracker for.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from luld import rules
from luld.constants_luld import (
    LULD_NEAR_CENTS,
    LULD_NEAR_FRACTION,
    LULD_NOTE,
    LULD_RULES_TEXT,
    LULD_SCHEMA_VERSION,
)
from luld.tracker import Facts

ET = ZoneInfo("America/New_York")

SOURCE_WORDS = {
    "open": "the opening print",
    "reopen": "the reopening print",
    "mean": "the 5-minute average of trades",
    "limit_exit": "the 5-minute average when the limit state ended",
    "open_mean": "the 09:30-09:35 average (no opening print on Nova's tape)",
    "seeded": "the 5-minute average when Nova began watching",
    "first_trade_after_halt": "the first trade after the halt (no reopening print on Nova's tape)",
}


def clock(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S")


def _money(x: float | None) -> str:
    return "?" if x is None else f"{x:,.2f}"


def _near(last: float | None, lower: float | None, upper: float | None) -> str | None:
    if last is None or last <= 0:
        return None
    room = max(last * LULD_NEAR_FRACTION, LULD_NEAR_CENTS)
    if lower is not None and last - lower <= room:
        return "down"
    if upper is not None and upper - last <= room:
        return "up"
    return None


def _distance(last: float | None, lower: float | None, upper: float | None) -> dict[str, float | None] | None:
    if last is None or last <= 0:
        return None
    return {
        "down_pct": round((lower - last) / last, 4) if lower is not None else None,
        "up_pct": round((upper - last) / last, 4) if upper is not None else None,
    }


def state_of(raw: dict[str, Any], facts: Facts, now: float) -> tuple[str, str | None]:
    """The view's state and, when it shows no band, why."""
    if not facts.covered:
        return "off", facts.covered_reason or "LULD does not cover this security"
    if raw["day_open"] is None:
        return "off", "No trading session today (a weekend or a market holiday)"
    if now < raw["day_open"]:
        return "off", f"LULD bands apply 09:30-16:00 ET; it is {clock(now)} ET"
    if now >= raw["day_close"]:
        return "off", "LULD bands ended at 16:00 ET"
    if raw["halted_since"] is not None:
        return "paused", f"Halted since {clock(raw['halted_since'])} ET: no band until it reopens"
    if raw["await_reopen"]:
        return "paused", "The halt ended: the band returns with the reopening print"
    lim = raw["limit"]
    if lim and lim["overdue"]:
        return "pause_due", None
    if raw["reference"] is None:
        warm = raw["warm_until"]
        if warm is not None and now < warm:
            if raw["tape_since"] is not None and raw["tape_since"] > raw["day_open"]:
                return "warming", (f"Nova began watching this stock's tape at {clock(raw['tape_since'])} ET, after it "
                                   f"opened: it needs 5 minutes of trades first (until {clock(warm)} ET)")
            return "warming", "Waiting for the opening print"
        return "unknown", "No trades on Nova's tape to take an average from"
    if facts.prev_close is None:
        return "unknown", "The previous close is not known, so the band's percentage is not either"
    if rules.tier_needed(facts.prev_close) and facts.tier is None:
        return "unknown", (f"Previous close {_money(facts.prev_close)}: the band is 5% for the S&P 500 / Russell "
                           f"1000 and 10% for other stocks, and {facts.tier_basis or 'its tier is not known'}")
    if raw["upper"] is None:
        return "unknown", "No band could be made from the reference"
    if lim:
        return "limit", None
    return "bands", None


def _line(state: str, raw: dict[str, Any], view: dict[str, Any], now: float) -> str:
    """The one line the strip and the hover start with."""
    lo, up = view["lower"], view["upper"]
    approx = "" if view["exact"] and view["tier_sure"] else "≈"
    lim = raw["limit"]
    if state == "limit" and lim:
        left = max(0.0, lim["pause_at"] - now)
        side = "LIMIT DOWN" if lim["side"] == "down" else "LIMIT UP"
        return f"{side} {_money(lim['band'])}: a 5-minute pause in {left:.0f} s if the quote stays on the band"
    if state == "pause_due" and lim:
        side = "lower" if lim["side"] == "down" else "upper"
        return f"PAUSE DUE: 15 s on the {side} band {_money(lim['band'])}; the listing exchange pauses it now"
    if state == "bands":
        return f"LULD {approx}{_money(lo)} - {approx}{_money(up)}"
    return view["reason"] or state


def tracker_view(raw: dict[str, Any], facts: Facts, *, symbol: str, now: float, source: str,
                 track: dict[str, Any] | None = None) -> dict[str, Any]:
    state, reason = state_of(raw, facts, now)
    shows = state in ("bands", "limit", "pause_due")
    lower = raw["lower"] if shows else None
    upper = raw["upper"] if shows else None
    param = raw["parameter"]
    lim = raw["limit"] if shows else None
    anchor = raw["anchor"]
    view: dict[str, Any] = {
        "schema_version": LULD_SCHEMA_VERSION,
        "symbol": symbol,
        "source": source,
        "state": state,
        "exact": bool(raw["exact"]) and shows,
        "lower": lower,
        "upper": upper,
        "reference": raw["reference"] if shows else None,
        "reference_since": raw["reference_since"] if shows else None,
        "reference_source": raw["reference_source"] if shows else None,
        "reference_words": SOURCE_WORDS.get(raw["reference_source"] or "") if shows else None,
        "percent": param.text() if (param is not None and shows) else None,
        "prev_close": facts.prev_close,
        "tier": facts.tier,
        "tier_text": facts.tier_basis,
        # The band's percentage rests on Nova's guess of the tier (over $3.00 only).
        "tier_sure": facts.tier_sure or not rules.tier_needed(facts.prev_close),
        "spread": raw["spread"] if shows and not raw["exact"] else None,
        "limit": lim,
        "straddle": raw["straddle"] if shows else None,
        "anchor": anchor,
        "halted_since": raw["halted_since"],
        "watching_since": raw["tape_since"],
        "warm_until": raw["warm_until"] if state == "warming" else None,
        "gap": raw["gap"],
        "last": raw["last"],
        "distance": _distance(raw["last"], lower, upper) if shows else None,
        "near": _near(raw["last"], lower, upper) if shows else None,
        "reason": reason,
        "history": raw["history"],
        "note": LULD_NOTE,
        "rules": LULD_RULES_TEXT,
        "track": track,
        "as_of": round(now, 3),
    }
    view["text"] = _line(state, raw, view, now)
    return view


def absent_view(symbol: str, *, now: float, source: str, reason: str, state: str = "unknown") -> dict[str, Any]:
    """No tracker for the stock: say why (no tape line, a replay without a recording, off)."""
    return {
        "schema_version": LULD_SCHEMA_VERSION, "symbol": symbol, "source": source, "state": state,
        "exact": False, "lower": None, "upper": None, "reference": None, "reference_since": None,
        "reference_source": None, "reference_words": None, "percent": None, "prev_close": None,
        "tier": None, "tier_text": None, "tier_sure": True, "spread": None, "limit": None, "straddle": None, "anchor": None,
        "halted_since": None, "watching_since": None, "warm_until": None, "gap": None, "last": None,
        "distance": None, "near": None, "reason": reason, "history": [], "note": LULD_NOTE,
        "rules": LULD_RULES_TEXT, "track": None, "as_of": round(now, 3), "text": reason,
    }


def signature(view: dict[str, Any]) -> tuple:
    """What a socket resends on: anything but the clock."""
    lim = view.get("limit") or {}
    return (view["state"], view["exact"], view["lower"], view["upper"], view["reference"],
            lim.get("since"), lim.get("overdue"), view.get("near"), view.get("straddle"), view.get("reason"),
            view.get("warm_until"), view.get("prev_close"), view.get("tier"))


STOCK_READ_SOURCE = "Nova's LULD calculation (the published rules)"


def stock_read_row(view: dict[str, Any] | None) -> dict[str, Any]:
    """The stock read's "Limit up / down band" row (ADR 036's halts group) from a view."""
    def row(value: str, state: str, detail: str | None) -> dict[str, Any]:
        return {"id": "luld", "label": "Limit up / down band", "value": value, "detail": detail, "state": state,
                "source": STOCK_READ_SOURCE, "as_of": view.get("as_of") if view else None}

    if not view:
        return row("Not known", "unknown", "Nova's LULD calculation is not answering")
    state = view["state"]
    if state in ("bands", "limit", "pause_due"):
        mark = "" if view["exact"] and view.get("tier_sure", True) else "≈"
        value = f"{mark}{_money(view['lower'])} - {mark}{_money(view['upper'])}"
        dist = view.get("distance") or {}
        parts = []
        if dist.get("down_pct") is not None:
            parts.append(f"{abs(dist['down_pct']) * 100:.1f}% above the lower band")
        if dist.get("up_pct") is not None:
            parts.append(f"{dist['up_pct'] * 100:.1f}% under the upper")
        detail = "; ".join(parts) or None
        if state != "bands":
            return row(value, "bad", view["text"])
        if view.get("near"):
            side = "lower" if view["near"] == "down" else "upper"
            return row(value, "warn", f"Near the {side} band: 15 s on it pauses the stock for 5 minutes. {detail or ''}".strip())
        return row(value, "info", detail)
    if state == "paused":
        return row("Paused", "info", view["reason"])
    return row("Not known" if state != "off" else "Off", "unknown", view["reason"])
