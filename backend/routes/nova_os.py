"""
Desk event log API -- the append-only receipts in ``nova_os/events.py``.

ADR 025 retired the Nova OS verdict and its ``/decide`` / ``/policy`` routes;
the event log stays because kill switch trips, risk halts and archive-health
failures still write to it, and the attention strip reads it.

Endpoints:
  GET /api/nova-os/events            -- recent append-only receipts
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from constants import NOVA_OS_EVENTS_DEFAULT_LIMIT
from nova_os.events import get_events

router = APIRouter(prefix="/api/nova-os", tags=["nova-os"])


@router.get("/events")
def nova_os_events(
    limit: int = NOVA_OS_EVENTS_DEFAULT_LIMIT,
    symbol: str | None = Query(None, description="Filter to one symbol"),
    kind: str | None = Query(None, description="Filter by event kind (decision/action/system)"),
) -> dict:
    rows = get_events(limit=limit, symbol=symbol, kind=kind)
    return {"count": len(rows), "events": rows}
