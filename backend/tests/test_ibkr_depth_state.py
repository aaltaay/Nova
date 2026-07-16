"""Tests for ibkr.depth.state queue backpressure visibility."""
from __future__ import annotations

import asyncio

from ibkr.depth import state


def test_push_book_drops_oldest_when_full():
    state.reset_all()
    state.reserve_slot("XYZ")
    q = state._queues["XYZ"]
    assert q.maxsize == 100

    small_q: asyncio.Queue = asyncio.Queue(maxsize=1)
    state._queues["XYZ"] = small_q
    small_q.put_nowait({"bids": [], "asks": [], "stale": True})

    state.push_book("XYZ", {"bids": [{"price": 1.0}], "asks": []})

    assert small_q.qsize() == 1
    book = small_q.get_nowait()
    assert book["bids"][0]["price"] == 1.0
