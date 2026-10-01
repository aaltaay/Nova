"""Too thin to trade, on the Trader's read (operator decision 2026-10-01; the rule is
``setup_scanner.liquidity``). Pure.

The read measures the stock as the operator sees it: today's volume (the scanner row's, repriced by
the L1 line), the chart's own stored minutes for the day's average price and the last five closed
minutes, and the Level 2 book on the Trader tab, walked for the desk's risk per trade over the plan's
risk a share. Stored minutes that end more than ``SETUPS_THIN_BARS_STALE_SEC`` before now leave the
pace unknown -- never a dead stock on a late store. The reading rides on the plan (``plan.liquidity``),
leads its checks, makes a setup plan NOT A TRADE when thin, and is the In play group's Liquidity row.
"""
from __future__ import annotations

from typing import Any

from constants_setups import LIQUIDITY_OK, LIQUIDITY_THIN, SETUPS_BAR_SEC, SETUPS_THIN_BARS_STALE_SEC
from setup_scanner import liquidity


def _end(bars: list[dict[str, Any]], now: float) -> tuple[float | None, str | None]:
    """Where the last-five-minutes window ends: the newest stored minute's end, if it is recent enough."""
    starts = [float(b["t"]) for b in bars if isinstance(b, dict) and isinstance(b.get("t"), (int, float))]
    if not starts:
        return None, "the chart has no minutes today"
    end = max(starts) + SETUPS_BAR_SEC
    floor = float(int(now // SETUPS_BAR_SEC) * SETUPS_BAR_SEC)
    if floor - end > SETUPS_THIN_BARS_STALE_SEC:
        return None, f"the chart's minutes stop {int((floor - end) // 60)} minutes ago"
    return min(end, floor), None


def read(ctx: dict[str, Any], now: float, risk: Any = None) -> dict[str, Any]:
    """The stock's liquidity now; the book is walked only for a plan's ``risk``."""
    bars = [b for b in ctx.get("bars") or [] if isinstance(b, dict)]
    unknown: dict[str, str] = {}
    end, why = _end(bars, now)
    pace = None
    if end is None:
        unknown["pace"] = why or "the last 5 minutes are not measured"
    else:
        pace = liquidity.pace_dollars(bars, end)
    day = liquidity.day_dollars(ctx.get("volume"), bars, now, ctx.get("price"))
    walked = None
    qty = liquidity.size_for(ctx.get("risk_usd"), risk)
    asks = ctx.get("asks") or []
    if risk is not None:                     # without a plan there is no fill to size
        if not asks or ctx.get("l1_only"):
            unknown["book"] = "Nova holds no Level 2 book for it"
        elif qty < 1:
            unknown["book"] = "no risk per trade to size the fill by"
        else:
            walked = liquidity.walk(asks, qty)
    return liquidity.judge(day=day, pace=pace, now=now, book=walked, risk=risk, unknown=unknown)


def _numbers(r: dict[str, Any]) -> str:
    minutes = int(round((r.get("pace_sec") or 300) / 60))
    return (f"{liquidity.money(r.get('day_dollars'))} traded today, "
            f"{liquidity.money(r.get('pace_dollars'))} in the last {minutes} minutes")


def check(r: dict[str, Any]) -> dict[str, Any]:
    """The plan's first check: can a trade be filled here at all?"""
    if r.get("state") == LIQUIDITY_THIN:
        return {"id": "liquidity", "state": "bad", "text": liquidity.headline(r)}
    if r.get("state") == LIQUIDITY_OK:
        return {"id": "liquidity", "state": "ok", "text": f"liquid enough: {_numbers(r)}"}
    missing = "; ".join((r.get("unknown") or {}).values()) or "not measured"
    return {"id": "liquidity", "state": "unknown", "text": f"liquidity not known: {missing}"}


def row(r: dict[str, Any]) -> dict[str, Any]:
    """The In play group's Liquidity row."""
    from stock_read.rows import row as make_row

    state = r.get("state")
    limits = r.get("limits") or {}
    rule = (f"Too thin to trade under {liquidity.money(limits.get('day_dollars'))} traded today or "
            f"{liquidity.money(limits.get('pace_dollars'))} in the last 5 minutes, or when buying your size "
            f"walks the asks more than {limits.get('walk_r', 0.25):g}R past the ask.")
    if state == LIQUIDITY_THIN:
        return make_row("liquidity", "Liquidity", "Too thin", "bad", "Nova's volume and Level 2",
                        f"{'; '.join(r.get('reasons') or [])}. {rule}", r.get("as_of"))
    if state == LIQUIDITY_OK:
        return make_row("liquidity", "Liquidity", liquidity.money(r.get("day_dollars")), "ok",
                        "Nova's volume and Level 2", f"{_numbers(r)}. {rule}", r.get("as_of"))
    missing = "; ".join((r.get("unknown") or {}).values()) or "not measured"
    return make_row("liquidity", "Liquidity", "Not known", "unknown", "Nova's volume and Level 2",
                    f"{missing}. {rule}", r.get("as_of"))
