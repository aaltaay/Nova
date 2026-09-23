"""
Archive REST routes (cold archive health, days, ask).

The decision replay routes (/replay, /walk, /review) were retired with the
Nova OS verdict (ADR 025).

Thin handlers — logic lives in ``backend/archive/``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from archive.ask import ask as ask_archive
from archive.health import archive_health, list_local_cold_days
from constants import (
    JOURNAL_TRADES_DEFAULT_LIMIT,
)

router = APIRouter(prefix="/api/archive", tags=["archive"])


def _require_session_date(session_date: str) -> None:
    if len(session_date) != 10 or session_date[4] != "-" or session_date[7] != "-":
        raise HTTPException(status_code=400, detail="session_date must be YYYY-MM-DD")


@router.get("/health")
def get_archive_health() -> dict:
    """Cold-archive + R2 durability status (fail-loud when upload misconfigured)."""
    return archive_health()


@router.get("/days")
def get_archive_days() -> dict:
    """List local cold archive session dates."""
    days = list_local_cold_days()
    return {"days": days, "count": len(days)}


@router.get("/ask")
def get_archive_ask(
    symbol: str | None = Query(default=None),
    session_date: str | None = Query(default=None),
    limit: int = Query(default=JOURNAL_TRADES_DEFAULT_LIMIT, ge=1, le=500),
) -> dict:
    """Find journal trades + archive index rows by symbol and/or day."""
    if session_date:
        _require_session_date(session_date)
    return ask_archive(symbol=symbol, session_date=session_date, limit=limit)
