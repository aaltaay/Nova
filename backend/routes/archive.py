"""
Archive REST routes (Nova OS P8/P9).

Thin handlers — logic lives in ``backend/archive/``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from archive.ask import ask as ask_archive
from archive.evening_review import evening_review as run_evening_review
from archive.health import archive_health, list_local_cold_days
from archive.replay import replay_day, walk_day
from constants import (
    ARCHIVE_EVENING_REVIEW_MAX_SYMBOLS,
    ARCHIVE_REPLAY_MAX_SYMBOLS,
    ARCHIVE_REPLAY_WALK_MAX_STEPS,
    ARCHIVE_REPLAY_WALK_STEP_MIN,
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


@router.get("/replay/{session_date}")
def get_archive_replay(
    session_date: str,
    limit: int = Query(default=20, ge=1, le=50),
    as_of: float | None = Query(
        default=None,
        description="Unix ts — if set, decide() only sees bars up to this moment (no-hindsight). Omit for the legacy whole-day (hindsight=True) snapshot.",
    ),
) -> dict:
    """Replay one archived day through decide(record=False)."""
    _require_session_date(session_date)
    result = replay_day(session_date, max_symbols=limit, as_of_ts=as_of)
    if result.get("error") and not result.get("decisions"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/walk/{session_date}")
def get_archive_walk(
    session_date: str,
    limit: int = Query(default=10, ge=1, le=ARCHIVE_REPLAY_MAX_SYMBOLS),
    step_min: float = Query(default=ARCHIVE_REPLAY_WALK_STEP_MIN, ge=1, le=60),
    max_steps: int = Query(default=ARCHIVE_REPLAY_WALK_MAX_STEPS, ge=1, le=ARCHIVE_REPLAY_WALK_MAX_STEPS),
) -> dict:
    """No-hindsight decision timeline for one day — the "rewind" scrubber:
    each entry in ``steps`` is what Nova OS would have decided as of that
    moment, using only bars available by then."""
    _require_session_date(session_date)
    result = walk_day(session_date, max_symbols=limit, step_min=step_min, max_steps=max_steps)
    if result.get("error") and not result.get("steps"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/review/{session_date}")
def get_archive_review(
    session_date: str,
    horizon_min: int | None = Query(default=None, ge=1, le=120),
    limit: int = Query(default=ARCHIVE_EVENING_REVIEW_MAX_SYMBOLS, ge=1, le=ARCHIVE_REPLAY_MAX_SYMBOLS),
) -> dict:
    """Evening review: no-hindsight decision per symbol, scored forward from
    that decision's own as-of moment."""
    _require_session_date(session_date)
    kwargs = {"max_symbols": limit}
    if horizon_min is not None:
        kwargs["horizon_min"] = horizon_min
    return run_evening_review(session_date, **kwargs)


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
