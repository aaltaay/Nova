"""``GET /api/ibkr/lanes``: who holds each Level 2 and Time & Sales line (ADR 071).

Shape: ``architecture/schema/market-data.md`` "Three lanes". Read-only.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from line_lanes import view

router = APIRouter(tags=["lanes"])


@router.get("/lanes")
def get_lanes() -> dict[str, Any]:
    return view.view()
