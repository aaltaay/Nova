"""Who sent an order, read from this desk's execution rows (operator report 2026-10-01; #677).

A practice row stamps its own ``order_source`` / ``order_origin`` when it is placed
(``practice.broker``). A Live row comes from IBKR and carries neither: it is joined here to
the execution row Nova wrote when it sent the order -- by permId, else by order id -- and only
when the symbols agree. A bracket's exit legs (``target_order_id`` / ``stop_order_id``) have
ids of their own and share their entry's sender. A row no execution row claims gets no
sender (the desk says it is not recorded): an id alone is never read as Nova's.
"""
from __future__ import annotations

import logging
from typing import Any

from execution import order_side

logger = logging.getLogger(__name__)

_LEG_ID_KEYS = ("order_id", "parent_order_id", "target_order_id", "stop_order_id")


def ledger_sent_by(led: dict[str, Any], side: str | None = None) -> dict[str, Any]:
    """The sender fields of one execution row: the ADR 007 source, the part of Nova (origin), and
    whether the order row is a short entry Nova sent (ADR 048: Fill now never re-sends one as a
    plain SELL).

    ``side`` is the order row's own: a bracket's exits share their entry's execution row, and the
    exits of a short bracket are BUYs that cover -- so only a SELL row is the short entry itself.
    """
    payload = led.get("payload") or {}
    row_side = str(side or payload.get("side") or "").strip().upper()
    position_side, effect = order_side.from_record(payload, row_side, str(led.get("operation") or ""))
    return {
        "order_source": led.get("source"),
        "order_origin": payload.get("origin"),
        "short_entry": bool(payload.get("short_entry")) and row_side == "SELL",
        "position_side": position_side,
        "effect": effect,
    }


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _symbol(row: dict[str, Any]) -> str:
    return str(row.get("symbol") or "").strip().upper()


def sent_by_index(ledger_rows: list[dict[str, Any]] | None) -> dict[tuple[str, int], dict[str, Any]]:
    """``("perm" | "order", id) -> execution row`` for every id an execution row placed under.

    ``ledger_rows`` must already be this desk's (``closed_blotter.ledger_rows_for_desk``): order
    ids restart per venue, so another venue's row must never be in the index. The first row
    recorded for an id keeps it.
    """
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for led in ledger_rows or []:
        if str(led.get("operation") or "") not in ("place", "bracket"):
            continue
        perm = _as_int(led.get("perm_id"))
        if perm > 0:
            index.setdefault(("perm", perm), led)
        for key in _LEG_ID_KEYS:
            oid = _as_int(led.get(key))
            if oid > 0:
                index.setdefault(("order", oid), led)
    return index


def lookup(index: dict[tuple[str, int], dict[str, Any]], row: dict[str, Any]) -> dict[str, Any] | None:
    """The execution row that sent ``row`` (an IBKR order row), or None."""
    symbol = _symbol(row)
    for key in (("perm", _as_int(row.get("perm_id"))), ("order", _as_int(row.get("order_id")))):
        if key[1] <= 0:
            continue
        led = index.get(key)
        if led is not None and _symbol(led) == symbol:
            return led
    return None


def attach_sent_by(rows: list[dict[str, Any]], ledger_rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Copies of ``rows``; a row with no sender of its own takes its execution row's.

    A row that already carries ``order_source`` (a practice row) keeps its own stamp.
    """
    index = sent_by_index(ledger_rows)
    out: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        if "order_source" not in copy:
            led = lookup(index, copy)
            if led is not None:
                copy.update(ledger_sent_by(led, copy.get("side")))
        out.append(copy)
    return out
