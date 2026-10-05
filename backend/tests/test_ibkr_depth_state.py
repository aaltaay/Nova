"""Tests for ibkr.depth.state: each viewer holds the newest book, versioned (ADR 045)."""
from __future__ import annotations

import asyncio

from ibkr.depth import state
from market_view import versions
from market_view.viewer_queues import BookVersion
from perf import counters


def _reset() -> None:
    state.reset_all()
    versions.reset_for_tests()
    counters.reset_for_tests()


def test_a_viewer_holds_the_newest_book_never_a_backlog():
    """2026-10-05: a 100-book FIFO replayed seconds of old books after a stall. Now a viewer gets
    the newest book; the ones it never sent are counted, not queued."""
    _reset()
    state.reserve_slot("XYZ")
    q = state.open_viewer_queue("XYZ")
    for price in (1.0, 1.1, 1.2):
        state.push_book("XYZ", {"bids": [{"price": price}], "asks": [], "l1_fallback": False})

    assert q.qsize() == 1
    item = q.get_nowait()
    assert isinstance(item, BookVersion)
    assert item.book["bids"][0]["price"] == 1.2
    assert item.seq == 3
    assert counters.read()["depth.viewer_skipped"] == 2


def test_control_frames_come_before_the_book_and_none_is_lost():
    _reset()
    q = state.open_viewer_queue("XYZ")
    state.push_book("XYZ", {"bids": [{"price": 2.0}], "asks": [], "l1_fallback": False})
    state.push_error("XYZ", "line dropped")
    state.push_lent("XYZ", {"symbol": "XYZ", "to": {"symbol": "AAA"}})

    assert q.get_nowait()["type"] == "error"
    assert q.get_nowait()["type"] == "lent"
    assert q.get_nowait().book["bids"][0]["price"] == 2.0
    assert q.qsize() == 0


def test_a_plain_asyncio_queue_still_drops_its_oldest():
    _reset()
    small_q: asyncio.Queue = asyncio.Queue(maxsize=1)
    state._viewer_queues["XYZ"] = [small_q]
    small_q.put_nowait({"bids": [], "asks": [], "stale": True})

    state.push_book("XYZ", {"bids": [{"price": 1.0}], "asks": []})

    assert small_q.qsize() == 1
    assert small_q.get_nowait().book["bids"][0]["price"] == 1.0
    assert counters.read()["depth.viewer_dropped"] == 1


def test_push_book_broadcasts_to_every_viewer():
    """2026-08-25: a single shared queue per symbol made two viewers
    competing consumers instead of both getting every book update -- the
    same defect class fixed in tape_stream.py first.
    """
    _reset()
    q1 = state.open_viewer_queue("XYZ")
    q2 = state.open_viewer_queue("XYZ")

    state.push_book("XYZ", {"bids": [{"price": 2.5}], "asks": []})

    assert q1.get_nowait().book["bids"][0]["price"] == 2.5
    assert q2.get_nowait().book["bids"][0]["price"] == 2.5


def test_every_book_is_versioned_and_the_version_is_readable():
    _reset()
    assert state.book_version("XYZ") is None
    first = state.push_book("XYZ", {"bids": [], "asks": [], "l1_fallback": True})
    second = state.push_book("XYZ", {"bids": [{"price": 3.0}], "asks": [], "l1_fallback": False})
    assert (first.seq, second.seq) == (1, 2)
    assert state.book_version("XYZ").seq == 2
    assert versions.replaced(versions.BOOK, "XYZ", 1).at == second.at


def test_depth_stream_hands_the_loop_back_between_books():
    """Like the tape's, a backlog of books must not hold the HTTP loop (#619)."""
    from ibkr.depth.stream import stream
    from tests.test_ibkr_tape_stream import _loop_turns_while_draining

    got, turns = _loop_turns_while_draining(stream, 200)
    assert got == 200
    assert turns >= 150
