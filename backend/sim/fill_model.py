"""Practice fill rules for a replayed session. Pure; every fill is an estimate.

A replay has no queue and, for historical downloads, no bid/ask, so a practice
fill is inferred -- never read from the tape. `architecture/practice-fills.md`
is the contract; `tests/test_sim_fill_model.py` pins each rule.
"""
from __future__ import annotations

from dataclasses import dataclass

BASIS_QUOTE = "quote"
BASIS_LAST_PRINT = "last_print"
BASIS_PRINT_CROSS = "print_cross"
BASIS_STOP_TRIGGER = "stop_trigger"
BASIS_LAST_MARK = "last_mark"

SUPPORTED_ORDER_TYPES = ("MKT", "LMT", "STP")


@dataclass(frozen=True)
class Reference:
    """The replay's market at the playhead; any field may be unknown."""

    last: float | None
    bid: float | None = None
    ask: float | None = None


@dataclass(frozen=True)
class Fill:
    price: float
    basis: str


def at_placement(
    side: str,
    order_type: str,
    ref: Reference,
    *,
    limit: float | None = None,
    stop: float | None = None,
) -> Fill | None:
    """Fill decided when the order arrives, or ``None`` to rest it."""
    buy = side.upper() == "BUY"
    quoted = ref.ask if buy else ref.bid
    touch = quoted if quoted is not None else ref.last
    if touch is None:
        return None
    basis = BASIS_QUOTE if quoted is not None else BASIS_LAST_PRINT
    typ = order_type.upper()
    if typ == "MKT":
        return Fill(touch, basis)
    if typ == "LMT" and limit is not None:
        if (buy and touch <= limit) or (not buy and touch >= limit):
            return Fill(touch, basis)
        return None
    if typ == "STP" and stop is not None and ref.last is not None:
        if (buy and ref.last >= stop) or (not buy and ref.last <= stop):
            return Fill(touch, BASIS_STOP_TRIGGER)
    return None


def on_print(
    side: str,
    order_type: str,
    price: float,
    *,
    limit: float | None = None,
    stop: float | None = None,
) -> Fill | None:
    """Fill a resting order against one later print, or ``None``."""
    buy = side.upper() == "BUY"
    typ = order_type.upper()
    if typ == "LMT" and limit is not None:
        if (buy and price <= limit) or (not buy and price >= limit):
            return Fill(limit, BASIS_PRINT_CROSS)
    if typ == "STP" and stop is not None:
        if (buy and price >= stop) or (not buy and price <= stop):
            return Fill(price, BASIS_STOP_TRIGGER)
    return None
