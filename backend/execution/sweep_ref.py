"""The sweep's evidence by Nova's reference: a Live row's order found at IBKR by its orderRef.

A Live row carries the reference it was sent with (``execution.order_ref``), written before the send.
It finds the row's order when the row has no order id -- a send Nova could not see finish
(``SEND_UNKNOWN``), or a process that stopped mid-send -- and it checks an order id the row has: an
IBKR order under that id with another reference is a different order (an id the Gateway handed out
again; Lean's IBKR brokerage issue 242), never this row's outcome.

Executions carry the reference too, so a fill proves the order reached IBKR even while completed
orders have not loaded. More than one order passing the match is ``ambiguous``: the operator decides.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from execution import order_ref, store

logger = logging.getLogger(__name__)

_SIDE_OF_EXECUTION = {"BOT": "BUY", "SLD": "SELL", "BUY": "BUY", "SELL": "SELL"}


@dataclass(frozen=True)
class Found:
    """``one`` (``order_id`` / ``perm_id``), ``none``, ``ambiguous`` (``order_ids``) or ``no_ref``."""

    verdict: str
    order_id: int | None = None
    perm_id: int | None = None
    order_ids: tuple[int, ...] = field(default_factory=tuple)


def _intent(row: dict) -> tuple[str, str, float | None]:
    """The row's symbol, entry side and the quantity it sent."""
    payload = row.get("payload") or {}
    side = str(payload.get("side") or "").upper()
    if not side and row.get("operation") == "bracket":
        side = "SELL" if payload.get("short_entry") else "BUY"
    qty = payload.get("sent_qty") if payload.get("sent_qty") is not None else payload.get("qty")
    try:
        sent = abs(float(qty)) if qty is not None else None
    except (TypeError, ValueError):
        sent = None
    return str(row.get("symbol") or "").upper(), side, sent


def find(row: dict, broker_rows: Iterable[dict], fills: Iterable[Any]) -> Found:
    """The order IBKR has under ``row``'s reference: its working / closed rows first, then executions."""
    ref = str(row.get("order_ref") or "")
    if not ref:
        return Found("no_ref")
    symbol, side, qty = _intent(row)
    perm = row.get("perm_id")
    matched = order_ref.match(broker_rows, order_ref=ref, symbol=symbol, side=side, qty=qty, perm_id=perm)
    if matched.verdict == "ambiguous":
        return Found("ambiguous", order_ids=tuple(matched.order_ids()))
    if matched.verdict == "one" and matched.row is not None:
        return Found("one", order_id=int(matched.row["order_id"]), perm_id=matched.row.get("perm_id"))
    orders: dict[int, int] = {}
    for fill in fills:
        execution = getattr(fill, "execution", None)
        if str(getattr(execution, "orderRef", "") or "") != ref:
            continue
        if str(getattr(getattr(fill, "contract", None), "symbol", "") or "").upper() not in ("", symbol):
            continue
        if _SIDE_OF_EXECUTION.get(str(getattr(execution, "side", "") or "").upper(), side) != side:
            continue
        orders[int(getattr(execution, "permId", 0) or 0)] = int(getattr(execution, "orderId", 0) or 0)
    if len(orders) > 1:
        return Found("ambiguous", order_ids=tuple(orders.values()))
    if len(orders) == 1:
        perm_id, order_id = next(iter(orders.items()))
        return Found("one", order_id=order_id, perm_id=perm_id or None)
    return Found("none")


def id_reused(row: dict, broker_row: dict | None) -> bool:
    """The broker's order under the row's id carries another reference: not this row's order."""
    ours = str(row.get("order_ref") or "")
    theirs = str((broker_row or {}).get("order_ref") or "")
    return bool(ours and theirs and theirs != ours)


def _int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, 0) else None
    except (TypeError, ValueError):
        return None


def decide(row: dict, order_id: int | None, all_rows: list[dict], fills: list) -> tuple[str, int | None]:
    """How the sweep reconciles ``row``: ``("use", id)`` by that order id; else ``ambiguous`` (more than one
    order matches: the row says so and waits for the operator), ``unknown`` (a reference or an id with no
    order to show for it) or ``never_sent`` (neither a reference nor an id)."""
    by_id = next((r for r in all_rows if order_id is not None and _int(r.get("order_id")) == order_id), None)
    if order_id is not None and not id_reused(row, by_id):
        return "use", order_id
    found = find(row, all_rows, fills)
    if found.verdict == "ambiguous":
        store.update_stages(
            str(row["id"]), reason_code=order_ref.AMBIGUOUS,
            error=(f"startup sweep: IBKR orders {', '.join(map(str, found.order_ids))} all carry this "
                   "order's reference, symbol, side and size -- Nova will not pick one; check TWS"),
        )
        logger.error("execution sweep: %s matches IBKR orders %s by reference -- left for the operator",
                     row["id"], list(found.order_ids))
        return "ambiguous", None
    if found.verdict == "one" and found.order_id:
        if found.order_id != order_id:
            order_ref.adopt(str(row["id"]), order_id=found.order_id, perm_id=found.perm_id)
        return "use", found.order_id
    if order_id is not None:
        logger.error("execution sweep: IBKR's order %s for %s carries another reference -- an id reused",
                     order_id, row["id"])
    return ("unknown" if row.get("order_ref") or order_id is not None else "never_sent"), None
