"""
Classify Time & Sales prints against the best bid/ask at receipt time.

Convention (matches typical DAS / Warrior T&S aggressor coloring):
  - ask     → print at or above the ask (buyer lifted the offer)
  - bid     → print at or below the bid (seller hit the bid)
  - between → print strictly inside the spread
  - unknown → missing, non-positive, or crossed book
"""
from __future__ import annotations

from typing import Any

TAPE_SIDE_ASK = "ask"
TAPE_SIDE_BID = "bid"
TAPE_SIDE_BETWEEN = "between"
TAPE_SIDE_UNKNOWN = "unknown"


def best_bid_ask(book: dict[str, Any] | None) -> tuple[float | None, float | None]:
    """Top-of-book bid/ask from an IBKR depth (or L1 fallback) book dict."""
    if not book:
        return None, None
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    bid = None
    ask = None
    if bids:
        try:
            bid = float(bids[0]["price"])
        except (KeyError, TypeError, ValueError):
            bid = None
    if asks:
        try:
            ask = float(asks[0]["price"])
        except (KeyError, TypeError, ValueError):
            ask = None
    return bid, ask


def classify_print_side(
    price: float,
    bid: float | None,
    ask: float | None,
) -> str:
    """Return ask | bid | between | unknown for a print vs BBO."""
    if bid is None or ask is None:
        return TAPE_SIDE_UNKNOWN
    try:
        bid_f = float(bid)
        ask_f = float(ask)
        px = float(price)
    except (TypeError, ValueError):
        return TAPE_SIDE_UNKNOWN
    if bid_f <= 0 or ask_f <= 0 or px <= 0:
        return TAPE_SIDE_UNKNOWN
    # Crossed / locked book is not trustworthy for aggressor side.
    if bid_f > ask_f:
        return TAPE_SIDE_UNKNOWN
    if px <= bid_f:
        return TAPE_SIDE_BID
    if px >= ask_f:
        return TAPE_SIDE_ASK
    return TAPE_SIDE_BETWEEN
