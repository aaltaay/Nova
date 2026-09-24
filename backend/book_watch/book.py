"""Pure Level 2 arithmetic for the book watcher: size per price, what is wholly in view, ticks."""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable

from book_watch.constants_book_watch import BOOK_WATCH_OFF_BOOK_EXCHANGES


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


def same_price(a: float, b: float) -> bool:
    return abs(a - b) < tick_for(min(a, b)) / 2


def lit_print(row: Any) -> bool:
    """A print that traded on an exchange's lit book; off-exchange prints never fill a level."""
    return str(row.get("exchange") or "").upper() not in BOOK_WATCH_OFF_BOOK_EXCHANGES
