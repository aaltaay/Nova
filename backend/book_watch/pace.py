"""How fast a stock trades on the lit book: the shares of its lit trades over the last minute (#984).

A big seller's ``clear_sec`` is its size over this pace -- the seconds the last minute's lit volume would take
to trade it (``big_seller.py``). Every lit trade counts, odd lots included; a cross or a volume-only print is no
trading pace, and an off-exchange report never touches the lit book. Before ``min_sec`` of watching there is
no pace: a few seconds' prints are no minute's. A ratio of what Nova saw, never a forecast.

Pure: prints in, the pace out.
"""
from __future__ import annotations

from collections import deque
from typing import Any

from book_watch.constants_book_watch import (
    BOOK_WATCH_AUCTION_CONDITIONS,
    BOOK_WATCH_BIG_PACE_MIN_SEC,
    BOOK_WATCH_BIG_PACE_SEC,
    BOOK_WATCH_HIDDEN_SKIP_CONDITIONS,
)

PACE_SKIP = BOOK_WATCH_AUCTION_CONDITIONS | BOOK_WATCH_HIDDEN_SKIP_CONDITIONS


class LitPace:
    def __init__(self, window_sec: float = BOOK_WATCH_BIG_PACE_SEC, min_sec: float = BOOK_WATCH_BIG_PACE_MIN_SEC) -> None:
        self.window_sec = window_sec
        self.min_sec = min_sec
        self.prints: deque[tuple[float, float]] = deque()  # (ts, shares)
        self.since: float | None = None                    # the first book since start or a reset

    def on_book(self, ts: float) -> None:
        if self.since is None:
            self.since = ts

    def on_print(self, ts: float, shares: float, *, lit: bool, conditions: Any) -> None:
        if not lit or self.since is None or set(str(conditions or "")) & PACE_SKIP:
            return
        self.prints.append((ts, shares))
        while self.prints and self.prints[0][0] < ts - self.window_sec:
            self.prints.popleft()

    def reset(self) -> None:
        self.prints.clear()
        self.since = None

    def rate(self, now: float) -> tuple[dict[str, float] | None, float | None]:
        """``{window_sec, lit_shares}`` (None before ``min_sec`` of watching) and lit shares a second (None
        with no lit trade in the window)."""
        if self.since is None:
            return None, None
        window = min(self.window_sec, now - self.since)
        if window < self.min_sec:
            return None, None
        lit = sum(sh for t, sh in self.prints if now - self.window_sec <= t <= now)
        return {"window_sec": round(window, 1), "lit_shares": lit}, (lit / window if lit > 0 else None)
