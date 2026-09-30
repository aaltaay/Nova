"""The book watcher's matching window (ADR 033): which lit prints fill a drop in resting size.

A drop in the size at one price between two books -- the earlier at ``t0``, the later at ``t1`` -- is
**filled** by the lit prints at exactly that price that arrived after ``t0 - before_sec`` and no later
than ``t1 + after_sec``, each print claimed once and oldest first; the rest of the drop was **pulled**.
The drop is judged ``settle_sec`` after ``t1``, later than ``after_sec``, so every print the window
can hold has arrived.

A price is a key rounded to six places (``book.price_key``), so one price is exactly one key: a
midpoint print (3.655) sits between two levels and fills neither.

**A level a print traded through** (#636). IBKR's book can trail its tape by seconds, so the prints
that took a level may land before the earlier of the two books that show it gone -- outside the
window. A lit, price-setting print above the latest book's best ask (below its best bid) proves the
size the book showed at the round-lot levels from the best to its own price was taken (``Sweeps``).
Until the book shows that size leave a level, a drop there within ``sweep_hold_sec`` of the sweep
first claims the prints at its price around the sweep itself (``before_sec`` before to ``after_sec``
after each such print), at most the size still owed, then its own window. It claims only real prints
at the level's exact price, so a level pulled before the sweep reached it still reads pulled. New size
posted at the level ends the sweep: a later drop there may be the new order, pulled, and the sweep's
leftover prints -- a hidden order, a refill that traded -- are not its own.

Why the window is 0.5 s either side, and what the sweep rule adds, measured on the Session Records:
``window_study.py`` (``tools/book_watch_window_study.py``). Pure.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from book_watch.book import SideView
from book_watch.constants_book_watch import (
    BOOK_WATCH_IDLE_SEC,
    BOOK_WATCH_MATCH_SLACK_SEC,
    BOOK_WATCH_PRINT_KEEP_SEC,
    BOOK_WATCH_SETTLE_SEC,
    BOOK_WATCH_SWEEP_HOLD_SEC,
    BOOK_WATCH_SWEEP_MIN_LEVEL,
    BOOK_WATCH_SWEEP_SKIP_CONDITIONS,
)

# Two price keys closer than this are one price (keys are rounded to six places).
PRICE_EPS = 1e-7


@dataclass(frozen=True)
class MatchParams:
    """How far either side of a drop's two books a print may arrive and still fill it, and how long a
    level a print traded through takes the prints around that print first (0: never)."""

    before_sec: float = BOOK_WATCH_MATCH_SLACK_SEC
    after_sec: float = BOOK_WATCH_MATCH_SLACK_SEC
    settle_sec: float = BOOK_WATCH_SETTLE_SEC
    sweep_hold_sec: float = BOOK_WATCH_SWEEP_HOLD_SEC

    def __post_init__(self) -> None:
        if self.before_sec < 0 or self.after_sec < 0 or self.sweep_hold_sec < 0:
            raise ValueError("the matching window cannot be negative")
        if not self.settle_sec > self.after_sec:
            raise ValueError("settle_sec must exceed after_sec, or a print inside the window may not have arrived")
        if self.sweep_hold_sec + self.settle_sec + self.before_sec >= BOOK_WATCH_PRINT_KEEP_SEC:
            raise ValueError("a swept level's prints must still be kept when its drop is judged")


DEFAULT_MATCH = MatchParams()


def swept_levels(key: float, views: dict[str, SideView] | None) -> tuple[str, list[float]] | None:
    """The side and the displayed prices a print at ``key`` traded through, or None.

    Through means above the best ask (below the best bid) of an uncrossed book whose best level shows
    at least ``BOOK_WATCH_SWEEP_MIN_LEVEL``; the levels are that side's from the best to ``key``.
    """
    if views is None:
        return None
    ask, bid = views["ask"], views["bid"]
    if ask.best is None or bid.best is None or ask.best <= bid.best:
        return None
    if key > ask.best + PRICE_EPS:
        side, view = "ask", ask
        prices = [p for p in view.levels if p <= key + PRICE_EPS]
    elif key < bid.best - PRICE_EPS:
        side, view = "bid", bid
        prices = [p for p in view.levels if p >= key - PRICE_EPS]
    else:
        return None
    if view.levels.get(view.best, 0.0) < BOOK_WATCH_SWEEP_MIN_LEVEL:
        return None  # an odd-lot best is not a protected quote: a print through it proves nothing
    return side, sorted(prices)


@dataclass
class Owed:
    """At one level: the size a sweep proved taken that the book still shows, and the sweeps' times."""

    shares: float
    times: deque[float]


