"""Pure Level 2 arithmetic for the book watcher: size per price, what is wholly in view, ticks, and the
copies of rows IBKR was moving in recorded books (#1133)."""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable

from book_watch.constants_book_watch import (
    BOOK_WATCH_COLLAPSE_FROM,
    BOOK_WATCH_COLLAPSE_TO,
    BOOK_WATCH_OFF_BOOK_EXCHANGES,
    BOOK_WATCH_ROUND_LOT,
)


def price_key(raw: Any) -> float | None:
    """A price as a dict key: rounded so 4.27 from two venues is one level."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return round(value, 6)


def aggregate(rows: Iterable[Any]) -> dict[float, float]:
    """Size per price, summed across the venues quoting it."""
    levels: dict[float, float] = {}
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        price = price_key(row.get("price"))
        try:
            size = float(row.get("size") or 0)
        except (TypeError, ValueError):
            continue
        if price is None or not math.isfinite(size) or size <= 0:
            continue
        levels[price] = levels.get(price, 0.0) + size
    return levels


def _row_key(row: Any) -> tuple[float, float] | None:
    if not isinstance(row, dict):
        return None
    price = price_key(row.get("price"))
    try:
        size = float(row.get("size") or 0)
    except (TypeError, ValueError):
        return None
    return None if price is None or not math.isfinite(size) else (price, size)


def drop_moving_copies(rows: list[Any], before: list[Any] | None) -> list[Any]:
    """A recorded side's rows less the copy of a row IBKR was moving when the book was taken (#1133).

    Live books show each venue once at a price (``ibkr/depth/book.py``); a book recorded before that can
    hold one venue's order on two rows. Rows that name their venue (``mm``) keep each venue's first row at
    a price. Session Records keep no venue, so there a copy is told by its size and its life: a row with
    the price and the odd size (not a round lot) of a row above it, when the book ``before`` held fewer
    rows of that price and size. Two venues often show the same round lot at a price, so a round-lot copy
    cannot be told from them and stays; with no book before, nothing goes.
    """
    rows = list(rows or ())
    if any(isinstance(row, dict) and row.get("mm") for row in rows):
        return _venue_once(rows)
    if before is None:
        return rows
    had = Counter(_row_key(row) for row in before)
    have: Counter[tuple[float, float] | None] = Counter()
    out: list[Any] = []
    for row in rows:
        key = _row_key(row)
        if key is not None and have[key] and key[1] % BOOK_WATCH_ROUND_LOT and have[key] >= had[key]:
            continue
        have[key] += 1
        out.append(row)
    return out


def _venue_once(rows: list[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[tuple[float | None, str]] = set()
    for row in rows:
        venue = row.get("mm") if isinstance(row, dict) else None
        if venue:
            key = (price_key(row.get("price")), str(venue))
            if key in seen:
                continue
            seen.add(key)
        out.append(row)
    return out


class RecordedCopies:
    """Recorded books read in order, each side through ``drop_moving_copies`` against the book before.

    A side recorded unchanged keeps the rows kept from it last time: IBKR sent nothing for that side, so a
    move it had not finished is still unfinished. Deterministic, no I/O; the books passed in are never
    changed.
    """

    def __init__(self) -> None:
        self._last: dict[str, tuple[list[Any], list[Any]]] = {}  # side -> (rows as recorded, rows kept)

    def read(self, book: Any) -> Any:
        if not isinstance(book, dict):
            return book
        out = book
        for side in ("bids", "asks"):
            rows = list(book.get(side) or ())
            last = self._last.get(side)
            if last is not None and rows == last[0]:
                kept = last[1]
            else:
                kept = drop_moving_copies(rows, None if last is None else last[0])
            self._last[side] = (rows, kept)
            if len(kept) != len(rows):
                out = dict(book) if out is book else out
                out[side] = list(kept)
        return out


@dataclass(frozen=True)
class SideView:
    """One side of one book: size per price, the cut-off price, the best price."""

    levels: dict[float, float]
    cutoff: float | None
    best: float | None
    rows: int


def side_view(rows: list[Any], side: str, num_rows: int) -> SideView:
    """Build a side. With every row in use, the worst visible price may be cut off
    (more venues can sit at it below the last row), so it is the cut-off and only
    prices strictly better are wholly in view. With rows to spare the whole side is."""
    rows = list(rows or ())
    levels = aggregate(rows)
    if not levels:
        return SideView({}, None, None, len(rows))
    best = max(levels) if side == "bid" else min(levels)
    cutoff = None
    if len(rows) >= num_rows:
        cutoff = min(levels) if side == "bid" else max(levels)
    return SideView(levels, cutoff, best, len(rows))


def collapsed(prev: SideView, cur: SideView) -> bool:
    """A side that shrank to a level or so at once: a reset or a glitch, not trading -- unknown."""
    return len(cur.levels) <= BOOK_WATCH_COLLAPSE_TO and len(prev.levels) >= BOOK_WATCH_COLLAPSE_FROM


def in_view(price: float, side: str, cutoff: float | None) -> bool:
    """Is ``price`` wholly in view on a side with this cut-off?"""
    if cutoff is None:
        return True
    return price > cutoff if side == "bid" else price < cutoff


def tick_for(price: float) -> float:
    """The listed tick: a cent at $1 and over, a hundredth of a cent under."""
    return 0.01 if price >= 1 else 0.0001


def distance_ticks(side: str, price: float, best: float | None) -> int | None:
    """Ticks between a level and its side's best price (0 = at the inside)."""
    if best is None:
        return None
    gap = (best - price) if side == "bid" else (price - best)
    return max(0, int(round(gap / tick_for(price))))


def median_level(levels: dict[float, float], *, exclude: float | None = None) -> float | None:
    """Median visible level size on a side, leaving out the level being judged."""
    sizes = [size for price, size in levels.items() if price != exclude]
    return float(median(sizes)) if sizes else None


def lit_print(row: Any) -> bool:
    """A print that traded on an exchange's lit book; off-exchange prints never fill a level."""
    return str(row.get("exchange") or "").upper() not in BOOK_WATCH_OFF_BOOK_EXCHANGES
