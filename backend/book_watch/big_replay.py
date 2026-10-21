"""Big sellers and buyers on a Sim replay (#846): the same tracker over a Session Record, at the playhead.

On a Sim desk off the live edge with a Session Record of the stock loaded (``sim.capture_player``), the
reading is ``big_seller.py``'s tracker over the recording's own books and prints from
``BOOK_WATCH_BIG_REPLAY_LOOKBACK_SEC`` before the playhead up to the playhead -- never past it. A price
that was big in the first book of that stretch reads ``seen_from_start`` ("held 3 min+"). The tracker is
fed forward as the playhead moves, and rebuilt when the playhead moves back, jumps further than the
lookback, or another recording loads, so a rewind never shows what came later.

A recording loaded with more books than the player keeps (``CAPTURE_L2_LOAD_LIMIT``) is thinned evenly:
the reading says how many books a second it read. A book recorded while IBKR served Level 1 only
(``l1_fallback``) is no depth: the tracker resets there, as the live watcher does.

Owner: this module's one replay state (in memory, rebuilt per recording). Not persisted.
"""
from __future__ import annotations

import bisect
import threading
from typing import Any

from book_watch.big_seller import BigWallTracker
from book_watch.book import RecordedCopies, lit_print, price_key, side_view
from book_watch.constants_book_watch import BOOK_WATCH_BIG_REPLAY_LOOKBACK_SEC, BOOK_WATCH_IDLE_SEC

_lock = threading.Lock()
_state: dict[str, Any] | None = None


def _num_rows() -> int:
    from constants import IBKR_DEPTH_NUM_ROWS

    return int(IBKR_DEPTH_NUM_ROWS)


def _start(data: Any, playhead: float, lookback: float) -> dict[str, Any]:
    start = playhead - lookback
    book_i = bisect.bisect_left(data.l2_keys, start)
    copies = RecordedCopies()  # each recorded book against the one before it (#1133)
    if book_i:
        copies.read(data.l2[book_i - 1])
    return {
        "key": data.key, "tracker": BigWallTracker(data.symbol), "views": None, "fed_to": start, "start": start,
        "book_i": book_i, "print_i": bisect.bisect_left(data.print_keys, start), "copies": copies,
        "last_book_ts": None, "books": 0,
    }


def _feed(st: dict[str, Any], data: Any, playhead: float, num_rows: int) -> None:
    """Every recorded book and print after what was fed, up to ``playhead``, in arrival order."""
    tracker: BigWallTracker = st["tracker"]
    bi, pi = st["book_i"], st["print_i"]
    b_end = bisect.bisect_right(data.l2_keys, playhead)
    p_end = bisect.bisect_right(data.print_keys, playhead)
    while bi < b_end or pi < p_end:
        if pi >= p_end or (bi < b_end and data.l2_keys[bi] <= data.print_keys[pi]):
            ts, row = data.l2_keys[bi], data.l2[bi]
            bi += 1
            if row.get("l1_fallback"):
                tracker.reset(ts)
                st["views"] = None
                continue
            row = st["copies"].read(row)
            views = {"bid": side_view(row.get("bids") or [], "bid", num_rows),
                     "ask": side_view(row.get("asks") or [], "ask", num_rows)}
            tracker.on_book(ts, views, st["views"])
            st["views"], st["last_book_ts"] = views, ts
            st["books"] += 1
            continue
        ts, row = data.print_keys[pi], data.prints[pi]
        pi += 1
        key = price_key(row.get("price"))
        try:
            shares = float(row.get("size") or 0)
        except (TypeError, ValueError):
            continue
        if key is not None and shares > 0:
            tracker.on_print(ts, key, shares, lit=lit_print(row), conditions=row.get("conditions"))
    tracker.tick(playhead)
    st["book_i"], st["print_i"], st["fed_to"] = bi, pi, playhead


def reading(data: Any, playhead: float, *, lookback: float = BOOK_WATCH_BIG_REPLAY_LOOKBACK_SEC,
            num_rows: int | None = None) -> dict[str, Any]:
    """The tracker's reading at ``playhead`` over the loaded recording ``data`` (a ``CaptureData``), with how
    fresh the recorded book is there."""
    global _state
    rows = num_rows if num_rows is not None else _num_rows()
    with _lock:
        st = _state
        if (st is None or st["key"] != data.key or playhead < st["fed_to"]
                or playhead - st["fed_to"] > lookback):
            st = _start(data, playhead, lookback)
        _feed(st, data, playhead, rows)
        _state = st
        last = st["last_book_ts"]
        age = None if last is None else playhead - last
        span = playhead - st["start"]
        return {
            "since": st["start"], "last_book_ts": last, "last_book_age_sec": None if age is None else round(age, 3),
            "watching": age is not None and age <= BOOK_WATCH_IDLE_SEC,
            "lookback_sec": lookback, "books_per_sec": round(st["books"] / span, 2) if span > 0 else None,
            **st["tracker"].reading(playhead),
        }


def reset_for_tests() -> None:
    global _state
    with _lock:
        _state = None
