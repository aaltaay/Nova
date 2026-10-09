"""IBKR order events no Nova order claims, each said in Nova's words and kept for the diagnostics row.

- **An IBKR liquidation** (execution ``liquidation`` set, or an order id below zero: IBKR's own order,
  client 0; Lean's IBKR brokerage issue 156): loud -- an ERROR line, and a Nova OS event receipt
  (``event: "ibkr_liquidation"``), once per execution.
- **A position that moved with no fill to say why**, found when a new session compares IBKR's
  positions with the last ones it reported (``ibkr.session_fills.explain``): loud the same way
  (``event: "ibkr_position_gap"``).
- **A fill sent outside Nova** (another client id: TWS, the mobile app, another API): logged.
- **An IBKR error on an order no Nova watch holds** (an order from before a restart, one placed
  outside Nova): logged. ``execution.telemetry_handlers`` used to drop these without a word.

Memory only, the last ``IBKR_UNCLAIMED_KEEP``; ``status()`` feeds ``GET /api/diagnostics``.
"""
from __future__ import annotations

import logging
import time
from collections import Counter, deque
from typing import Any

from constants_ibkr import IBKR_UNCLAIMED_KEEP

logger = logging.getLogger(__name__)

_events: deque[dict[str, Any]] = deque(maxlen=IBKR_UNCLAIMED_KEEP)
_counts: Counter[str] = Counter()
_receipted: set[str] = set()


def is_liquidation(execution: Any) -> bool:
    """IBKR liquidated it: the execution says so, or it carries IBKR's own order id (below zero)."""
    try:
        flagged = int(getattr(execution, "liquidation", 0) or 0) != 0
        order_id = int(getattr(execution, "orderId", 0) or 0)
    except (TypeError, ValueError):
        return False
    return flagged or order_id < 0


def fill_facts(fill: Any) -> dict[str, Any]:
    execution = getattr(fill, "execution", None)
    when = getattr(execution, "time", None)
    return {
        "symbol": str(getattr(getattr(fill, "contract", None), "symbol", "") or "").upper() or None,
        "side": str(getattr(execution, "side", "") or "") or None,
        "shares": getattr(execution, "shares", None),
        "price": getattr(execution, "price", None),
        "exec_id": str(getattr(execution, "execId", "") or "") or None,
        "order_id": getattr(execution, "orderId", None),
        "perm_id": getattr(execution, "permId", None),
        "client_id": getattr(execution, "clientId", None),
        "account": str(getattr(execution, "acctNumber", "") or "") or None,
        "order_ref": str(getattr(execution, "orderRef", "") or "") or None,
        "time": when.isoformat() if hasattr(when, "isoformat") else (str(when) if when else None),
    }


def _keep(kind: str, facts: dict[str, Any]) -> dict[str, Any]:
    event = {"kind": kind, "ts": time.time(), **facts}
    _events.append(event)
    _counts[kind] += 1
    return event


def _receipt(event_name: str, key: str, payload: dict[str, Any]) -> None:
    """One Nova OS event receipt per key, written off the IB loop (``persist_queue``)."""
    if key in _receipted:
        return
    _receipted.add(key)

    def _write() -> None:
        from nova_os.events import KIND_SYSTEM, record_receipt

        record_receipt(kind=KIND_SYSTEM, symbol=payload.get("symbol"), payload={"event": event_name, **payload})

    try:
        from execution import persist_queue

        persist_queue.submit(f"{event_name} {key}", _write)
    except Exception:
        logger.exception("IBKR unclaimed: the %s receipt for %s could not be queued", event_name, key)


def note_liquidation(fill: Any) -> None:
    facts = fill_facts(fill)
    if facts["exec_id"] in _receipted:
        return
    _keep("liquidation", facts)
    logger.error(
        "IBKR LIQUIDATED %s: %s %s @ %s (execution %s, %s) -- an order IBKR placed, not Nova",
        facts["symbol"], facts["side"], facts["shares"], facts["price"], facts["exec_id"], facts["time"],
    )
    _receipt("ibkr_liquidation", str(facts["exec_id"]), facts)


def note_outside_fill(fill: Any) -> None:
    facts = fill_facts(fill)
    _keep("outside_fill", facts)
    logger.info(
        "IBKR: a fill Nova did not send -- %s %s %s @ %s (client %s, order %s, execution %s)",
        facts["symbol"], facts["side"], facts["shares"], facts["price"], facts["client_id"],
        facts["order_id"], facts["exec_id"],
    )


def note_order_error(order_id: int, code: int, message: str) -> None:
    _keep("order_error", {"order_id": order_id, "code": code, "message": message})
    logger.warning(
        "IBKR Error %s on order %s, which no Nova order is watching: %s", code, order_id, message or "(no text)",
    )


def note_position_gap(gap: dict[str, Any]) -> None:
    _keep("position_gap", dict(gap))
    logger.error(
        "IBKR position moved with no fill to explain it: %s %s was %s, now %s; fills Nova read account "
        "for %s, leaving %s unexplained",
        gap.get("account"), gap.get("symbol"), gap.get("before"), gap.get("after"), gap.get("by_fills"),
        gap.get("unexplained"),
    )
    key = f"{gap.get('account')}:{gap.get('symbol')}:{gap.get('before')}:{gap.get('after')}"
    _receipt("ibkr_position_gap", key, dict(gap))


def status() -> dict[str, Any]:
    """What the diagnostics row shows: counts by kind and the newest events, newest first."""
    return {"counts": dict(_counts), "events": list(reversed(_events))}


def reset_for_tests() -> None:
    _events.clear()
    _counts.clear()
    _receipted.clear()
