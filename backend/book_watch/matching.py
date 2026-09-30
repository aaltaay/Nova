"""The book watcher's matching window (ADR 033): which lit prints fill a drop in resting size.

A drop in the size at one price between two books -- the earlier at ``t0``, the later at ``t1`` -- is
**filled** by the lit prints at exactly that price that arrived after ``t0 - before_sec`` and no later
than ``t1 + after_sec``, each print claimed once and oldest first; the rest of the drop was **pulled**.
The drop is judged ``settle_sec`` after ``t1``, later than ``after_sec``, so every print the window
can hold has arrived.

A price is a key rounded to six places (``book.price_key``), so one price is exactly one key: a
midpoint print (3.655) sits between two levels and fills neither.

Why the window is 0.5 s either side, measured on the Session Records: ``window_study.py``
(``tools/book_watch_window_study.py``). Pure.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from book_watch.constants_book_watch import BOOK_WATCH_MATCH_SLACK_SEC, BOOK_WATCH_SETTLE_SEC

# Two price keys closer than this are one price (keys are rounded to six places).
PRICE_EPS = 1e-7


@dataclass(frozen=True)
class MatchParams:
    """How far either side of a drop's two books a print may arrive and still fill it."""

    before_sec: float = BOOK_WATCH_MATCH_SLACK_SEC
    after_sec: float = BOOK_WATCH_MATCH_SLACK_SEC
    settle_sec: float = BOOK_WATCH_SETTLE_SEC

    def __post_init__(self) -> None:
        if self.before_sec < 0 or self.after_sec < 0:
            raise ValueError("the matching window cannot be negative")
        if not self.settle_sec > self.after_sec:
            raise ValueError("settle_sec must exceed after_sec, or a print inside the window may not have arrived")


DEFAULT_MATCH = MatchParams()


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
