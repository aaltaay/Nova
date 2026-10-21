"""The Forex page's route (ADR 061): the board. Read-only; it never waits on IBKR."""
from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from constants_forex_board import FOREX_ERR_BAD_PARAM, FOREX_PERIODS
from forex_board import board, reads, refresh
from forex_board.state import store

router = APIRouter(tags=["forex"])


def _replay_desk() -> bool:
    from sim.mode import is_replay_desk

    return bool(is_replay_desk())


@router.get("/api/forex/board")
def get_board(period: str = "1D"):
    if period not in FOREX_PERIODS:
        return JSONResponse(status_code=400, content={"detail": {
            "reason": FOREX_ERR_BAD_PARAM, "error": f"period must be one of {', '.join(FOREX_PERIODS)}",
            "field": "period"}})
    now = time.time()
    on = refresh.enabled()
    if on:
        refresh.want(period, now)
    return board.compose(store(), now, enabled=on, replay_desk=_replay_desk(), period=period,
                         history_left=reads.history_left(), history_headroom=reads.headroom(now))
