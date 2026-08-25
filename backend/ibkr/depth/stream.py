"""IBKR depth book streaming for WebSocket consumers."""
from __future__ import annotations

import asyncio


def should_send_current_book(book: dict | None) -> bool:
    """Whether a freshly-opened WS viewer should receive an immediate snapshot."""
    if book is None:
        return False
    return bool(book["bids"] or book["asks"] or book["l1_fallback"])


async def stream(queue: asyncio.Queue):
    """AsyncGenerator yielding book snapshots (or None on heartbeat timeout)
    for one viewer's own queue -- see ``state.open_viewer_queue``.
    """
    while True:
        try:
            book = await asyncio.wait_for(queue.get(), timeout=15)
            yield book
        except asyncio.TimeoutError:
            yield None
