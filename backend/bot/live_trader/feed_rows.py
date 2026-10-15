"""A host's rows as the Live Trader bot reads them: adds, how far behind the read is, a position's id. Pure.

The feed records every change of a host's average as an add (``trade.adds``). An add that fills in pieces moves
the average two or three times in a few seconds, and an entry that fills in pieces does the same right after the
entry: changes ``LT_ADD_MERGE_SEC`` apart are one add, the ones that close to the entry are part of the entry,
and a group whose average ends where it began (a misread that came back) is no add. A group is acted on only
once it has settled: the stream's clock has passed its last change by ``LT_ADD_MERGE_SEC``. Shapes:
architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bot.live_trader.constants_live_trader import LT_ADD_MERGE_SEC, LT_FLICKER_PCT

ET = ZoneInfo("America/New_York")
DAY_SEC = 86_400
# The page's own allowance for a clock read a little ahead of the read's time (frontend FOLLOWED_CLOCK_AHEAD_SEC).
CLOCK_AHEAD_SEC = 300


def position_id(host: str, side: str, symbol: str) -> str:
    """One position per host, side and stock: a row the feed reopens for the same stock is the same position."""
    return f"{host}|{side}|{symbol}"


def add_groups(adds: list[dict[str, Any]], entry_ts: float, feed_now: float | None) -> tuple[list[dict], bool]:
    """``(settled, pending)``: the host's adds folded into groups, oldest first, and whether a group is still
    moving. A group is ``{first_ts, last_ts, from_price, to_price, changes}``; groups that start within
    ``LT_ADD_MERGE_SEC`` of the entry, and groups that end where they began, are left out."""
    groups: list[dict[str, Any]] = []
    for add in sorted(adds, key=lambda a: a["ts"]):
        last = groups[-1] if groups else None
        if last is not None and add["ts"] - last["last_ts"] <= LT_ADD_MERGE_SEC:
            last.update(last_ts=add["ts"], to_price=add["price"], changes=last["changes"] + 1)
            continue
        start = add["prev_price"] if add.get("prev_price") is not None else None
        groups.append({"first_ts": add["ts"], "last_ts": add["ts"], "from_price": start, "to_price": add["price"],
                       "changes": 1})
    settled, pending = [], False
    for g in groups:
        if g["first_ts"] - entry_ts <= LT_ADD_MERGE_SEC:
            continue                                  # the entry still filling in pieces
        if feed_now is None or feed_now - g["last_ts"] < LT_ADD_MERGE_SEC:
            pending = True                            # still moving: acted on once it settles
            continue
        if g["from_price"] and abs(g["to_price"] / g["from_price"] - 1.0) * 100.0 < LT_FLICKER_PCT:
            continue                                  # came back where it began: a misread, not an add
        settled.append(g)
    return settled, pending


def clock_ts(date: str, clock: str | None) -> float | None:
    """The stream's on-screen ``HH:MM:SS`` (ET) that day as epoch seconds; None without a clock."""
    if not clock:
        return None
    try:
        return datetime.fromisoformat(f"{date}T{clock}").replace(tzinfo=ET).timestamp()
    except ValueError:
        return None


def _sec_of_day(ts: float) -> int:
    t = datetime.fromtimestamp(ts, ET)
    return t.hour * 3600 + t.minute * 60 + t.second


def behind_sec(clock: str | None, updated_at: float | None) -> float | None:
    """How far the bar's on-screen clock was behind the moment the feed read it, however far (a frame from before
    midnight read after it counts across it) -- the Following page's ``behindStream``; None when unknown."""
    if updated_at is None or not clock:
        return None
    parts = clock.split(":")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    shown = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    lag = _sec_of_day(updated_at) - shown
    if lag >= 0:
        return float(lag)
    return 0.0 if lag >= -CLOCK_AHEAD_SEC else float(lag + DAY_SEC)


def reference_price(quote: dict[str, Any] | None) -> float | None:
    """The market a host's average is checked against: the mid of a two-sided quote, else the last."""
    if not quote:
        return None
    bid, ask, last = quote.get("bid"), quote.get("ask"), quote.get("last")
    if bid and ask and 0 < bid <= ask:
        return round((bid + ask) / 2.0, 6)
    return float(last) if last and last > 0 else None


def apart_pct(price: float, reference: float) -> float:
    """How far ``price`` is from ``reference``, in percent points."""
    return abs(price / reference - 1.0) * 100.0
