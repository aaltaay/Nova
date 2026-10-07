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

A commitment belongs to the venue the order was sent on (Live, Paper or Sim): a
Paper sell still working must not refuse a Live exit of the same stock, and an
order id means nothing across venues (practice ids restart at 1 per venue).
``committed_qty`` / ``release_order`` / ``snapshot`` answer for one venue.

A short entry is committed as ``SHORT`` (ADR 048), never as ``SELL``: it spends no long, so
it must not shrink what a closing SELL may sell, while the borrow and margin checks of the next
short count it (``committed_qty(symbol, SHORT)``, ``commitments(SHORT)``, priced at the order's
limit).

Not persisted (no ``schema_version``): a commitment is only meaningful for the
process that placed the order. The durable half is the ledger's ``boot_id``;
``execution.startup_sweep`` reconciles rows a previous process left behind.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

_lock = threading.RLock()


# A short-opening SELL's side key (ADR 048): kept apart from SELL, which spends a long.
SHORT = "SHORT"
_SIDES = ("BUY", "SELL", SHORT)


@dataclass
class Commitment:
    execution_id: str
    symbol: str
    side: str
    qty: float
    order_id: int | None = None
    venue: str | None = None
    created_ts: float = field(default_factory=time.time)
    price: float | None = None    # the order's limit, when it has one (a short's margin reads it)


_commitments: dict[str, Commitment] = {}

__all__ = [
    "SHORT", "Commitment", "attach_order", "commit", "commitments", "committed_qty",
    "release_execution", "release_on_broker_status", "release_order",
    "reset_for_tests", "snapshot",
]


def _normalize(symbol: str | None, side: str | None) -> tuple[str, str]:
    return (symbol or "").strip().upper(), (side or "").strip().upper()


def _venue(venue: str | None) -> str | None:
    """``venue``, else the desk's now (the execution door passes the one it sends on)."""
    if venue is not None:
        return venue
    from sim.mode import venue as desk_venue

    return desk_venue()


def commit(
    execution_id: str,
    *,
    symbol: str | None,
    side: str | None,
    qty: float | None,
    venue: str | None = None,
    price: float | None = None,
) -> None:
    """Record ``qty`` as spent for ``symbol``/``side`` (``BUY``, ``SELL`` or ``SHORT``) until the order resolves."""
    sym, direction = _normalize(symbol, side)
    try:
        amount = float(qty or 0)
    except (TypeError, ValueError):
        return
    if not sym or direction not in _SIDES or amount <= 0:
        return
    try:
        limit = float(price) if price is not None else None
    except (TypeError, ValueError):
        limit = None
    with _lock:
        _commitments[execution_id] = Commitment(
            execution_id=execution_id, symbol=sym, side=direction, qty=amount, venue=_venue(venue),
            price=limit,
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


def release_order(order_id: int | None, venue: str | None = None) -> bool:
    """Free the commitment of ``order_id`` on ``venue`` (the desk's when not given).

    IBKR's callbacks pass ``"live"`` -- only Live sends to IBKR -- and a practice broker's
    notices pass their own venue, so one venue's order N never frees another's."""
    if order_id is None:
        return False
    target = int(order_id)
    where = _venue(venue)
    with _lock:
        for execution_id, row in list(_commitments.items()):
            if row.order_id == target and row.venue == where:
                del _commitments[execution_id]
                return True
    return False


def release_on_broker_status(order_id: int | None, status: str | None, venue: str | None = "live") -> bool:
    """Free the commitment once the broker is done with the order.

    A false Cancelled (Error 10349) frees the shares a beat early and the
    order comes back working with no commitment. That direction is deliberate:
    a commitment stuck open would refuse a real exit.
    """
    from execution.telemetry import TERMINAL_REJECT_STATUSES

    text = str(status or "")
    if text != "Filled" and text not in TERMINAL_REJECT_STATUSES:
        return False
    return release_order(order_id, venue)


def committed_qty(symbol: str | None, side: str | None, venue: str | None = None) -> float:
    """Shares already sent for ``symbol``/``side`` on ``venue`` (the desk's) and not yet resolved."""
    sym, direction = _normalize(symbol, side)
    if not sym or not direction:
        return 0.0
    where = _venue(venue)
    with _lock:
        return sum(
            row.qty for row in _commitments.values()
            if row.symbol == sym and row.side == direction and row.venue == where
        )


def commitments(side: str, venue: str | None = None) -> list[Commitment]:
    """Copies of every commitment on ``side`` on ``venue`` (the desk's): ``SHORT`` for the shorts in flight."""
    direction = (side or "").strip().upper()
    where = _venue(venue)
    with _lock:
        return [
            Commitment(**{**row.__dict__}) for row in _commitments.values()
            if row.side == direction and row.venue == where
        ]


def snapshot(venue: str | None = None, *, all_venues: bool = False) -> list[dict]:
    """The commitments of ``venue`` (the desk's), or of every venue with ``all_venues``."""
    where = None if all_venues else _venue(venue)
    with _lock:
        return [
            {
                "execution_id": row.execution_id,
                "symbol": row.symbol,
                "side": row.side,
                "qty": row.qty,
                "order_id": row.order_id,
                "venue": row.venue,
                "created_ts": row.created_ts,
            }
            for row in _commitments.values()
            if all_venues or row.venue == where
        ]


def reset_for_tests() -> None:
    with _lock:
        _commitments.clear()
