"""Leaderboard playback routes (ADR 022; shapes in AGENTS.md section 3)."""
from __future__ import annotations

import asyncio
import re
from datetime import date as date_cls

from fastapi import APIRouter, HTTPException, Query

from constants_leaderboard import LEADERBOARD_DAYS_LIMIT, LEADERBOARD_SOURCES
from leaderboard import playback

router = APIRouter(prefix="/api/leaderboard")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _day(value: str) -> str:
    if not _DATE_RE.match(value or ""):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    try:
        date_cls.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must be a real calendar day") from exc
    return value


def _source(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if value not in LEADERBOARD_SOURCES:
        raise HTTPException(status_code=400, detail=f"source must be one of {', '.join(LEADERBOARD_SOURCES)}")
    return value


@router.get("/days")
async def get_days(limit: int = Query(LEADERBOARD_DAYS_LIMIT, ge=1, le=LEADERBOARD_DAYS_LIMIT)) -> dict:
    return await asyncio.to_thread(playback.days, limit)


@router.get("/{day}")
async def get_board(day: str, at: float = Query(..., description="Playhead, epoch seconds"), source: str | None = None) -> dict:
    return await asyncio.to_thread(playback.board_at, _day(day), float(at), _source(source))


@router.get("/{day}/coverage")
async def get_coverage(day: str, source: str | None = None) -> dict:
    return await asyncio.to_thread(playback.coverage, _day(day), _source(source))


@router.get("/{day}/halts")
async def get_halts(day: str, until: float | None = None) -> dict:
    return await asyncio.to_thread(playback.halts, _day(day), until)
