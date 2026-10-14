"""The pure core of a rebuilt day's Gappers by the second: who can be on the list inside a minute, and the list at a
second. No I/O and no clock.

A minute ``m`` is a whole-minute epoch second; the seconds ``[m, m + 60)`` read minute ``m``'s stocks, each priced
as of ``m`` and then by its trades printed in ``[m, s)``. A bar is ``(start, high, close, volume)``: it closes at
``start + 60`` and counts at every minute from then on, never earlier -- the rebuild's own rule
(``research/leaderboard/lb_core.py``), so the list at second ``m`` is the stored minute board.
"""
from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from constants_leaderboard import LEADERBOARD_ROWS_PER_BOARD_MAX, LEADERBOARD_SECONDS_MAX_DISAGREEMENTS
from leaderboard.ranking import GAPPERS_RULES, rank_rows, refusal
from leaderboard.rows import change_fraction

Bar = tuple[int, float, float, float]             # (start, high, close, volume)
Second = tuple[int, float | None, float]          # (second, last price-setting price or None, the second's volume)
Print = tuple[int, int, float, float, bool]       # (SIP ns, sequence, price, size, sets a price)


@dataclass(frozen=True)
class Candidate:
    """A stock that can be on the list inside ``minute``, priced as of the minute.

    ``price`` is None when no bar of the stock had closed by then (its first trade is inside the minute);
    ``rank`` is its frozen 09:30 rank from 09:30, else None.
    """

    minute: int
    symbol: str
    price: float | None
    volume: float
    prev_close: float
    rank: int | None = None


def qualifies(price: float | None, prev_close: float | None) -> bool:
    """``GAPPERS_RULES`` on one price against the prior close, with the ranking's own arithmetic."""
    if price is None or prev_close is None or prev_close <= 0:
        return False
    return refusal({"price": price, "change_pct": change_fraction(price, prev_close)}, GAPPERS_RULES) is None


def as_of(bars: Sequence[Bar], minutes: Iterable[int]) -> Iterator[tuple[int, float | None, float, Bar | None]]:
    """For each minute, ascending: the close of the stock's last bar closed by it, its running volume, and its bar
    starting at that minute (None when it did not trade then). ``bars`` sorted by start."""
    i, close, volume = 0, None, 0.0
    for minute in minutes:
        while i < len(bars) and bars[i][0] + 60 <= minute:
            close, volume = bars[i][2], volume + bars[i][3]
            i += 1
        starting = bars[i] if i < len(bars) and bars[i][0] == minute else None
        yield minute, close, volume, starting


def premarket_candidates(symbol: str, bars: Sequence[Bar], prev_close: float | None,
                         minutes: Sequence[int]) -> list[Candidate]:
    """The premarket minutes in which ``symbol`` can be a gapper: its price as of the minute, or the high of its bar
    starting at the minute, clears the rule. A price printed inside a minute is at most that bar's high."""
    if not bars or prev_close is None or prev_close <= 0 or not qualifies(max(b[1] for b in bars), prev_close):
        return []
    out: list[Candidate] = []
    for minute, close, volume, starting in as_of(bars, minutes):
        high = starting[1] if starting is not None else None
        if qualifies(close, prev_close) or qualifies(high, prev_close):
            out.append(Candidate(minute, symbol, close, volume, prev_close))
    return out


def frozen_candidates(members: Sequence[tuple[str, int]], bars: Mapping[str, Sequence[Bar]],
                      prev_close: Mapping[str, float], minutes: Sequence[int]) -> list[Candidate]:
    """From 09:30: the frozen members at their 09:30 rank, each priced as of every later minute."""
    out: list[Candidate] = []
    for symbol, rank in members:
        pc = prev_close.get(symbol)
        if pc is None or pc <= 0:
            continue
        for minute, close, volume, _starting in as_of(bars.get(symbol, ()), minutes):
            out.append(Candidate(minute, symbol, close, volume, pc, rank))
    return out


def tally_seconds(prints: Iterable[Print], minutes: Iterable[int]) -> list[Second]:
    """One row per second inside ``minutes`` in which the stock traded: the second's last price-setting print (SIP
    time, then sequence number; None when no print in it set a price) and the second's volume. Cancels and
    errors are no trade and must already be out."""
    wanted = set(minutes)
    tally: dict[int, list] = {}
    for ns, sequence, price, size, sets_price in prints:
        second = ns // 1_000_000_000
        if second - second % 60 not in wanted:
            continue
        held = tally.get(second)
        if held is None:
            held = tally[second] = [None, None, 0.0]
        held[2] += size
        if sets_price and (held[0] is None or (ns, sequence) >= held[0]):
            held[0], held[1] = (ns, sequence), price
    return [(second, held[1], held[2]) for second, held in sorted(tally.items())]


def priced_at(candidate: Candidate, seconds: Sequence[Second], at: int) -> tuple[float | None, float]:
    """The candidate's price and volume at second ``at``: as of its minute, then its seconds in ``[minute, at)``."""
    price, volume = candidate.price, candidate.volume
    start = bisect_left(seconds, (candidate.minute,))
    for second, last, size in seconds[start:]:
        if second >= at:
            break
        volume += size
        if last is not None:
            price = last
    return price, volume


def list_at(at: int, candidates: Sequence[Candidate], seconds: Mapping[str, Sequence[Second]]) -> list[dict[str, Any]]:
    """The Gappers list at second ``at`` from the candidates of its minute.

    Before 09:30 ``GAPPERS_RULES`` ranks them (the top ``LEADERBOARD_ROWS_PER_BOARD_MAX``); from 09:30 the frozen
    members keep their 09:30 order. Rows carry ``symbol, rank, price, prev_close, change_pct, gap_pct, volume``;
    ``gap_pct`` is the move, as on the live list before there is an open.
    """
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        price, volume = priced_at(candidate, seconds.get(candidate.symbol, ()), at)
        change = change_fraction(price, candidate.prev_close) if price is not None else None
        rows.append({"symbol": candidate.symbol, "rank": candidate.rank, "price": price,
                     "prev_close": candidate.prev_close, "change_pct": change, "gap_pct": change, "volume": volume})
    if any(row["rank"] is not None for row in rows):
        return sorted(rows, key=lambda row: row["rank"] if row["rank"] is not None else float("inf"))
    return rank_rows(rows, GAPPERS_RULES)[:LEADERBOARD_ROWS_PER_BOARD_MAX]


def check_minutes(stored: Mapping[int, Sequence[str]], by_minute: Mapping[int, Sequence[Candidate]],
                  minutes: Iterable[int]) -> dict[str, Any]:
    """Each minute's list at its first second against the stored board (symbols in rank order)."""
    checked = agreed = 0
    disagreements: list[dict[str, Any]] = []
    for minute in minutes:
        if minute not in stored:
            continue
        checked += 1
        ours = [row["symbol"] for row in list_at(minute, by_minute.get(minute, ()), {})]
        theirs = list(stored[minute])
        if ours == theirs:
            agreed += 1
        elif len(disagreements) < LEADERBOARD_SECONDS_MAX_DISAGREEMENTS:
            disagreements.append({"minute_ts": minute, "stored": theirs, "by_second": ours})
    return {"checked_minutes": checked, "agreed_minutes": agreed, "disagreements": disagreements}
