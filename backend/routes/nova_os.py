"""
Nova OS read API (Phase P1) — READ ONLY. No route here decides, stages, or
places an order; those arrive in later phases. Today this exposes the audit
trail and the stable vocabulary so the UI (and future decide()) can render and
validate against the same codes the backend persists.

Endpoints:
  GET /api/nova-os/policy   -- policy version, control modes, decisions,
                               action codes, reason codes, loss policy
  GET /api/nova-os/events   -- recent append-only decision/action receipts
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from constants import (
    NOVA_OS_ACTIONS,
    NOVA_OS_DECISIONS,
    NOVA_OS_DEFAULT_MODE,
    NOVA_OS_EVENTS_DEFAULT_LIMIT,
    NOVA_OS_LOSS_POLICY_DOWNGRADE_AFTER_LOSSES,
    NOVA_OS_LOSS_POLICY_HALT_AFTER_LOSSES,
    NOVA_OS_MODES,
    NOVA_OS_REASON_CODES,
)
from nova_os import codes
from nova_os.events import get_events

router = APIRouter(prefix="/api/nova-os", tags=["nova-os"])


@router.get("/policy")
def nova_os_policy() -> dict:
    """The stable Nova OS vocabulary + policy metadata the UI validates against."""
    return {
        "policy_version": codes.policy_version(),
        "default_mode": NOVA_OS_DEFAULT_MODE,
        "modes": list(NOVA_OS_MODES),
        "decisions": list(NOVA_OS_DECISIONS),
        "actions": list(NOVA_OS_ACTIONS),
        "reason_codes": list(NOVA_OS_REASON_CODES),
        "loss_policy": {
            "downgrade_after_losses": NOVA_OS_LOSS_POLICY_DOWNGRADE_AFTER_LOSSES,
            "halt_after_losses": NOVA_OS_LOSS_POLICY_HALT_AFTER_LOSSES,
        },
    }


@router.get("/events")
def nova_os_events(
    limit: int = NOVA_OS_EVENTS_DEFAULT_LIMIT,
    symbol: str | None = Query(None, description="Filter to one symbol"),
    kind: str | None = Query(None, description="Filter by event kind (decision/action/system)"),
) -> dict:
    rows = get_events(limit=limit, symbol=symbol, kind=kind)
    return {"count": len(rows), "events": rows}
