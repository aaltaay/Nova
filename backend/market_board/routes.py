"""The Market page's route (ADR 053): the board. Read-only; it never waits on IBKR or the network."""
from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from constants_market_board import MARKET_ERR_BAD_PARAM, MARKET_PERIODS, MARKET_TOP_KINDS
from market_board import board, refresh
from market_board.state import store

router = APIRouter(tags=["market"])


def _replay_desk() -> bool:
    from sim.mode import is_replay_desk

    return bool(is_replay_desk())


def _bad(field: str, allowed: tuple[str, ...]) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": {
        "reason": MARKET_ERR_BAD_PARAM, "error": f"{field} must be one of {', '.join(allowed)}", "field": field}})


@router.get("/api/market/board")
def get_board(sectors: str = "1D", industries: str = "1D", climate: str = "1D", top: str = "biggest",
              top_period: str = "1D"):
    params = {"sectors": sectors, "industries": industries, "climate": climate, "top": top, "top_period": top_period}
    for field in ("sectors", "industries", "climate", "top_period"):
        if params[field] not in MARKET_PERIODS:
            return _bad(field, MARKET_PERIODS)
    if top not in MARKET_TOP_KINDS:
        return _bad("top", MARKET_TOP_KINDS)
    now = time.time()
    on = refresh.enabled()
    if on:
        refresh.want(now)
    return board.compose(store(), now, enabled=on, replay_desk=_replay_desk(), params=params)
