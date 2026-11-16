"""IBKR depth book streaming for WebSocket consumers, and the frames that carry it (ADR 045)."""
from __future__ import annotations

import asyncio
import json
import logging
import time

from constants_market_view import MARKET_VIEW_BEAT_SEC
from market_view import versions
from market_view.viewer_queues import BookVersion

logger = logging.getLogger(__name__)


def should_send_current_book(book: dict | None) -> bool:
    """Whether a freshly-opened WS viewer should receive an immediate snapshot."""
    if book is None:
        return False
    return bool(book["bids"] or book["asks"] or book["l1_fallback"])


async def stream(queue, timeout: float = MARKET_VIEW_BEAT_SEC):
    """AsyncGenerator yielding one viewer's items -- a ``BookVersion`` (the newest book), a control
    frame (``error`` / ``lent``) -- or None after ``timeout`` without one; see
    ``state.open_viewer_queue``. The depth socket wakes this often to say the book is still current
    (``beat``) and to push the book watcher's verdicts (ADR 033).
    """
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            yield None
            continue
        yield item
        await asyncio.sleep(0)


def book_frame(symbol: str, item: BookVersion, now: float | None = None) -> str:
    """``{"type": "book", "symbol", "data", "seq", "at", "sent"}`` -- ``data`` is the book as it always was."""
    return json.dumps({
        "type": "book",
        "symbol": symbol,
        "data": item.book,
        "seq": item.seq,
        "at": item.at,
        "sent": time.time() if now is None else now,
    })


def beat_frame(symbol: str, now: float | None = None) -> str:
    """``{"type": "beat", "symbol", "seq", "at", "now", "first_book"}`` -- the line's newest version as of ``now``.

    ``first_book`` is null once the line's request delivered a book with a row, else what it is waiting for
    (``first_book.waiting``, #913). Left out when it cannot be read: the desk then keeps its lock.
    """
    t = time.time() if now is None else now
    latest = versions.latest(versions.BOOK, symbol)
    frame = {
        "type": "beat",
        "symbol": symbol,
        "seq": latest.seq if latest is not None else 0,
        "at": latest.at if latest is not None else None,
        "now": t,
    }
    try:
        from ibkr.depth import first_book

        frame["first_book"] = first_book.waiting(symbol, now=t)
    except Exception:
        logger.exception("IBKR depth: %s's first book could not be read for its beat", symbol)
    return json.dumps(frame)
