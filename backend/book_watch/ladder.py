"""The book watcher on the Level 2 ladder (ADR 033 amendment, 2026-09-29; Sim replay #617).

What one ``/ws/ibkr/depth/{symbol}`` socket is sent as ``{"type": "book_watch", "data": ...}``
frames beside its books. The socket asks ``LadderPush.frame`` at most every
``BOOK_WATCH_PUSH_SEC``; a frame goes out only when there is news:

- the first frame (``reset: true``) carries the large drops of the last
  ``BOOK_WATCH_LADDER_MEMORY_SEC``, so a price pulled before the socket opened is still
  "pulled here" on the ladder;
- later frames carry only the drops judged since (``reset: false``);
- ``hidden`` carries the hidden sellers' and buyers' words the same way (``hidden.py``): the
  first frame the newest word on each stretch still holding or heard in that memory, later
  frames each new word (a stretch speaks when it is flagged, as it grows, and when it ends);
- each side's totals ride on every frame and are refreshed on their own at most every
  ``BOOK_WATCH_SIDES_PUSH_SEC``;
- ``big`` carries the line's big sellers and buyers (``big_seller.py``, #984) whole, on the first frame and
  on every frame after one of them changed, and at most every ``BOOK_WATCH_SIDES_PUSH_SEC`` while one holds
  (its seconds of lit volume move with the pace); ``big_float`` rides with it -- the float Nova already read
  for the symbol (cache only, never a fetch);
- on a Sim replay off the live edge (#617), ``ladder_replay.py`` feeds the same ``SymbolWatch`` detector over
  the loaded recording's own books and prints up to the playhead (``source: "replay"``); while no usable
  depth and tape cover the playhead or the watcher is off, one ``watching: false`` frame says why, then nothing.

Owner: each socket's own ``LadderPush`` (in memory, gone with the socket). Hints
consistent with spoofing -- never a detection.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from book_watch import live
from book_watch.constants_book_watch import (
    BOOK_WATCH_NOTE,
    BOOK_WATCH_OFF_REASON,
    BOOK_WATCH_SCHEMA_VERSION,
    BOOK_WATCH_SIDES_PUSH_SEC,
    BOOK_WATCH_STATS_WINDOW_SEC,
)

logger = logging.getLogger(__name__)


def big_float(symbol: str) -> dict[str, Any] | None:
    """The symbol's float from the fundamentals already read (never a Yahoo fetch), or None."""
    try:
        from fundamentals import peek_cached

        row = peek_cached(symbol)
    except Exception:
        logger.warning("book watch: the cached float of %s is unreadable -- the ladder shows none", symbol,
                       exc_info=True)
        return None
    shares = row.get("float_shares") if row else None
    if isinstance(shares, bool) or not isinstance(shares, (int, float)) or shares <= 0:
        return None
    return {"shares": float(shares), "contradicted": row.get("float_contradicted") is True}


class LadderPush:
    """One socket's position in its line's verdicts."""

    def __init__(self, symbol: str) -> None:
        self.symbol = (symbol or "").upper()
        self.source: str | None = None
        self.epoch: int | None = None
        self.last_now: float | None = None
        self.seq: int | None = None  # None: the next frame starts the ladder over
        self.hidden_seq: int | None = None
        self.big_version: int | None = None
        self.big_ts = 0.0
        self.sides: dict[str, Any] | None = None
        self.sides_ts = 0.0
        self.watching: bool | None = None
        self.absent: str | None = None  # the reason last sent for having no verdicts

    def _clear_cursor(self) -> None:
        self.epoch = None
        self.last_now = None
        self.seq = None
        self.hidden_seq = None
        self.big_version = None
        self.big_ts = 0.0
        self.sides = None
        self.sides_ts = 0.0
        self.watching = None
        self.absent = None

    def frame(self, now: float | None = None, *, live_line: bool = True) -> dict[str, Any] | None:
        """The next frame for this socket, or None when there is nothing new.

        ``live_line`` is False while the ladder shows a Sim replay rather than the live book."""
        source = "live" if live_line else "replay"
        if self.source != source:
            self._clear_cursor()
            self.source = source
        if not live.enabled():
            clock = (time.time() if now is None else now) if live_line else (now if now is not None else 0.0)
            return self._absent(BOOK_WATCH_OFF_REASON, clock, source=source)
        if not live_line:
            from book_watch import ladder_replay

            view = ladder_replay.ladder_view(
                self.symbol,
                self.seq,
                now,
                self.hidden_seq if self.seq is not None else None,
                epoch=self.epoch,
            )
            playhead = float(view.get("now") if view.get("now") is not None else (now or 0.0))
            if not view.get("watching"):
                return self._absent(view.get("reason") or "Replay book watcher unavailable.", playhead, source="replay")
            return self._emit(view, playhead, source="replay")
        now = time.time() if now is None else now
        view = live.ladder_view(self.symbol, self.seq, now, self.hidden_seq if self.seq is not None else None)
        if view is None:
            return None  # no book has reached the watcher yet: nothing to say
        return self._emit(view, now, source="live")

    def _emit(self, view: dict[str, Any], now: float, *, source: str) -> dict[str, Any] | None:
        epoch = view.get("epoch")
        # A line forgotten and watched again numbers from 1; a replay rewind or source change bumps epoch.
        reset = (
            self.seq is None
            or view["seq"] < self.seq
            or (epoch is not None and self.epoch is not None and epoch != self.epoch)
            or (self.last_now is not None and now < self.last_now)
        )
        drops, hidden = view["drops"], view["hidden"]
        sides_due = view["sides"] != self.sides and (reset or now - self.sides_ts >= BOOK_WATCH_SIDES_PUSH_SEC)
        big_due = (
            reset
            or view["big_version"] != self.big_version
            or (view["big_holding"] and now - self.big_ts >= BOOK_WATCH_SIDES_PUSH_SEC)
        )
        if not (reset or drops or hidden or sides_due or big_due or view["watching"] != self.watching):
            return None
        big: dict[str, Any] = {}
        if big_due:
            items = view["big_items"] if "big_items" in view else (live.big_items(self.symbol, now) or [])
            big = {"big": items, "big_float": big_float(self.symbol)}
            self.big_version, self.big_ts = view["big_version"], now
        self.epoch = epoch
        self.last_now = now
        self.seq, self.sides, self.sides_ts = view["seq"], view["sides"], now
        self.hidden_seq = view["hidden_seq"]
        self.watching, self.absent = view["watching"], None
        return {
            "schema_version": BOOK_WATCH_SCHEMA_VERSION,
            "source": source,
            "now": round(now, 3),
            "reset": reset,
            "seq": view["seq"],
            "watching": view["watching"],
            "reason": None,
            "window_sec": view["window_sec"],
            "sides": view["sides"],
            "drops": drops,
            "hidden": hidden,
            **big,
            "note": BOOK_WATCH_NOTE,
        }

    def _absent(self, reason: str, now: float, *, source: str = "live") -> dict[str, Any] | None:
        if self.absent == reason:
            return None
        self.absent, self.seq, self.sides, self.watching = reason, None, None, False
        self.hidden_seq = self.big_version = self.epoch = self.last_now = None
        return {
            "schema_version": BOOK_WATCH_SCHEMA_VERSION,
            "source": source,
            "now": round(now, 3),
            "reset": True,
            "seq": 0,
            "watching": False,
            "reason": reason,
            "window_sec": BOOK_WATCH_STATS_WINDOW_SEC,
            "sides": None,
            "drops": [],
            "hidden": [],
            "big": [],
            "big_float": None,
            "note": BOOK_WATCH_NOTE,
        }
