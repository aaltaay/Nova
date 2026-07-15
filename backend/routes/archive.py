"""
Archive REST routes (Nova OS P8/P9).

Thin handlers — logic lives in ``backend/archive/``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from archive.health import archive_health, list_local_cold_days
from archive.replay import replay_day

router = APIRouter(prefix="/api/archive", tags=["archive"])


@router.get("/health")
def get_archive_health() -> dict:
    """Cold-archive + R2 durability status (fail-loud when upload misconfigured)."""
    return archive_health()


@router.get("/days")
def get_archive_days() -> dict:
    """List local cold archive session dates."""
    days = list_local_cold_days()
    return {"days": days, "count": len(days)}


@router.get("/replay/{session_date}")
def get_archive_replay(
    session_date: str,
    limit: int = Query(default=20, ge=1, le=50),
) -> dict:
    """Replay one archived day through decide(record=False)."""
    if len(session_date) != 10 or session_date[4] != "-" or session_date[7] != "-":
        raise HTTPException(status_code=400, detail="session_date must be YYYY-MM-DD")
    result = replay_day(session_date, max_symbols=limit)
    if result.get("error") and not result.get("decisions"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result
