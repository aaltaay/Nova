"""The Global page's route (ADR 060): the board. Read-only; it never waits on IBKR."""
from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from constants_global_board import GLOBAL_ERR_BAD_PARAM, GLOBAL_PERIODS
from global_board import board, reads, refresh
from global_board.state import store

router = APIRouter(tags=["global"])


def _replay_desk() -> bool:
    from sim.mode import is_replay_desk

    return bool(is_replay_desk())


@router.get("/api/global/board")
def get_board(period: str = "1D"):
    if period not in GLOBAL_PERIODS:
        return JSONResponse(status_code=400, content={"detail": {
            "reason": GLOBAL_ERR_BAD_PARAM, "error": f"period must be one of {', '.join(GLOBAL_PERIODS)}",
            "field": "period"}})
    now = time.time()
    on = refresh.enabled()
    if on:
        refresh.want(period, now)
    return board.compose(store(), now, enabled=on, replay_desk=_replay_desk(), period=period,
                         history_left=reads.history_left())
