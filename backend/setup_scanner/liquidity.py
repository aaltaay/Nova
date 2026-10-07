"""Too thin to trade (operator decision 2026-10-01). Pure.

LPA, 2026-10-01: Gainers #41, +10%, $1.0M traded all day by its first trigger and $42K in the five
minutes before it; 100 shares at the inside with the next offer 18 cents higher. The scanners armed
five setups on it and drew them like trades. "There's no way I will ever trade something like that."

A stock is **too thin** at a moment when any of these fails:

- **day**: it has traded at least ``SETUPS_THIN_MIN_DAY_DOLLARS`` today (from 04:00 ET) -- its day
  volume times the volume-weighted average price of its minutes (the last price when no minute has
  volume yet);
- **pace**: its last ``SETUPS_THIN_PACE_SEC`` of closed minutes traded at least
  ``SETUPS_THIN_MIN_PACE_DOLLARS``;
- **book**: with a Level 2 book and a size -- the desk's risk per trade over the setup's risk a share
  -- buying that size walks the asks no more than ``SETUPS_THIN_MAX_WALK_R`` of the risk past the best
  ask. A best ask of 100 shares with a hole behind it hides the real price of a fill; the inside
  spread alone never shows it. A short sells into the bids, so its walk is the bids' (``walk_bids``,
  ADR 048): the same limit, under the best bid.

A check Nova cannot make is **unknown** and its reason is kept: never thin on a guess, never a pass.
The reading is ``ok`` only when the day and the pace are both known and pass (and the book, when it
was read). Nothing here places, stages or blocks an order: ``trade_verdict`` makes a thin setup NOT
A TRADE, and the lanes stop proposing it.
"""
from __future__ import annotations

import math
from datetime import datetime, time as dtime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from constants_setups import (
    LIQUIDITY_OK,
    LIQUIDITY_THIN,
    LIQUIDITY_UNKNOWN,
    SETUPS_THIN_MAX_WALK_R,
    SETUPS_THIN_MIN_DAY_DOLLARS,
    SETUPS_THIN_MIN_PACE_DOLLARS,
    SETUPS_THIN_PACE_SEC,
)

ET = ZoneInfo("America/New_York")
SESSION_START = dtime(4, 0)
_EPS = 1e-9


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _tcv(bar: Any) -> tuple[float, float, float] | None:
    """A bar's start, close and volume: a scanner ``Bar`` or a stored ``{t, c, v}`` row."""
    if isinstance(bar, dict):
        t, c, v = _num(bar.get("t")), _num(bar.get("c")), _num(bar.get("v"))
    else:
        t, c, v = _num(getattr(bar, "t", None)), _num(getattr(bar, "c", None)), _num(getattr(bar, "v", None))
    if t is None or c is None or c <= 0:
        return None
    return t, c, max(v or 0.0, 0.0)


def session_start(now: float) -> float:
    """04:00 ET of ``now``'s Eastern date, epoch seconds."""
    day = datetime.fromtimestamp(now, ET).date()
    return datetime.combine(day, SESSION_START, ET).timestamp()


def money(x: float | None) -> str:
    """"$1.25M", "$42K", "$800"; "?" when unknown."""
    if x is None:
        return "?"
    if x >= 1e6:
        return f"${x / 1e6:,.2f}M"
    if x >= 1e3:
        return f"${x / 1e3:,.0f}K"
    return f"${x:,.0f}"


def day_dollars(volume: Any, bars: Iterable[Any], now: float, price: Any = None) -> float | None:
    """Dollars traded today: the day volume times the volume-weighted average price of today's minutes,
    else the last price; None when the day volume is unknown."""
    vol = _num(volume)
    if vol is None or vol < 0:
        return None
    start = session_start(now)
    px_vol = vols = 0.0
    for bar in bars:
        got = _tcv(bar)
        if got is None or got[0] < start or got[0] >= now:
            continue
        px_vol += got[1] * got[2]
        vols += got[2]
    avg = px_vol / vols if vols > 0 else _num(price)
    return None if avg is None else vol * avg