class Sweeps:
    """What sweeps proved traded that the book still shows, per level, until the book shows it gone.

    ``auto`` False: only ``mark`` adds a sweep (the study places its own, to measure against chance)."""

    def __init__(self, hold_sec: float, *, auto: bool = True) -> None:
        self.hold_sec = hold_sec
        self.auto = auto
        self.levels: dict[tuple[str, float], Owed] = {}
        self.events = 0

    def note(self, ts: float, key: float, conditions: object, views: dict[str, SideView] | None,
             book_ts: float | None) -> None:
        """A lit print arrived: mark the levels it traded through, if it proves any."""
        if not self.auto or self.hold_sec <= 0 or book_ts is None or ts - book_ts > BOOK_WATCH_IDLE_SEC:
            return
        if set(str(conditions or "")) & BOOK_WATCH_SWEEP_SKIP_CONDITIONS:
            return
        swept = swept_levels(key, views)
        if swept is not None:
            self.mark(ts, swept[0], swept[1], views)

    def mark(self, ts: float, side: str, prices: Iterable[float], views: dict[str, SideView] | None) -> None:
        """A sweep at ``ts`` took ``prices`` on ``side``: everything the book shows there is owed."""
        if self.hold_sec <= 0 or views is None:
            return
        shown = views[side].levels
        for price in prices:
            size = shown.get(price, 0.0)
            if size <= 0:
                continue
            owed = self.levels.get((side, price))
            if owed is None:
                owed = self.levels[(side, price)] = Owed(size, deque())
            owed.shares = size  # a stale level still shows what the last sweep left owed
            owed.times.append(ts)
            while owed.times and owed.times[0] < ts - BOOK_WATCH_PRINT_KEEP_SEC:
                owed.times.popleft()
        self.events += 1
        if self.events % 256 == 0:  # forget the levels no sweep has touched for a while
            keep = ts - BOOK_WATCH_PRINT_KEEP_SEC
            self.levels = {k: v for k, v in self.levels.items() if v.times and v.times[-1] >= keep}

    def on_drop(self, side: str, price: float, dropped: float, t1: float) -> tuple[float, list[float]]:
        """The book shows ``dropped`` shares leave a level at ``t1``: how many of them the sweeps within the
        hold explain, at most what is still owed, and those sweeps' times, oldest first."""
        owed = self.levels.get((side, price))
        if owed is None:
            return 0.0, []
        within = [ts for ts in owed.times if t1 - self.hold_sec <= ts <= t1]
        paid = min(dropped, owed.shares)
        owed.shares -= paid
        if owed.shares <= 0:
            del self.levels[(side, price)]
        return (paid, within) if within else (0.0, [])

    def forget(self, side: str, price: float) -> None:
        """New size posted at the level, or the level left the view: what the sweep proved can no longer
        be told from what came after it."""
        self.levels.pop((side, price), None)

    def forget_side(self, side: str) -> None:
        for key in [k for k in self.levels if k[0] == side]:
            del self.levels[key]

    def clear(self) -> None:
        self.levels.clear()


def claim(rows: Iterable[list[float]], start: float, end: float, price: float, need: float,
          taken: list[tuple[float, float, float]] | None = None) -> float:
    """Claim up to ``need`` shares from the lit prints at ``price`` that arrived in (``start``, ``end``].

    ``rows`` are ``[ts, price, shares left to claim]`` in arrival order; a claim lowers what is left, so
    a print fills one drop at most. ``taken`` (a list) records each claim as ``(ts, price, shares)``.
    """
    filled = 0.0
    for row in rows:
        if filled >= need:
            break
        ts, key, left = row[0], row[1], row[2]
        if ts <= start or ts > end or left <= 0 or abs(key - price) > PRICE_EPS:
            continue
        take = min(left, need - filled)
        row[2] = left - take
        filled += take
        if taken is not None:
            taken.append((ts, key, take))
    return filled
