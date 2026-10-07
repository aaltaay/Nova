"""IBKR's own book -- its positions and working orders -- whatever the desk shows.

``ibkr.account`` and ``ibkr.orders`` answer for the desk's venue: on Paper and Sim they read
the practice ledger (ADR 020). The few callers that act on Live while the desk may show
another venue read IBKR itself here: the kill switch's sweep (#656) and Nova's Live day
cover (ADR 048 step 6) with the execution door's check of it. A read before the session is
ready raises ``IbkrAccountError`` -- never "flat", never "nothing working".

Memory reads of the IB instance's own state; nothing is asked of IBKR.
"""
from __future__ import annotations

from typing import Any

from ibkr import client as _client
from ibkr.errors import IbkrAccountError


def _ib() -> Any:
    ib = _client.get_ib()
    if ib is None:
        raise IbkrAccountError(f"{_client.unavailable_detail('IBKR')} -- IBKR's own book cannot be read")
    return ib


def positions() -> dict[str, float]:
    """``{SYMBOL: signed qty}`` IBKR holds: a short is negative."""
    held: dict[str, float] = {}
    for pos in _ib().positions():
        symbol = str(pos.contract.symbol or "").strip().upper()
        held[symbol] = held.get(symbol, 0.0) + float(pos.position or 0)
    return held


def open_rows() -> list[dict[str, Any]]:
    """IBKR's working orders as order rows (``ibkr.order_rows``)."""
    from ibkr.order_rows import trade_to_order_row

    return [trade_to_order_row(trade) for trade in _ib().openTrades()]


def order_state(order_id: int) -> dict[str, Any] | None:
    """IBKR's status of order ``order_id`` this session -- ``{status, filled, remaining}`` -- or None when the
    session does not know it (placed before a reconnect)."""
    for trade in _ib().trades():
        if int(getattr(trade.order, "orderId", 0) or 0) == int(order_id):
            st = trade.orderStatus
            return {"status": str(st.status or ""), "filled": float(st.filled or 0),
                    "remaining": float(st.remaining or 0)}
    return None


def account_summary() -> dict[str, Any]:
    """IBKR's account values as the summary ``ibkr.account`` builds on Live (its ``account_class`` stamps
    included); ``pending`` until IBKR has sent the net liquidation."""
    from ibkr.account_summary import summary_from_items

    summary = summary_from_items(list(_ib().accountValues()), mode=_client.account_mode())
    if "NetLiquidation" not in summary:
        summary["pending"] = True
    return summary
