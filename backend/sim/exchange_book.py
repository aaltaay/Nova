"""An exchange's own book on the Sim's Level 2 (ADR 057): what the replay snapshot reads at the playhead.

The import (``sim.exchange_book_import``, by hand) leaves a symbol-day's venue books in ``exchange_book_store``.
``at`` answers the historical snapshot with two things: the depth to draw -- every venue book whose span holds the
playhead, merged by price into one montage, each level keeping its venue -- and the coverage of every book of
that symbol-day, so the ladder can say what was imported and when, even where none covers the playhead.

**One venue's book is never the market's.** It is labelled with its venue on every level and in ``venues``, and
nothing here becomes a bid, an ask or a fill. **Never read ahead:** a venue's event is its last at or before the
playhead, taken to its microsecond (the playhead is a datetime). Outside a book's span there is no book from it.

Cost: the Level 2 panel polls the snapshot every second. The list of a day's books is read again at most every
``SIM_EXCHANGE_BOOK_LIST_TTL_SEC`` (an import in another process shows up within it), a book's chunk index is held
with it, and inflated chunks are held in a small LRU, so a poll is a bisect or two. A missing store is no book; an
unreadable one is logged once per outage and reads as no book, never an error in the replay.
"""
from __future__ import annotations

import bisect
import logging
import math
import sqlite3
import struct
import threading
import time
import zlib
from array import array
from collections import OrderedDict
from dataclasses import dataclass

from constants_sim import (
    SIM_EXCHANGE_BOOK_CHUNK_CACHE, SIM_EXCHANGE_BOOK_F_MAYBE_BAD_BOOK, SIM_EXCHANGE_BOOK_LEVELS,
    SIM_EXCHANGE_BOOK_LIST_TTL_SEC, SIM_EXCHANGE_BOOK_SOURCE,
)
from sim import exchange_book_store as store

logger = logging.getLogger(__name__)

_DAYS_KEPT = 16
_now = time.monotonic
_lock = threading.Lock()
# (symbol, date) -> (monotonic expiry, that day's books).
_days: OrderedDict[tuple[str, str], tuple[float, list[_Book]]] = OrderedDict()
# (book id, imported_at, ordinal) -> the chunk's columns; a new import of a book is a new key.
_chunks: OrderedDict[tuple[str, float, int], dict[str, array]] = OrderedDict()
_degraded: str | None = None


@dataclass(frozen=True)
class _Book:
    payload: dict
    starts: array
    counts: array


def reset_for_tests() -> None:
    global _degraded
    with _lock:
        _days.clear()
        _chunks.clear()
        _degraded = None


def _report(error: Exception | None) -> None:
    """One log line per store outage, and one when it clears."""
    global _degraded
    signature = f"{type(error).__name__}: {error}" if error is not None else None
    with _lock:
        if signature == _degraded:
            return
        previous, _degraded = _degraded, signature
    if signature is None:
        logger.info("Replay exchange books: the store is readable again (was %s)", previous)
    else:
        logger.warning("Replay exchange books: the store cannot be read; the replay goes on without them",
                       exc_info=error)


def _read_day(symbol: str, date: str) -> list[_Book]:
    db = store.reader()
    if db is None:
        return []
    try:
        return [_Book(payload, *store.chunk_index(db, payload["id"])) for payload in store.books_for(db, symbol, date)]
    finally:
        db.close()


def _day(symbol: str, date: str) -> list[_Book]:
    key, now = (symbol, date), _now()
    with _lock:
        hit = _days.get(key)
        if hit is not None and hit[0] > now:
            _days.move_to_end(key)
            return hit[1]
    books = _read_day(symbol, date)
    with _lock:
        _days[key] = (now + SIM_EXCHANGE_BOOK_LIST_TTL_SEC, books)
        _days.move_to_end(key)
        while len(_days) > _DAYS_KEPT:
            _days.popitem(last=False)
    return books


