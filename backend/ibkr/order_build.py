"""Pure IBKR order-type normalize / validate / construct (no broker I/O).

Owner: ibkr.orders.place_order + execution.validate.
Invalidation: none -- stateless.
"""
from __future__ import annotations

from typing import Literal

OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MKT", "LMT", "STP", "STP LMT", "TRAIL"]
PLACEABLE_ORDER_TYPES: tuple[str, ...] = ("MKT", "LMT", "STP", "STP LMT", "TRAIL")

_TYPE_ALIASES = {
    "MKT": "MKT",
    "MARKET": "MKT",
    "LMT": "LMT",
    "LIMIT": "LMT",
    "STP": "STP",
    "STOP": "STP",
    "STPLMT": "STP LMT",
    "STOPLIMIT": "STP LMT",
    "TRAIL": "TRAIL",
    "TRAILSTOP": "TRAIL",
    "TRAILINGSTOP": "TRAIL",
}


def normalize_order_type(raw: str | None) -> str:
    """Map ticket / API aliases onto IBKR wire types (STP LMT keeps the space)."""
    compact = "".join(ch for ch in str(raw or "").strip().upper() if ch.isalnum())
    return _TYPE_ALIASES.get(compact, str(raw or "").strip().upper())


def validation_error(
    side: str,
    qty: float,
    order_type: str,
    limit_price: float | None,
    stop_price: float | None,
    _outside_rth: bool,
) -> str | None:
    if side not in ("BUY", "SELL"):
        return "side must be BUY or SELL"
    if qty <= 0:
        return "qty must be greater than zero"
    typ = normalize_order_type(order_type)
    if typ not in PLACEABLE_ORDER_TYPES:
        return "order_type must be MKT, LMT, STP, STP LMT, or TRAIL"
    if typ in ("LMT", "STP LMT") and (limit_price is None or limit_price <= 0):
        return f"limit_price must be greater than zero for {typ}"
    if typ in ("STP", "STP LMT") and (stop_price is None or stop_price <= 0):
        return f"stop_price must be greater than zero for {typ}"
    if typ == "TRAIL" and (stop_price is None or stop_price <= 0):
        return "stop_price must be greater than zero for TRAIL (trail $)"
    # MKT / LMT / STP / STP LMT / TRAIL all forward outside_rth. IBKR may
    # reject or ignore (Error 2109) some combinations -- surface that after Place.
    return None


def build_ib_order(
    side: OrderSide,
    qty: float,
    order_type: OrderType | str,
    limit_price: float | None,
    stop_price: float | None,
    outside_rth: bool,
):
    from ib_async import LimitOrder, MarketOrder, Order, StopLimitOrder, StopOrder
    from constants import IBKR_ORDER_TIF_DEFAULT

    tif = IBKR_ORDER_TIF_DEFAULT
    typ = normalize_order_type(order_type)
    eh = bool(outside_rth)
    if typ == "MKT":
        return MarketOrder(side, qty, outsideRth=eh, tif=tif)
    if typ == "LMT":
        return LimitOrder(side, qty, limit_price, outsideRth=eh, tif=tif)
    if typ == "STP":
        return StopOrder(side, qty, stop_price, outsideRth=eh, tif=tif)
    if typ == "STP LMT":
        return StopLimitOrder(
            side, qty, limit_price, stop_price, outsideRth=eh, tif=tif,
        )
    if typ == "TRAIL":
        return Order(
            orderType="TRAIL",
            action=side,
            totalQuantity=qty,
            auxPrice=float(stop_price),
            outsideRth=eh,
            tif=tif,
        )
    raise ValueError(f"unsupported order_type: {order_type}")
