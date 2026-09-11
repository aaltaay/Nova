"""In-flight position commitments for the ADR 007 position gates.

``long_qty`` / ``short_qty`` only move when a fill lands, so two commands that
validate before either one fills both see the whole position as available.
This module records what is already on the wire so the second one is refused.

Owner: ``execution.service`` — commits under ``service._lock`` immediately
before the broker send, so a command validating in the same process cannot
spend the same shares twice.

Invalidation: released when the send fails, when the broker reports the order
terminal (Filled / Cancelled / ApiCancelled / Inactive), or on
``reset_for_tests``. A still-working order keeps its commitment on purpose —
the position it will consume is still unsold.

Not persisted (no ``schema_version``): a commitment is only meaningful for the
process that placed the order. The durable half is the ledger's ``boot_id``;
``execution.startup_sweep`` reconciles rows a previous process left behind.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

_lock = threading.RLock()


@dataclass
class Commitment:
    execution_id: str
    symbol: str
    side: str
    qty: float
    order_id: int | None = None
    created_ts: float = field(default_factory=time.time)


_commitments: dict[str, Commitment] = {}

__all__ = [
    "Commitment", "attach_order", "commit", "committed_qty",
    "release_execution", "release_on_broker_status", "release_order",
    "reset_for_tests", "snapshot",
]


def _normalize(symbol: str | None, side: str | None) -> tuple[str, str]:
    return (symbol or "").strip().upper(), (side or "").strip().upper()


def commit(
    execution_id: str,
    *,
    symbol: str | None,
    side: str | None,
    qty: float | None,
) -> None:
    """Record ``qty`` as spent for ``symbol``/``side`` until the order resolves."""
    sym, direction = _normalize(symbol, side)
    try:
        amount = float(qty or 0)
    except (TypeError, ValueError):
        return
    if not sym or direction not in ("BUY", "SELL") or amount <= 0:
        return
    with _lock:
        _commitments[execution_id] = Commitment(
            execution_id=execution_id, symbol=sym, side=direction, qty=amount,
        )


def attach_order(execution_id: str, order_id: int | None) -> None:
    """Link the broker order id so a terminal callback can free the shares."""
    if order_id is None:
        return
    with _lock:
        row = _commitments.get(execution_id)
        if row is not None:
            row.order_id = int(order_id)


def release_execution(execution_id: str) -> bool:
    with _lock:
        return _commitments.pop(execution_id, None) is not None


def release_order(order_id: int | None) -> bool:
    if order_id is None:
        return False
    target = int(order_id)
    with _lock:
        for execution_id, row in list(_commitments.items()):
            if row.order_id == target:
                del _commitments[execution_id]
                return True
    return False


def release_on_broker_status(order_id: int | None, status: str | None) -> bool:
    """Free the commitment once the broker is done with the order.

    A false Cancelled (Error 10349) frees the shares a beat early and the
    order comes back working with no commitment. That direction is deliberate:
    a commitment stuck open would refuse a real exit.
    """
    from execution.telemetry import TERMINAL_REJECT_STATUSES

    text = str(status or "")
    if text != "Filled" and text not in TERMINAL_REJECT_STATUSES:
        return False
    return release_order(order_id)


def committed_qty(symbol: str | None, side: str | None) -> float:
    """Shares already sent for ``symbol``/``side`` and not yet resolved."""
    sym, direction = _normalize(symbol, side)
    if not sym or not direction:
        return 0.0
    with _lock:
        return sum(
            row.qty for row in _commitments.values()
            if row.symbol == sym and row.side == direction
        )


def snapshot() -> list[dict]:
    with _lock:
        return [
            {
                "execution_id": row.execution_id,
                "symbol": row.symbol,
                "side": row.side,
                "qty": row.qty,
                "order_id": row.order_id,
                "created_ts": row.created_ts,
            }
            for row in _commitments.values()
        ]


def reset_for_tests() -> None:
    with _lock:
        _commitments.clear()