def pace_dollars(bars: Iterable[Any], end: float, window_sec: float = SETUPS_THIN_PACE_SEC) -> float:
    """Dollars traded in the closed minutes that start in ``[end - window_sec, end)`` (a minute with no
    bar traded nothing)."""
    total = 0.0
    for bar in bars:
        got = _tcv(bar)
        if got is not None and end - window_sec <= got[0] < end:
            total += got[1] * got[2]
    return total


def walk(asks: Iterable[Any], qty: int) -> dict[str, Any] | None:
    """Buying ``qty`` shares through the displayed asks, cheapest first (venue rows at one price summed):
    ``{qty, best_ask, last, avg, over_ask, shown, short}`` -- ``short`` when the book shows fewer shares
    than ``qty`` (``avg`` / ``last`` are then over the shares shown). None without an ask or a size."""
    if qty < 1:
        return None
    levels: dict[float, float] = {}
    for lvl in asks or []:
        if not isinstance(lvl, dict):
            continue
        px, sz = _num(lvl.get("price")), _num(lvl.get("size"))
        if px is None or px <= 0 or sz is None or sz <= 0:
            continue
        key = round(px, 4)
        levels[key] = levels.get(key, 0.0) + sz
    if not levels:
        return None
    left, cost, last = float(qty), 0.0, None
    for px in sorted(levels):
        take = min(left, levels[px])
        cost += take * px
        left -= take
        last = px
        if left <= _EPS:
            break
    filled = qty - max(left, 0.0)
    best = min(levels)
    avg = cost / filled if filled > 0 else best
    return {"qty": int(qty), "best_ask": best, "last": last, "avg": round(avg, 4),
            "over_ask": round(avg - best, 4), "shown": round(sum(levels.values())), "short": left > _EPS}


def walk_bids(bids: Iterable[Any], qty: int) -> dict[str, Any] | None:
    """Selling ``qty`` shares (a short) through the displayed bids, highest first (venue rows at one price
    summed): ``{qty, best_bid, last, avg, under_bid, shown, short}`` -- ``walk``'s mirror (ADR 048: "Too thin
    to trade" walks the bids for a short). None without a bid or a size."""
    if qty < 1:
        return None
    levels: dict[float, float] = {}
    for lvl in bids or []:
        if not isinstance(lvl, dict):
            continue
        px, sz = _num(lvl.get("price")), _num(lvl.get("size"))
        if px is None or px <= 0 or sz is None or sz <= 0:
            continue
        key = round(px, 4)
        levels[key] = levels.get(key, 0.0) + sz
    if not levels:
        return None
    left, proceeds, last = float(qty), 0.0, None
    for px in sorted(levels, reverse=True):
        take = min(left, levels[px])
        proceeds += take * px
        left -= take
        last = px
        if left <= _EPS:
            break
    filled = qty - max(left, 0.0)
    best = max(levels)
    avg = proceeds / filled if filled > 0 else best
    return {"qty": int(qty), "best_bid": best, "last": last, "avg": round(avg, 4),
            "under_bid": round(best - avg, 4), "shown": round(sum(levels.values())), "short": left > _EPS}


def slippage(book: dict[str, Any]) -> float:
    """How far a walk's average fill lands past the inside: over the ask for a buy, under the bid for a short."""
    return float(book["under_bid"] if "under_bid" in book else book["over_ask"])


def size_for(risk_usd: Any, risk: Any) -> int:
    """Whole shares of the desk's risk per trade over the risk a share; 0 when either is unknown."""
    usd, per = _num(risk_usd), _num(risk)
    if usd is None or per is None or usd <= 0 or per <= _EPS:
        return 0
    return int(math.floor(usd / per + _EPS))


