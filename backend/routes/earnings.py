"""
Earnings calendar route -- Finnhub-sourced BMO/AMC calendar for the Earnings tab.

Not an IBKR scanner lease and not a HOD Momo input (single-market-data-feed.mdc
carve-out, same class as Large Cap / Catalysts).

Endpoints:
  GET /api/earnings?range=today|tomorrow|week|month
"""
from __future__ import annotations

from fastapi import APIRouter

from constants import NOVA_API_REV
from earnings_calendar import build_earnings_view

router = APIRouter(tags=["earnings"])


@router.get("/api/earnings")
def get_earnings(range: str = "today"):
    view = build_earnings_view(range)
    return {"rev": NOVA_API_REV, **view}
