"""Tests for ibkr.depth.state queue backpressure visibility."""
from __future__ import annotations

import asyncio

from ibkr.depth import state


def test_push_book_drops_oldest_when_full():
    state.reset_all()
    state.reserve_slot("XYZ")
    q = state.open_viewer_queue("XYZ")
    assert q.maxsize == 100

    small_q: asyncio.Queue = asyncio.Queue(maxsize=1)
    state._viewer_queues["XYZ"] = [small_q]
    small_q.put_nowait({"bids": [], "asks": [], "stale": True})

    state.push_book("XYZ", {"bids": [{"price": 1.0}], "asks": []})

    assert small_q.qsize() == 1
    book = small_q.get_nowait()
    assert book["bids"][0]["price"] == 1.0


def test_push_book_broadcasts_to_every_viewer():
    """2026-08-25: a single shared queue per symbol made two viewers
    competing consumers instead of both getting every book update -- the
    same defect class fixed in tape_stream.py first.
    """
    state.reset_all()
    q1: asyncio.Queue = asyncio.Queue()
    q2: asyncio.Queue = asyncio.Queue()
    state._viewer_queues["XYZ"] = [q1, q2]

    state.push_book("XYZ", {"bids": [{"price": 2.5}], "asks": []})

    assert q1.get_nowait()["bids"][0]["price"] == 2.5
    assert q2.get_nowait()["bids"][0]["price"] == 2.5
