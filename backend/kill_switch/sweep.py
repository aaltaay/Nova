"""Kill-switch cancel sweep -- every venue's working orders, every cancel through the door (ADR 007).

Spec D (2026-09-30), #656: the sweep used to stop at "is IBKR connected?" and read only the desk's
venue, so on Paper with the Gateway down, or on a Sim replay, it reported nothing cancelled while
practice orders kept resting and filling. Now it reads and cancels each venue that can hold a
working order, whatever the desk shows:

- **Live** while IBKR is connected (its own open trades, never the practice ledger); otherwise it
  says so: ``"Gateway disconnected: Live orders were not swept"``.
- **Paper** always -- its ledger is local and persistent, readable with the Gateway dark.
- **Sim** when this process has a Sim scratch ledger loaded (nothing loaded holds no order).

Each cancel is a ``kill`` cancel with an explicit ``target_venue`` (``execution.venue_door``). A
read that fails is that venue's ``error`` -- never "nothing to cancel" -- and a refused cancel is
listed in ``failed`` with its reason. The sweep runs on the caller's loop (the async route), the
loop every other order runs on: it used to run ``execute`` under ``asyncio.run`` from a sync route,
a second event loop that raised "bound to a different event loop" on the door's lock whenever an
order held it (#656).

Owns no state.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from constants_sim import DESK_VENUE_LIVE, DESK_VENUE_PAPER, DESK_VENUE_SIM

logger = logging.getLogger(__name__)

LIVE_DISCONNECTED = "Gateway disconnected: Live orders were not swept"
LIVE_NOT_READY = "IBKR is still connecting (session not ready): Live orders were not swept"
SIM_NOT_LOADED = "Sim's scratch account is not open in this process, so it holds no working order."
VENUES = (DESK_VENUE_LIVE, DESK_VENUE_PAPER, DESK_VENUE_SIM)   # real money first

Rows = list[dict[str, Any]]


def _live_rows() -> tuple[Rows | None, str | None, str | None]:
    """IBKR's own working orders -- never the desk's practice ledger."""
    from ibkr import client as _client

    if not _client.is_connected():
        return None, LIVE_DISCONNECTED, None
    ib = _client.get_ib()
    if ib is None:
        return None, LIVE_NOT_READY, None
    from ibkr.order_rows import trade_to_order_row

    return [trade_to_order_row(trade) for trade in ib.openTrades()], None, None


def _paper_rows() -> tuple[Rows | None, str | None, str | None]:
    from practice.broker import for_venue

    return for_venue(DESK_VENUE_PAPER).working_orders(), None, None


def _sim_rows() -> tuple[Rows | None, str | None, str | None]:
    from practice.broker import loaded

    broker = loaded(DESK_VENUE_SIM)
    if broker is None:
        return [], None, SIM_NOT_LOADED
    return broker.working_orders(), None, None


def read_working(venue: str) -> tuple[Rows | None, str | None, str | None]:
    """``(rows, error, note)``: ``venue``'s working orders, or None with why they could not be read."""
    readers: dict[str, Callable[[], tuple[Rows | None, str | None, str | None]]] = {
        DESK_VENUE_LIVE: _live_rows, DESK_VENUE_PAPER: _paper_rows, DESK_VENUE_SIM: _sim_rows,
    }
    try:
        return readers[venue]()
    except Exception as exc:
        logger.exception("kill: %s's working orders could not be read -- that venue was not swept", venue)
        return None, f"{venue.capitalize()}'s working orders could not be read ({exc}): not swept", None


async def cancel_via_door(venue: str, order_id: int, symbol: str | None) -> tuple[bool, str | None]:
    """One ``kill`` cancel aimed at ``venue`` through ``execution.service.execute``; ``(ok, error)``."""
    from execution.models import ExecutionCommand
    from execution.service import execute

    receipt = await execute(
        ExecutionCommand(
            operation="cancel",
            idempotency_key=f"kill:cancel:{venue}:{order_id}:{uuid.uuid4()}",
            source="kill",
            order_id=order_id,
            symbol=symbol,
            skip_risk=True,
            target_venue=venue,
        ),
        wait_ack=False,
    )
    return bool(receipt.ok), receipt.error


def _order_id(row: dict[str, Any]) -> int | None:
    try:
        return int(row.get("order_id"))
    except (TypeError, ValueError):
        return None


async def sweep_venue(venue: str) -> dict[str, Any]:
    """``{venue, cancelled, failed, error, note}`` for one venue's working orders."""
    rows, error, note = read_working(venue)
    out: dict[str, Any] = {"venue": venue, "cancelled": [], "failed": [], "error": error, "note": note}
    if rows is None:
        return out
    problems: list[str] = []
    for row in rows:
        order_id = _order_id(row)
        if order_id is None or order_id <= 0:
            # An order Nova's API session did not place (TWS shows it with id 0): Nova cannot cancel it.
            problems.append(f"an order ({row.get('symbol') or '?'}, perm id {row.get('perm_id') or '?'}) "
                            "has no API order id -- cancel it in TWS")
            continue
        try:
            ok, why = await cancel_via_door(venue, order_id, str(row.get("symbol") or "") or None)
        except Exception as exc:
            logger.exception("kill: the %s cancel of order %s raised", venue, order_id)
            ok, why = False, f"{type(exc).__name__}: {exc}"
        if ok:
            out["cancelled"].append(order_id)
        else:
            out["failed"].append(order_id)
            problems.append(f"order {order_id}: {why or 'refused'}")
    if problems:
        out["error"] = "; ".join(problems)
    return out


async def sweep_every_venue() -> list[dict[str, Any]]:
    """Every venue's sweep, Live first: ``[{venue, cancelled, failed, error, note}]``."""
    return [await sweep_venue(venue) for venue in VENUES]
