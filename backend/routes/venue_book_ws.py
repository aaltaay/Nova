"""``WS /ws/ibkr/venue-book/{symbol}``: the brain's Nasdaq book, for whoever joins it (ADR 072 Amendment 5).

A socket here only joins: it never opens the line, never moves a lane, and closing it ends nothing
(``line_lanes.lanes`` alone puts the book on a stock). Frames, ``architecture/schema/market-data.md``
"The brain's Nasdaq book":

  ``{"type": "subscribed", "symbol", "venue"}``
  ``{"type": "book", "symbol", "venue", "data": {"bids", "asks"}, "seq", "at", "sent"}``   every changed book, rows as IBKR holds them
  ``{"type": "waiting", "symbol", "venue", "message"}``    the book is not up (no free Level 2 line, IBKR's refusal, not this stock); sent each beat
  ``{"type": "closed", "symbol", "venue", "reason"}``      the line ended; the socket stays open and waits for the next
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import WebSocket, WebSocketDisconnect

from constants_market_view import MARKET_VIEW_BEAT_SEC
from ibkr import venue_book
from market_view.viewer_queues import BookVersion

logger = logging.getLogger(__name__)

NOT_THIS_STOCK_WORDS = "The brain's lane is not on {symbol}."


def waiting_words(symbol: str) -> str | None:
    """Why ``symbol``'s Nasdaq book is not up, in words; None when it is."""
    if venue_book.is_up(symbol):
        return None
    st = venue_book.status()
    if st["symbol"] != symbol:
        return NOT_THIS_STOCK_WORDS.format(symbol=symbol)
    return st["error"] or f"Waiting for IBKR to open {venue_book.VENUE}'s own book of {symbol}."


def book_frame(symbol: str, item: BookVersion, now: float | None = None) -> str:
    return json.dumps({"type": "book", "symbol": symbol, "venue": venue_book.VENUE, "data": item.book, "seq": item.seq, "at": item.at,
                       "sent": time.time() if now is None else now})


async def run_ws_venue_book(websocket: WebSocket, symbol: str) -> None:
    symbol = symbol.strip().upper()
    await websocket.accept()
    queue = venue_book.open_viewer(symbol)
    try:
        await websocket.send_text(json.dumps({"type": "subscribed", "symbol": symbol, "venue": venue_book.VENUE}))
        data = venue_book.current(symbol)
        if data is not None:
            st = venue_book.status()
            await websocket.send_text(book_frame(symbol, BookVersion(st["seq"], st["at"] or 0.0, data)))
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=MARKET_VIEW_BEAT_SEC)
            except asyncio.TimeoutError:
                why = waiting_words(symbol)
                if why is not None:
                    await websocket.send_text(json.dumps({"type": "waiting", "symbol": symbol, "venue": venue_book.VENUE, "message": why}))
                continue
            if isinstance(item, BookVersion):
                await websocket.send_text(book_frame(symbol, item))
            else:
                await websocket.send_text(json.dumps(item))
    except WebSocketDisconnect:
        logger.debug("IBKR venue book WS disconnected: %s", symbol)
    except Exception as exc:
        from ws_close_errors import is_websocket_send_after_close

        if is_websocket_send_after_close(exc):
            logger.debug("IBKR venue book WS send-after-close: %s", symbol)
        else:
            logger.exception("IBKR venue book WS error for %s: %s", symbol, exc)
    finally:
        venue_book.close_viewer(symbol, queue)
