"""IBKR depth book streaming for WebSocket consumers."""
from __future__ import annotations

import asyncio


def should_send_current_book(book: dict | None) -> bool:
    """Whether a freshly-opened WS viewer should receive an immediate snapshot."""
    if book is None:
        return False
    return bool(book["bids"] or book["asks"] or book["l1_fallback"])


# A viewer with no book for this long is sent a ping.
DEPTH_STREAM_HEARTBEAT_SEC = 15.0


async def stream(queue: asyncio.Queue, timeout: float = DEPTH_STREAM_HEARTBEAT_SEC):
    """AsyncGenerator yielding book snapshots (or None after ``timeout`` without one)
    for one viewer's own queue -- see ``state.open_viewer_queue``. The depth socket
    wakes this often to push the book watcher's verdicts (ADR 033) and pings on its
    own clock.
    """
    while True:
        try:
            book = await asyncio.wait_for(queue.get(), timeout=timeout)
            yield book
        except asyncio.TimeoutError:
            yield None
