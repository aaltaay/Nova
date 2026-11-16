"""Your close of a handed position (ADR 072 decision 5, ``traders.md`` "Handed to you and closed by you").

A close of yours that reaches past your own shares into ones handed to you first cancels the handed trader's resting
exits in that stock -- its stop and targets would otherwise sell shares that are being sold under them -- then the
fill sells your own shares first and the handed ones after (``owners.split``). The cancels are the practice broker's
own (source ``cancel_working``, code ``TAKEOVER``), made inside the order's placement: an ``execution`` call from here
would wait on the door's lock this order already holds. Asked by ``practice.broker`` once the rules have passed.
"""
from __future__ import annotations

import logging
from typing import Any

from constants_owners import HOLDER_YOU, TAKEOVER_CODE

logger = logging.getLogger(__name__)
_EPS = 1e-9


def _exit(row: dict[str, Any]) -> bool:
    return row.get("effect") == "closes" or row.get("parent_id") is not None or row.get("leg_role") in ("target", "stop")


def before_close(broker: Any, symbol: str, side: str, qty: float, *, source: str | None, origin: str | None,
                 bot_id: str | None) -> list[int]:
    """Cancel the handed trader's resting exits in ``symbol`` when your close reaches its shares; the ids cancelled."""
    from owners.rules import handed_from
    from owners.whose import book_of, holder_of, holder_of_order

    ledger = broker.ledger
    owners = getattr(ledger, "owners", None)
    if owners is None or holder_of_order(source, origin, bot_id) != HOLDER_YOU:
        return []
    own = owners.qty_of(symbol, HOLDER_YOU)
    closing = (side == "SELL" and own > -_EPS) or (side == "BUY" and own < _EPS)
    giver = handed_from(ledger, symbol)
    if giver is None or not closing or float(qty) <= abs(own) + _EPS:
        return []
    cancelled = []
    for row in list(ledger.working_orders()):
        if (str(row.get("symbol") or "").upper() == symbol and book_of(holder_of(row)) == giver and _exit(row)):
            answer = broker.cancel(int(row["order_id"]), source="cancel_working", code=TAKEOVER_CODE,
                                   reason=f"Cancelled before your close of the {symbol} handed to you")
            if answer.get("ok"):
                cancelled.append(int(row["order_id"]))
            else:
                logger.warning("OWNERS: %s's exit %s on %s could not be cancelled before your close: %s",
                               giver, row["order_id"], symbol, answer.get("error"))
    if cancelled:
        logger.info("OWNERS: your close of %s reached %s's handed shares: its exits %s cancelled", symbol, giver,
                    cancelled)
    return cancelled
