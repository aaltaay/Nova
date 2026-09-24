"""Test helper: a fake ib_async depth ticker whose ``domTicks`` set a whole book.

The depth handler keeps its own book from ``ticker.domTicks`` (#540), so a test
that wants the handler to show a given book sends IBKR row operations: an
update at each row (past the end it appends), then a delete of every deeper row
from the bottom up, so a shorter book replaces a longer one.
"""
from __future__ import annotations

from types import SimpleNamespace

from constants import IBKR_DEPTH_NUM_ROWS
from ibkr.depth.book import BID_SIDE, DELETE, UPDATE

ASK_SIDE = 0


def level(price: float, size: float, mm: str = "ARCA") -> tuple[float, float, str]:
    return price, size, mm


def dom_ticks(bids=(), asks=()) -> list[SimpleNamespace]:
    ticks: list[SimpleNamespace] = []
    for side, levels in ((BID_SIDE, bids), (ASK_SIDE, asks)):
        levels = [lv if len(lv) == 3 else (*lv, "ARCA") for lv in levels]
        for position, (price, size, mm) in enumerate(levels):
            ticks.append(SimpleNamespace(position=position, marketMaker=mm, operation=UPDATE,
                                         side=side, price=price, size=size))
        for position in reversed(range(len(levels), IBKR_DEPTH_NUM_ROWS)):
            ticks.append(SimpleNamespace(position=position, marketMaker="", operation=DELETE,
                                         side=side, price=0.0, size=0.0))
    return ticks


def depth_ticker(bids=(), asks=()) -> SimpleNamespace:
    """A ticker update carrying the row operations that set this book."""
    return SimpleNamespace(domTicks=dom_ticks(bids, asks))
