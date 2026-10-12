"""The targets the exit sheet chose for Nova's exit (#681, #845): read, checked, split into halves, said.

``exit_trade.take`` hands Nova the exit of the shares you hold; with a ``target`` -- and a ``target2`` for
the second half -- Nova rests them beside its stop as one exit-only pair (``exit_orders.place_pair``).
This module holds the rules over the sheet's numbers, pure but for the refusal it raises:

- ``price``: a price the sheet sent, or None when it sent none;
- ``refusal``: a target that would fill at once, sits past the stop, or a target 2 not beyond target 1;
- ``apply``: the trade's target fields -- ``target1_qty`` / ``target2_qty`` from ``halves.split`` (the first
  half the smaller part of an odd count; one share, or no target 2, sells whole at target 1);
- ``words``: the targets as the timeline says them.
"""
from __future__ import annotations

from typing import Any

from bot.first_pullback import halves
from constants_stock_mode import STOCK_MODE_INVALID
from stock_mode.errors import StockModeError

_EPS = 1e-9


def price(value: Any, field: str) -> float | None:
    """A price the sheet sent, or None when it sent none; anything else is refused."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise StockModeError(STOCK_MODE_INVALID, f"the {field} is a price", status=400, field=field) from exc
    if not out > 0:
        raise StockModeError(STOCK_MODE_INVALID, f"the {field} is a price over zero", status=400, field=field)
    return out


def refusal(short: bool, stop: float, last: float | None, t1: float | None,
            t2: float | None) -> StockModeError | None:
    """A target that would fill at once (at or through the last price), sits past the stop, or a second
    target not beyond the first."""
    if t1 is None:
        return None if t2 is None else StockModeError(STOCK_MODE_INVALID, "target 2 needs a target 1 beside it",
                                                      field="target")
    side = "under" if short else "over"
    if (t1 >= stop - _EPS) if short else (t1 <= stop + _EPS):
        return StockModeError(STOCK_MODE_INVALID, f"target 1 {t1:.2f} must be {side} the stop {stop:.2f}",
                              field="target")
    if last is not None and ((t1 >= last - _EPS) if short else (t1 <= last + _EPS)):
        return StockModeError(STOCK_MODE_INVALID, f"target 1 {t1:.2f} is not {side} the last price {last:.2f}: it "
                              f"would {'cover' if short else 'sell'} at once", field="target")
    if t2 is not None and ((t2 >= t1 - _EPS) if short else (t2 <= t1 + _EPS)):
        return StockModeError(STOCK_MODE_INVALID, f"target 2 {t2:.2f} must be {side} target 1 {t1:.2f}",
                              field="target2")
    return None


def apply(trade: dict[str, Any], t1: float | None, t2: float | None, fraction: Any) -> None:
    """Set the trade's targets: ``target``, ``target2`` (None when every share sells at target 1),
    ``target1_fraction`` and the shares each half sells."""
    trade.update(target=round(t1, 4) if t1 is not None else None, target2=round(t2, 4) if t2 is not None else None,
                 target1_fraction=fraction, target1_qty=None, target2_qty=None)
    if t1 is None:
        trade["target2"] = None
        return
    first, second = halves.split(trade, target1_key="target")
    trade.update(target1_qty=first, target2_qty=second)
    if not second:
        trade["target2"] = None             # one share, or no target 2: every share at target 1


def words(trade: dict[str, Any]) -> str:
    """``target 10.30 for every share``, or ``target 1 10.30 for 50, target 2 10.50 for 50``."""
    if trade.get("target2"):
        return (f"target 1 {float(trade['target']):.2f} for {trade['target1_qty']}, target 2 "
                f"{float(trade['target2']):.2f} for {trade['target2_qty']}")
    return f"target {float(trade['target']):.2f} for every share"
