"""Desk halt surfaces -- MWCB banner + Nasdaq RSS feed health.

Display only. Does not place or block orders.
"""
from __future__ import annotations

from fastapi import APIRouter

from constants import NOVA_API_REV
from ibkr import nasdaq_halt_feed

router = APIRouter(tags=["halts"])


@router.get("/api/halts/desk")
def get_halt_desk():
    return {"rev": NOVA_API_REV, **nasdaq_halt_feed.desk_snapshot()}