def _walk_words(w: dict[str, Any], risk: float) -> str:
    slip = slippage(w)
    if "under_bid" in w:
        return (f"shorting {w['qty']:,} shares walks the bids to {w['last']:.2f}: {slip * 100:.0f}c under the "
                f"{w['best_bid']:.2f} bid on average, {slip / risk:.1f}R of the {risk * 100:.0f}c risk")
    return (f"buying {w['qty']:,} shares walks the asks to {w['last']:.2f}: {slip * 100:.0f}c over the "
            f"{w['best_ask']:.2f} ask on average, {slip / risk:.1f}R of the {risk * 100:.0f}c risk")


def judge(*, day: float | None, pace: float | None, pace_sec: float = SETUPS_THIN_PACE_SEC, now: float,
          book: dict[str, Any] | None = None, risk: Any = None,
          unknown: dict[str, str] | None = None) -> dict[str, Any]:
    """The reading: ``{state: "ok" | "thin" | "unknown", reasons, failed: ("day" | "pace" | "book")[],
    unknown, day_dollars, pace_dollars, pace_sec, walk, as_of, limits}``. ``book`` is a ``walk`` (or, for a
    short, ``walk_bids``) answer;
    ``unknown`` names why a check could not be made (``{"day" | "pace" | "book": words}``)."""
    unknown = dict(unknown or {})
    reasons: list[str] = []
    failed: list[str] = []
    if day is None:
        unknown.setdefault("day", "Nova does not know today's volume")
    elif day < SETUPS_THIN_MIN_DAY_DOLLARS:
        reasons.append(f"traded {money(day)} today, under {money(SETUPS_THIN_MIN_DAY_DOLLARS)}")
        failed.append("day")
    minutes = int(round(pace_sec / 60))
    if pace is None:
        unknown.setdefault("pace", f"the last {minutes} minutes are not measured")
    elif pace < SETUPS_THIN_MIN_PACE_DOLLARS:
        reasons.append(f"{money(pace)} in the last {minutes} minutes, under {money(SETUPS_THIN_MIN_PACE_DOLLARS)}")
        failed.append("pace")
    per = _num(risk)
    walked = None
    if book is not None and per is not None and per > _EPS:
        walked = {**book, "r": round(slippage(book) / per, 2)}
        if walked["r"] > SETUPS_THIN_MAX_WALK_R + _EPS:
            words = _walk_words(walked, per)
            if walked["short"]:
                words += f" -- and the book shows only {walked['shown']:,} shares"
            reasons.append(words)
            failed.append("book")
        elif walked["short"]:
            unknown.setdefault("book", f"the book shows only {walked['shown']:,} of the {walked['qty']:,} shares")
    if reasons:
        state = LIQUIDITY_THIN
    elif day is None or pace is None:
        state = LIQUIDITY_UNKNOWN
    else:
        state = LIQUIDITY_OK
    return {"state": state, "reasons": reasons, "failed": failed, "unknown": unknown,
            "day_dollars": None if day is None else round(day), "pace_dollars": None if pace is None else round(pace),
            "pace_sec": int(pace_sec), "walk": walked, "as_of": now,
            "limits": {"day_dollars": SETUPS_THIN_MIN_DAY_DOLLARS, "pace_dollars": SETUPS_THIN_MIN_PACE_DOLLARS,
                       "walk_r": SETUPS_THIN_MAX_WALK_R}}


def is_thin(reading: Any) -> bool:
    return isinstance(reading, dict) and reading.get("state") == LIQUIDITY_THIN


def headline(reading: Any) -> str | None:
    """"too thin to trade: traded $0.90M today, under $2.00M; ..." for a thin reading, else None."""
    if not is_thin(reading):
        return None
    return "too thin to trade: " + "; ".join(reading.get("reasons") or ["too little trading"])


def same(a: Any, b: Any) -> bool:
    """Whether two readings say the same thing (state and which checks failed): a lane journals a change only."""
    def key(r: Any) -> tuple:
        if not isinstance(r, dict):
            return (None,)
        return (r.get("state"), tuple(r.get("failed") or ()), tuple(sorted((r.get("unknown") or {}).keys())))
    return key(a) == key(b)