def _chunk(book: _Book, ordinal: int) -> dict[str, array]:
    payload = book.payload
    key = (payload["id"], payload["imported_at"], ordinal)
    with _lock:
        if key in _chunks:
            _chunks.move_to_end(key)
            return _chunks[key]
    db = store.reader()
    if db is None:
        raise sqlite3.OperationalError("the exchange book store is gone")
    try:
        blob, events = store.read_chunk(db, payload["id"], ordinal)
    finally:
        db.close()
    columns = store.unpack_chunk(blob, events)
    with _lock:
        _chunks[key] = columns
        while len(_chunks) > SIM_EXCHANGE_BOOK_CHUNK_CACHE:
            _chunks.popitem(last=False)
    return columns


def _ns(t: float) -> int:
    """The playhead to its microsecond, in nanoseconds (a datetime's float timestamp is exact to about 0.24 us)."""
    return round(t * 1_000_000) * 1_000


def _event_at(book: _Book, t_ns: int) -> tuple[dict[str, array], int] | None:
    """The book's last event at or before ``t_ns`` inside its span, as ``(chunk columns, index)``; else None."""
    payload = book.payload
    if not payload["known_from_ns"] <= t_ns < payload["known_to_ns"]:
        return None
    ordinal = bisect.bisect_right(book.starts, t_ns) - 1
    if ordinal < 0:
        return None
    columns = _chunk(book, ordinal)
    at = bisect.bisect_right(columns["ns"], t_ns) - 1
    return (columns, at) if at >= 0 else None


def _levels(columns: dict[str, array], at: int, side: str, venue: str) -> list[dict]:
    out = []
    for k in range(SIM_EXCHANGE_BOOK_LEVELS):
        price, size = columns[f"{side}_px_{k}"][at], columns[f"{side}_sz_{k}"][at]
        if math.isnan(price) or size <= 0:
            continue
        out.append(dict(price=price, size=size, orders=columns[f"{side}_ct_{k}"][at], mm=venue, exchange=venue))
    return out


def _seconds(ns: int) -> float:
    return ns / 1e9


def at(symbol: str, date: str, t: float) -> tuple[dict | None, list[dict]]:
    """``(depth, coverage)`` for ``symbol`` on ``date`` at playhead ``t`` (epoch seconds).

    ``depth`` is the montage of every venue book covering ``t`` (None when none does); ``coverage`` lists every
    book imported for that symbol-day, covering or not ([] with none, or when the store cannot be read).
    """
    try:
        books = _day(symbol.upper(), date)
        t_ns = _ns(t)
        shown, coverage = [], []
        for book in books:
            payload = book.payload
            found = _event_at(book, t_ns)
            event_ts, bad = None, False
            if found is not None:
                columns, index = found
                event_ts = _seconds(columns["ns"][index])
                bad = bool(columns["flags"][index] & SIM_EXCHANGE_BOOK_F_MAYBE_BAD_BOOK)
                shown.append((payload, columns, index, event_ts, bad))
            coverage.append(dict(venue=payload["venue"], label=payload["label"], dataset=payload["dataset"],
                                 known_from=_seconds(payload["known_from_ns"]),
                                 known_to=_seconds(payload["known_to_ns"]), events=payload["events"],
                                 imported_at=payload["imported_at"], covered=found is not None, book_ts=event_ts,
                                 maybe_bad_book=bad))
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError, zlib.error, struct.error) as exc:
        _report(exc)
        return None, []
    _report(None)
    if not shown:
        return None, coverage
    bids = [level for payload, columns, index, _ts, _bad in shown
            for level in _levels(columns, index, "bid", payload["venue"])]
    asks = [level for payload, columns, index, _ts, _bad in shown
            for level in _levels(columns, index, "ask", payload["venue"])]
    newest = max(event_ts for *_rest, event_ts, _bad in shown)
    return dict(symbol=symbol.upper(), bids=sorted(bids, key=lambda level: -level["price"]),
                asks=sorted(asks, key=lambda level: level["price"]), ts=newest, age_sec=round(max(0.0, t - newest), 6),
                l1_fallback=False, session_id=None, source=SIM_EXCHANGE_BOOK_SOURCE,
                venues=[dict(venue=payload["venue"], label=payload["label"], dataset=payload["dataset"], ts=event_ts,
                             maybe_bad_book=bad) for payload, _columns, _index, event_ts, bad in shown]), coverage
