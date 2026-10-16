"""A host's rows as the Live Trader bot reads them: adds, how far behind the read is, a position's id. Pure.

The feed records every change of a host's average as an add (``trade.adds``). An add that fills in pieces moves
the average two or three times in a few seconds, and an entry that fills in pieces does the same right after the
entry: changes ``LT_ADD_MERGE_SEC`` apart are one add, the ones that close to the entry are part of the entry,
and a group whose average ends where it began (a misread that came back) is no add. A group is acted on only
once it has settled: the stream's clock has passed its last change by ``LT_ADD_MERGE_SEC``. Shapes:
architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bot.live_trader.constants_live_trader import (
    LT_ADD_MERGE_SEC,
    LT_OTHER_HOST_SEC,
    LT_SWITCH_SEC,
    LT_UNREAD_SEC,
)

ET = ZoneInfo("America/New_York")
DAY_SEC = 86_400
# The page's own allowance for a clock read a little ahead of the read's time (frontend FOLLOWED_CLOCK_AHEAD_SEC).
CLOCK_AHEAD_SEC = 300
SIDES = ("long", "short")
# A price in text the reader could not parse: a row it did not read whole (a scroll, a cut or glued pair). Text
# without one -- "no positions", a name tag -- is a side read empty, not a side read wrong.
PRICE_IN_TEXT = re.compile(r"\d+\.\d+")


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
        if g["from_price"] and cent(g["to_price"]) == cent(g["from_price"]):
            continue                                  # came back where it began, as the bar shows it: no add
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
    hms = time_of_day(clock)
    if hms is None:
        return None
    shown = hms[0] * 3600 + hms[1] * 60 + hms[2]
    lag = _sec_of_day(updated_at) - shown
    if lag >= 0:
        return float(lag)
    return 0.0 if lag >= -CLOCK_AHEAD_SEC else float(lag + DAY_SEC)


def time_of_day(clock: str) -> tuple[int, int, int] | None:
    """``(h, m, s)`` of an ``HH:MM:SS`` clock, or None when it is no time of day (a misread screen: ``09:34:97``)."""
    parts = clock.split(":")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    h, m, s = (int(p) for p in parts)
    return (h, m, s) if h < 24 and m < 60 and s < 60 else None


def cent(price: float) -> float:
    """A price to the cent (a hundredth of a cent under $1): how a bar shows an average."""
    return round(price, 2) if price >= 1 else round(price, 4)


def averages(trade: dict[str, Any]) -> set[float]:
    """Every average a trade or a row showed, to the cent: its entry's, its latest and each add's."""
    prices = [trade.get("entry_price"), trade.get("price"), *(a.get("price") for a in trade.get("adds") or ())]
    return {cent(float(p)) for p in prices if isinstance(p, (int, float)) and not isinstance(p, bool) and p > 0}


def other_host(name: str, row: dict[str, Any], hosts: dict[str, dict[str, Any]],
               previous: set[tuple[str, str, float]]) -> tuple[str | None, float] | None:
    """Whose ``row`` is when it is not ``name``'s: ``(host, average)`` for another host's row of the same side and
    stock that showed an average to the cent in common and was on the bar within ``LT_OTHER_HOST_SEC`` of it, or
    ``(None, average)`` for a trade of the feed's previous day (``previous``: ``(side, symbol, average)``); None
    when nothing else ever showed it. At a hand-over the bar can show one host's rows under the next host's name
    tag for minutes, and two hosts never share an average to the cent."""
    mine = averages(row)
    if not mine:
        return None
    start = float(row["entry_ts"])
    for other, host in hosts.items():
        if other == name:
            continue
        for r in host.get("rows") or ():
            if r["side"] != row["side"] or r["symbol"] != row["symbol"]:
                continue
            end = r.get("exit_ts") if r["status"] != "open" else None
            if r["entry_ts"] > start + LT_OTHER_HOST_SEC or (end is not None and end < start - LT_OTHER_HOST_SEC):
                continue
            shared = mine & averages(r)
            if shared:
                return other, min(shared)
    for price in sorted(mine):
        if (row["side"], row["symbol"], price) in previous:
            return None, price
    return None


def filled_together(row: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    """True when ``row`` is one of two or more slots that changed within ``LT_SWITCH_SEC`` onto an empty bar: rows
    opening together while every older row had closed by then (a bar back after a blank, or the slots switching at
    a hand-over). Such rows were already open: the screen changed, not the host's trades."""
    on_bar = [r for r in rows if not r.get("left_bar")]
    peers = [r for r in on_bar if abs(r["entry_ts"] - row["entry_ts"]) <= LT_SWITCH_SEC]
    start, end = min(r["entry_ts"] for r in peers), max(r["entry_ts"] for r in peers)
    ids = {r["id"] for r in peers}
    closing = 0
    for r in on_bar:
        if r["id"] in ids or r["entry_ts"] > start:
            continue
        if r["status"] == "open" or r.get("exit_ts") is None or r["exit_ts"] > end + LT_SWITCH_SEC:
            return False                              # the bar was not empty: a row stayed open beside them
        closing += r["exit_ts"] >= start - LT_SWITCH_SEC
    return len(peers) + closing >= 2


def unread_sides(log: list[dict[str, Any]] | None, date: str, at_ts: float | None) -> dict[str, set[str]]:
    """Each host whose reads in force over the ``LT_UNREAD_SEC`` before ``at_ts`` (the stream's time; the log's
    newest when None) carried a price the reader could not parse: the sides that text names (``long:`` /
    ``short:``), both when it names none. ``log`` is the feed's read log, oldest first (``feed.parse_reads``)."""
    out: dict[str, set[str]] = {}
    for line in reversed(log or ()):
        ts = clock_ts(date, line["clock"])
        if ts is None:
            continue
        if at_ts is None:
            at_ts = ts
        if ts > at_ts:
            continue                                  # a read after the moment asked about
        for name, read in (line.get("traders") or {}).items():
            for text in read.get("unparsed") or ():
                if PRICE_IN_TEXT.search(text):
                    out.setdefault(name, set()).update(_sides_named(text))
        if ts <= at_ts - LT_UNREAD_SEC:
            break                                     # the read in force when the window began: nothing older
    return out


def _sides_named(text: str) -> set[str]:
    head = text.strip().lower()
    named = {s for s in SIDES if head.startswith(s)}
    return named or set(SIDES)


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
