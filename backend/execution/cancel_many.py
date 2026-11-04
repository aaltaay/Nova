"""Cancel many working orders, one door call each, on one venue (ADR 007, #1281).

``DELETE /api/ibkr/orders``: a stock's cancel, the Cancel All hotkey and KILL's first step. An order id is only
meaningful on the venue that issued it (``execution.venue_door``), so a run holds one venue: the caller's, else the
desk's on arrival. Every cancel names it, a list read after the desk left it is not sent at all, and the first cancel
the door refuses ``VENUE_CHANGED`` ends the run. Nothing reaches the venue the desk moved to.

Owner: this module (no state; the door is ``execution.service``).
"""
from __future__ import annotations

import uuid
from typing import Any

from execution import service as _service
from execution import venue_door
from execution.models import ExecutionCommand
from ibkr import orders as _orders
from ibkr.errors import IbkrAccountError


async def cancel_open_orders(symbol: str | None, all_symbols: bool, venue: str | None, *, client_timing: Any,
                             received_ns: int, ingress_wall_ns: int) -> dict[str, Any]:
    """``{ok, cancelled, failed, error}``, with ``symbol`` or ``all_symbols`` saying which run it was."""
    sym = (symbol or "").strip().upper()
    if not all_symbols and not sym:
        return {
            "ok": False, "error": "symbol is required (or pass all_symbols=true)",
            "cancelled": [], "failed": [],
        }
    rows_venue = venue or venue_door.current()
    try:
        open_list = _orders.open_orders()
    except IbkrAccountError as exc:
        return {
            "ok": False, "error": str(exc), "cancelled": [], "failed": [],
        }
    cancelled: list[int] = []
    failed: list[dict[str, Any]] = []
    scope_key = "ALL" if all_symbols else sym
    moved = venue_door.current() != rows_venue     # a list read after the move is the other venue's
    for row in open_list:
        if moved:
            break
        row_sym = str(row.get("symbol", "")).upper()
        if row.get("order_id") is None:
            continue
        if not all_symbols and row_sym != sym:
            continue
        oid = int(row["order_id"])
        receipt = await _service.execute(
            ExecutionCommand(
                operation="cancel",
                idempotency_key=f"cancel-all:{scope_key}:{oid}:{uuid.uuid4()}",
                source="manual",
                symbol=row_sym or None,
                order_id=oid,
                skip_risk=True,
                expected_venue=rows_venue,
                client_timing=client_timing,
                backend_ingress_wall_ns=ingress_wall_ns,
            ),
            received_ns=received_ns,
        )
        _service.finalize_http_response(
            receipt.execution_id, duplicate=receipt.duplicate,
        )
        if receipt.ok:
            cancelled.append(oid)
        else:
            failed.append({"order_id": oid, "error": receipt.error})
            moved = receipt.reason_code == venue_door.VENUE_CHANGED
    out: dict[str, Any] = {
        "ok": not failed and not moved,
        "cancelled": cancelled,
        "failed": failed,
        "error": None if not failed else f"{len(failed)} cancel(s) failed",
    }
    if moved:
        now = venue_door.current().capitalize()
        was = rows_venue.capitalize()
        out["error"] = f"The desk moved from {was} to {now}: the cancels stopped, none went to {now}."
    if not all_symbols:
        out["symbol"] = sym
    else:
        out["all_symbols"] = True
    return out
