"""IBKR depth book streaming for WebSocket consumers."""
from __future__ import annotations

import asyncio

from ibkr.depth import state


def should_send_current_book(book: dict | None) -> bool:
    """Whether a freshly-opened WS viewer should receive an immediate snapshot."""
    if book is None:
        return False
    return bool(book["bids"] or book["asks"] or book["l1_fallback"])


async def stream(symbol: str):
    """AsyncGenerator yielding book snapshots for the given symbol."""
    q = state._queues.get(symbol)
    if q is None:
        return
    while True:
        try:
            book = await asyncio.wait_for(q.get(), timeout=15)
            yield book
        except asyncio.TimeoutError:
            yield None
