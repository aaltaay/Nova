"""``GET /api/ibkr/feed`` -- is IBKR data arriving, and the feed's gaps (#672). Read-only.

Answers ``ibkr.feed_pulse.view()`` from memory (a Wi-Fi read happens on its own
worker thread, never here). The desk polls it once a second for its NO DATA chip.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ibkr import feed_pulse

router = APIRouter()


@router.get("/feed")
def ibkr_feed() -> dict[str, Any]:
    return feed_pulse.view()
