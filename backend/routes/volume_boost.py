"""GET /api/volume-boost -- derived L1 spike list (no scanner lease)."""
from __future__ import annotations

from fastapi import APIRouter

from volume_boost import build_view

router = APIRouter(tags=["volume-boost"])


@router.get("/api/volume-boost")
def get_volume_boost():
    return build_view()
