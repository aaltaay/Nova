"""One exchange's own order book for the brain's lane: Nasdaq's, beside the all-exchange Level 2 (ADR 072 Amendment 5).

Owns the one extra Level 2 request Nova makes on an exchange itself (``Stock(sym, "NASDAQ")``,
``isSmartDepth=False``, 20 rows a side), the book kept from its row operations, and the viewers of it. It is a
book of its own: ``ibkr.depth`` never sees it, so nothing that reads the all-exchange book (your Level 2 pane,
Paper fills, the book watcher, a print's side, the view gate, recordings) reads this one.

``line_lanes.lanes`` is the only caller of ``follow``: the book is on the stock the brain's lane is on while a
Level 2 line is free, and gives its line back the moment your lane or Claude's needs it.

line.py (the request, the book, the frames).
"""
from ibkr.venue_book.line import (
    VENUE,
    close,
    close_viewer,
    current,
    follow,
    held,
    is_up,
    open_viewer,
    reset_for_tests,
    status,
    symbol,
)

__all__ = ["VENUE", "close", "close_viewer", "current", "follow", "held", "is_up", "open_viewer", "reset_for_tests",
           "status", "symbol"]
