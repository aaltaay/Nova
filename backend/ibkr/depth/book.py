"""Nova's own Level 2 book, kept with IBKR's row rules (#540).

IBKR sends each side of a depth book as row operations: insert a level at row
``position`` (the rows below move down), update the level at ``position``, or
delete it (the rows below move up). ib_async 2.1.0 keeps a side in a dict
keyed by position instead: an insert overwrites the row, a delete leaves a
hole, and a row inserted after a delete lands at the end of the list. So
``ticker.domBids`` / ``domAsks`` fall out of price order and keep levels IBKR
removed -- GRML 2026-09-22 recorded 466 of 111,116 books out of order, 269 of
them with a first bid or ask that was not the best.

``DepthBook`` replays ``ticker.domTicks`` (every row operation since the last
update event) onto plain lists with IBKR's rules. Pure: no I/O, no ib_async.

IBKR can move rows by rewriting each one with its neighbour, and ib_async
hands Nova the row operations of each TCP read as it arrives
(``tcpDataProcessed``): a read that ends partway through such a move leaves
one venue's row on two rows until the next read finishes it (#1133).
``shown()`` is the book Nova shows -- each venue once at a price, as IBKR's
SMART book holds it.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

INSERT, UPDATE, DELETE = 0, 1, 2
BID_SIDE = 1  # IBKR: side 1 is the bid, 0 the ask


@dataclass(frozen=True)
class Level:
    price: float
    size: float
    mm: str = ""
    # The ``DepthBook.apply`` call that last wrote the row: which of a venue's two rows is current.
    read: int = field(default=0, compare=False)


@dataclass
class DepthBook:
    """One symbol's book: at most ``max_rows`` levels a side, in IBKR's row order."""

    max_rows: int
    bids: list[Level] = field(default_factory=list)
    asks: list[Level] = field(default_factory=list)
    reads: int = 0

    def reset(self) -> None:
        """A new subscription or an IBKR depth reset (error 317): IBKR resends the book."""
        self.bids.clear()
        self.asks.clear()

    def apply(self, ticks: Iterable[Any]) -> None:
        self.reads += 1
        for tick in ticks:
            self._apply_one(tick)

    def _apply_one(self, tick: Any) -> None:
        rows = self.bids if int(getattr(tick, "side", -1)) == BID_SIDE else self.asks
        position = int(getattr(tick, "position", -1))
        operation = int(getattr(tick, "operation", -1))
        if position < 0:
            return
        if operation == DELETE:
            if position < len(rows):
                del rows[position]
            return
        level = Level(float(tick.price), float(tick.size), str(getattr(tick, "marketMaker", "") or ""), self.reads)
        if operation == INSERT:
            rows.insert(min(position, len(rows)), level)
            del rows[self.max_rows:]  # the row pushed past the book's depth falls off
        elif operation == UPDATE:
            if position < len(rows):
                rows[position] = level
            else:
                rows.append(level)

    def in_price_order(self) -> bool:
        return is_ordered([lv.price for lv in self.bids], bid=True) and is_ordered(
            [lv.price for lv in self.asks], bid=False,
        )

    def shown(self) -> tuple[list[Level], list[Level]]:
        """The bids and asks Nova shows: the kept rows less a move IBKR has not finished.

        The kept rows stay as IBKR addresses them, so its next operations land on the right row.
        """
        return one_row_per_venue(self.bids), one_row_per_venue(self.asks)


def one_row_per_venue(rows: list[Level]) -> list[Level]:
    """``rows`` with each venue once at a price (#1133).

    A SMART book holds one row per venue per price (a price's rows go in venue order), so a venue's
    second row there is the order IBKR is moving, never a second order. Of the two, the one IBKR wrote
    last is kept -- the other still holds what the row said before; a copy is the same either way. A row
    with no venue proves nothing and is kept.
    """
    out: list[Level] = []
    seen: dict[tuple[float, str], int] = {}
    for level in rows:
        if not level.mm:
            out.append(level)
            continue
        key = (level.price, level.mm)
        at = seen.get(key)
        if at is None:
            seen[key] = len(out)
            out.append(level)
        elif level.read > out[at].read:
            out[at] = level
    return out


def is_ordered(prices: list[float], *, bid: bool) -> bool:
    """Bids best-first (descending), asks best-first (ascending); equal prices allowed."""
    pairs = zip(prices, prices[1:], strict=False)  # adjacent pairs; the shift makes lengths differ
    return all(a >= b for a, b in pairs) if bid else all(a <= b for a, b in pairs)


def sort_levels(rows: list[dict[str, Any]], *, bid: bool) -> list[dict[str, Any]]:
    """Best price first, keeping the recorded order at equal prices.

    For books recorded before #540, whose rows can be out of price order;
    a book kept by ``DepthBook`` is already in order and comes back unchanged.
    """
    def key(row: dict[str, Any]) -> float:
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            return float("inf")
        return -price if bid else price

    return sorted(rows, key=key)
