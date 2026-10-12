"""The resting exits of a trade Nova holds the exit of, read each tick (#681, #845): which filled, booked in halves.

Nova's exit (``exit_trade``) and an approved bracket (``runner``) rest the same legs -- target 1 for the first
half, target 2 for the rest, the stop for every share still held -- and read them the same way, so one rule
books them: a leg that filled since the last tick is booked in ``halves`` (``bot.first_pullback.halves``) with
its fill price (the leg's own price when the row has none) and its filled shares (the shares left when the row
has none). A target that sold part of the trade is a half: the broker shrinks the stop to the shares left and
the stop stays where it is. The stop, or a target that sold the last shares, ends the trade. The callers say
it and save the trade; a row Nova cannot read raises ``orders.ReadError`` -- never "not filled".
"""
from __future__ import annotations

from typing import Any

from bot.first_pullback import halves
from stock_mode import orders

_EPS = 1e-9
# Each resting exit: the trade's key for its order id, the reason it closes with, and the leg it books as.
LEGS = (("target_order_id", "target", "target1"), ("target2_order_id", "target", "target2"),
        ("stop_order_id", "stop", "stop"))


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def book_fills(trade: dict[str, Any], now: float) -> tuple[list[tuple[str, float, float, float]],
                                                          tuple[str, float] | None]:
    """``(halves sold, done)``: each first half booked now as ``(leg, shares, price, shares left)``, and
    ``(reason, price)`` when the stop -- or the target that sold the last shares -- ended the trade."""
    left = float(trade["qty"]) - halves.sold(trade)
    sold_now: list[tuple[str, float, float, float]] = []
    for leg, reason, name in LEGS:
        if not trade.get(leg) or halves.booked(trade, trade[leg]):
            continue
        row = orders.order_row(trade[leg]) or {}
        if orders.order_state(row) != "filled":
            continue
        price = _num(row.get("avg_fill_price")) or float(trade["target" if name == "target1" else name])
        sold = float(row.get("filled_qty") or 0) or left
        halves.book(trade, name, sold, price, now, trade[leg])
        left -= sold
        if reason == "stop" or left <= _EPS:
            return sold_now, (reason, price)
        sold_now.append((name, sold, price, left))
    return sold_now, None


def resting(trade: dict[str, Any]) -> list[str]:
    """The trade's exit legs that still hold an order Nova has not booked (a sold half is done)."""
    return [leg for leg, _reason, _name in LEGS if trade.get(leg) and not halves.booked(trade, trade[leg])]
