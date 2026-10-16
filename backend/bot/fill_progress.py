"""A bot order's fill, as the bot audit stream carries it: the ``fill`` block, and when a working order has
filled more shares than were last said (a ``partial`` line, operator ask 2026-10-16).

Owner: the filled shares last said for each working bot order, in memory, keyed by the order id and the
venue row's own placed stamp (a Sim rewind can hand an id out again). Invalidation: a mark is dropped when
its order ends (``forget``); a process start forgets every mark, so an order still working that had filled
part before the start is said once more, with the same numbers. Shapes: architecture/schema/bot.md, "Fills on
the bot audit stream".
"""
from __future__ import annotations

from typing import Any

_EPS = 1e-9
_said: dict[tuple[int, str], float] = {}


def reset_for_tests() -> None:
    _said.clear()


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _key(order_id: int, row: dict[str, Any]) -> tuple[int, str]:
    placed = row.get("entered_ts") or row.get("submitted_at") or row.get("placed_ts") or ""
    return int(order_id), str(placed)


def block(row: dict[str, Any] | None, *, phase: str, leg: str, order_id: Any) -> dict[str, Any]:
    """``{phase, leg, order_id, qty, filled_qty, remaining_qty, avg_fill_price, status}`` from the venue's row."""
    row = row or {}
    qty = _num(row.get("qty"))
    filled = _num(row.get("filled_qty")) or 0.0
    remaining = _num(row.get("remaining_qty"))
    if remaining is None and qty is not None:
        remaining = max(qty - filled, 0.0)
    return {"phase": phase, "leg": leg, "order_id": None if order_id is None else int(order_id), "qty": qty,
            "filled_qty": filled, "remaining_qty": remaining, "avg_fill_price": _num(row.get("avg_fill_price")),
            "status": row.get("status")}


def partial(row: dict[str, Any] | None, *, phase: str, leg: str, order_id: Any) -> dict[str, Any] | None:
    """The fill block when this working order has filled more shares than were last said, else None. The caller
    passes only a row its venue reads as working."""
    if row is None or order_id is None:
        return None
    filled = _num(row.get("filled_qty")) or 0.0
    key = _key(order_id, row)
    if filled <= _said.get(key, 0.0) + _EPS:
        return None
    _said[key] = filled
    return block(row, phase=phase, leg=leg, order_id=order_id)


def forget(order_id: Any) -> None:
    """The order ended: its marks go."""
    if order_id is None:
        return
    oid = int(order_id)
    for key in [k for k in _said if k[0] == oid]:
        del _said[key]


def words(fill: dict[str, Any], symbol: str, verb: str) -> str:
    """"bought 40 of 100 PLTR at 25.1, 60 still working"."""
    price = fill.get("avg_fill_price")
    at = f" at {price:g}" if price is not None else ""
    qty = fill.get("qty")
    of = f" of {qty:g}" if qty is not None else ""
    left = fill.get("remaining_qty")
    rest = f", {left:g} still working" if left is not None else ""
    return f"{verb} {fill['filled_qty']:g}{of} {symbol}{at}{rest}"
