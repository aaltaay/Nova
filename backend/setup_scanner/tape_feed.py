"""What the tape gate reads: Level 2 samples and prints for the symbols the
scanner is watching closely -- passively.

ADR 016 decision 2 and ADR 022: the scanner opens no IBKR line of its own.
It reads a symbol's book only while Nova already holds a real depth line for
it (a Trader tab's Level 2, a Session Record), and its prints through an extra
viewer queue on a tick-by-tick line someone else holds. An extra queue does
not keep a line alive: the line's viewer refcount is untouched, so closing
the Trader tab still releases it. Without a line the gate says ``blind``.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

from constants_setups import TAPE_GATE_BOOK_SAMPLE_SEC, TAPE_GATE_WINDOW_SEC

logger = logging.getLogger(__name__)

BOOK_KEEP = 80
PRINT_KEEP = 5000
KEEP_SEC = 3 * TAPE_GATE_WINDOW_SEC


class TapeFeed:
    def __init__(self, depth: Any = None, tape: Any = None):
        if depth is None:
            from ibkr.depth import state as depth
        if tape is None:
            from ibkr import tape_stream as tape
        self._depth = depth
        self._tape = tape
        self._books: dict[str, deque] = {}
        self._prints: dict[str, deque] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._last_sample: dict[str, float] = {}
        self._keep_sec = KEEP_SEC
        self._book_keep = BOOK_KEEP

    def keep_window(self, window_sec: float) -> None:
        """Keep enough history for the longest tape window any template reads (ADR 029)."""
        keep = max(KEEP_SEC, 3 * float(window_sec))
        if keep == self._keep_sec:
            return
        self._keep_sec = keep
        self._book_keep = max(BOOK_KEEP, int(keep / TAPE_GATE_BOOK_SAMPLE_SEC) + 4)
        for sym, dq in list(self._books.items()):
            self._books[sym] = deque(dq, maxlen=self._book_keep)

    def has_depth(self, sym: str) -> bool:
        try:
            return bool(self._depth.is_live(sym))
        except Exception:
            logger.debug("setup tape feed: depth check failed for %s", sym, exc_info=True)
            return False

    def has_tape(self, sym: str) -> bool:
        return sym in self._queues

    def sync(self, wanted: set[str], now: float) -> None:
        """Sample books, attach / detach print queues, drain prints."""
        for sym in wanted:
            if self.has_depth(sym) and now - self._last_sample.get(sym, 0.0) >= TAPE_GATE_BOOK_SAMPLE_SEC:
                book = self._depth.current_book(sym)
                if book and (book.get("bids") or book.get("asks")):
                    self._books.setdefault(sym, deque(maxlen=self._book_keep)).append((now, book))
                    self._last_sample[sym] = now
            if sym not in self._queues and self._tape.is_subscribed(sym):
                self._queues[sym] = self._tape.open_viewer_queue(sym)
        for sym in list(self._queues):
            if sym not in wanted:
                self._drop(sym)
        for sym in list(self._books):
            if sym not in wanted:
                self._books.pop(sym, None)
                self._last_sample.pop(sym, None)
        for sym, q in self._queues.items():
            buf = self._prints.setdefault(sym, deque(maxlen=PRINT_KEEP))
            while True:
                try:
                    pr = q.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if isinstance(pr, dict):
                    buf.append(pr)
            while buf and float(buf[0].get("ts") or 0) < now - self._keep_sec:
                buf.popleft()

    def books(self, sym: str) -> list[tuple[float, dict]]:
        return list(self._books.get(sym, ()))

    def prints(self, sym: str) -> list[dict]:
        return list(self._prints.get(sym, ()))

    def _drop(self, sym: str) -> None:
        q = self._queues.pop(sym, None)
        if q is not None:
            try:
                self._tape.close_viewer_queue(sym, q)
            except Exception:
                logger.warning("setup tape feed: could not close the print queue for %s", sym, exc_info=True)
        self._prints.pop(sym, None)

    def close(self) -> None:
        for sym in list(self._queues):
            self._drop(sym)
        self._books.clear()
