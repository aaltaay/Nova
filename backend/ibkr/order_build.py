"""Pure IBKR order-type normalize / validate / construct (no broker I/O).

Owner: ibkr.orders.place_order + execution.validate.
Invalidation: none -- stateless.
"""
from __future__ import annotations

from typing import Literal

from constants_ibkr import IBKR_ORDER_TIF_DEFAULT, IBKR_ORDER_TIFS

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


def normalize_tif(raw: str | None) -> str:
    """Upper-case a TIF; blank means the Nova default (never send blank -- 10349)."""
    text = str(raw or "").strip().upper()
    return text or IBKR_ORDER_TIF_DEFAULT


def tif_error(raw: str | None) -> str | None:
    """None when *raw* is a TIF Nova places; otherwise the refusal text."""
    if normalize_tif(raw) in IBKR_ORDER_TIFS:
        return None
    return f"tif must be one of {', '.join(IBKR_ORDER_TIFS)}"


def validation_error(
    side: str,
    qty: float,
    order_type: str,
    limit_price: float | None,
    stop_price: float | None,
    _outside_rth: bool,
    tif: str | None = None,
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
    return tif_error(tif)


def build_ib_order(
    side: OrderSide,
    qty: float,
    order_type: OrderType | str,
    limit_price: float | None,
    stop_price: float | None,
    outside_rth: bool,
    tif: str | None = None,
):
    from ib_async import LimitOrder, MarketOrder, Order, StopLimitOrder, StopOrder

    tif = normalize_tif(tif)
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
