"""A trade that sells in two halves (#681, #845): which half filled where, and what the whole trade made.

The operator's material sells half at target 1 and the rest at target 2, the stop left where it is after
the first half. A trade carries ``target2`` (null: every share at target 1, as before two halves) and
``target1_fraction``; ``split`` turns them into the shares each half sells, the way the execution door
checks them (``execution.exit_oco.split``). Every exit the trade makes is booked in ``halves`` -- one row
per sale, ``{leg, qty, price, ts, order_id}``, ``leg`` one of ``target1`` / ``target2`` / ``stop`` / ``time``
/ ``flush`` / ``outside`` / ``handed`` -- so the trade record says which half sold where, and its exit price
and R count every share (``result``). Nova's bot and Nova's exit (``stock_mode.exit_trade``) keep the same
rows. Pure over the trade dict; the callers read the orders and save the trade.
"""
from __future__ import annotations

from typing import Any

from execution.exit_oco import split as _split

_EPS = 1e-9
# A trade's resting exits: the key of each order id, and the leg it books as.
TARGET_LEGS = (("target_order_id", "target1"), ("target2_order_id", "target2"))


def short(trade: dict[str, Any]) -> bool:
    return trade.get("side") == "short"


def split(trade: dict[str, Any], qty: Any = None, *, target1_key: str = "target1") -> tuple[int, int]:
    """``(first half, second half)`` for the trade's ``qty`` (or ``qty``); second 0: all at target 1."""
    return _split(trade.get("qty") if qty is None else qty, trade.get(target1_key), trade.get("target2"),
                  trade.get("target1_fraction"), short=short(trade))


def rows(trade: dict[str, Any]) -> list[dict[str, Any]]:
    return [h for h in trade.get("halves") or [] if isinstance(h, dict)]


def booked(trade: dict[str, Any], order_id: Any) -> bool:
    """An exit order whose sale is already in ``halves``."""
    if order_id is None:
        return False
    return any(h.get("order_id") is not None and int(h["order_id"]) == int(order_id) for h in rows(trade))


def book(trade: dict[str, Any], leg: str, qty: float, price: float | None, ts: float,
         order_id: Any = None) -> dict[str, Any]:
    """Book one sale (a cover, on a short) of ``qty`` shares at ``price`` (None: unknown)."""
    row = {"leg": leg, "qty": float(qty), "price": None if price is None else float(price), "ts": float(ts),
           "order_id": None if order_id is None else int(order_id)}
    trade.setdefault("halves", []).append(row)
    return row


def sold(trade: dict[str, Any]) -> float:
    return sum(float(h.get("qty") or 0) for h in rows(trade))


def result(trade: dict[str, Any], fill: Any, risk: Any = None) -> tuple[float | None, float | None, float | None]:
    """``(exit price, R, dollars)`` over every booked sale: the shares-weighted price, R in the trade's risk a
    share (None when ``risk`` is not over zero) and the gross dollars. None while any sale's price is unknown."""
    sales = rows(trade)
    shares = sum(float(h.get("qty") or 0) for h in sales)
    if not sales or shares <= _EPS or fill is None or any(h.get("price") is None for h in sales):
        return None, None, None
    entry = float(fill)
    gain = sum(float(h["qty"]) * ((entry - float(h["price"])) if short(trade) else (float(h["price"]) - entry))
               for h in sales)
    price = sum(float(h["qty"]) * float(h["price"]) for h in sales) / shares
    r = round(gain / (shares * float(risk)), 3) if risk is not None and float(risk) > 0 else None
    return round(price, 4), r, round(gain, 2)


def words(trade: dict[str, Any]) -> str:
    """``target 1 10.30 x 50, stop 9.89 x 50`` -- where each part of the trade sold."""
    names = {"target1": "target 1", "target2": "target 2"}
    out = []
    for h in rows(trade):
        at = f" {float(h['price']):g}" if h.get("price") is not None else ""
        out.append(f"{names.get(str(h.get('leg')), h.get('leg'))}{at} x {float(h.get('qty') or 0):g}")
    return ", ".join(out)
