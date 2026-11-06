"""What Claude sees of one stock when it looks: the Level 2 book, the last prints, the quote, the view lock.

Read-only, over the lines the desk already holds (``ibkr.depth``'s book, the tape archive ``l2.tape``, IBKR's Level 1
through Paper's reference). Nothing here opens a line: a stock without one answers so.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

_PRINT_KEYS = ("ts", "price", "size", "side", "exchange", "bid", "ask", "conditions")
_BOOK_ROWS = 10


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def tape_summary(prints: list[dict[str, Any]]) -> dict[str, Any]:
    """Volume, the price range, VWAP and how much traded at or above the ask / at or under the bid."""
    vol = at_ask = at_bid = 0.0
    notional = 0.0
    prices = []
    for row in prints:
        px, size = _num(row.get("price")), _num(row.get("size")) or 0.0
        if px is None:
            continue
        prices.append(px)
        vol += size
        notional += px * size
        bid, ask = _num(row.get("bid")), _num(row.get("ask"))
        if ask is not None and px >= ask:
            at_ask += size
        elif bid is not None and px <= bid:
            at_bid += size
    return {"prints": len(prices), "volume": vol, "high": max(prices) if prices else None,
            "low": min(prices) if prices else None, "vwap": notional / vol if vol else None,
            "at_ask": at_ask, "at_bid": at_bid}


async def look(symbol: str, seconds: float = 120.0, max_prints: int = 200) -> dict[str, Any]:
    from agent_trader import bands, lines
    from ibkr import depth
    from ibkr.depth import state as depth_state
    from l2 import tape
    from market_view import gate
    from practice.reference import LiveReference

    sym = (symbol or "").strip().upper()
    now = time.time()
    book = depth.current_book(sym) or {}
    ref = LiveReference().reference(sym)
    rows = await asyncio.to_thread(tape.get_trades_in_range, sym, now - float(seconds), now)
    prints = [{k: row.get(k) for k in _PRINT_KEYS if k in row} for row in rows]
    lock = gate.desk_lock(sym)
    luld = bands.of(sym, ref.last)
    return {
        "symbol": sym, "at": now,
        "line": {"depth": depth.is_live(sym), "tape": tape.is_watched(sym), "claude_holds": lines.holds(sym),
                 "book_at": depth_state.last_book_at(sym)},
        "quote": {"last": ref.last, "bid": ref.bid, "ask": ref.ask},
        "book": {"bids": list(book.get("bids") or [])[:_BOOK_ROWS], "asks": list(book.get("asks") or [])[:_BOOK_ROWS],
                 "l1_fallback": bool(book.get("l1_fallback")), "at_limit": bands.at_limit(book, luld)},
        "luld": luld,
        "tape": {"seconds": float(seconds), "summary": tape_summary(prints), "prints": prints[-int(max_prints):]},
        "locked": lock,
    }
