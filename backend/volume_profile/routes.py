"""``GET /api/volume-profile/{symbol}`` -- the 5-minute pane's profiles (ADR 058, ``architecture/schema/volume-profile.md``).

Read-only: it needs no API key, and it places, stages and blocks nothing. 422 for a bad symbol, kind, day or anchor.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException

from volume_profile import service

router = APIRouter(tags=["volume_profile"])
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.\-]{0,9}")


@router.get("/api/volume-profile/{symbol}")
async def volume_profile(symbol: str, kind: str, day: str | None = None, anchor: float | None = None) -> dict[str, Any]:
    sym = symbol.strip().upper()
    if not _SYMBOL.fullmatch(sym):
        raise HTTPException(status_code=422, detail=f"Not a stock symbol: {symbol!r}")
    if kind not in ("today", "yesterday"):
        raise HTTPException(status_code=422, detail="kind is today or yesterday")
    try:
        session = date.fromisoformat(day) if day else None
    except ValueError:
        raise HTTPException(status_code=422, detail=f"day is YYYY-MM-DD, not {day!r}") from None
    try:
        return await service.profile(sym, kind, session, anchor)  # type: ignore[arg-type]
    except service.BadRequest as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
