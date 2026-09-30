"""The Cryptos page's routes (ADR 040): the board and a coin's chart. Read-only; neither waits on the network."""
from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from constants_crypto import CRYPTO_CANDLE_TFS, CRYPTO_ERR_UNKNOWN_SYMBOL, CRYPTO_ERR_UNKNOWN_TF
from crypto import board, candles, refresh
from crypto.state import store

router = APIRouter(tags=["crypto"])


def _replay_desk() -> bool:
    from sim.mode import is_replay_desk

    return bool(is_replay_desk())


@router.get("/api/crypto/board")
def get_board():
    now = time.time()
    on = refresh.enabled()
    if on:
        refresh.want(now)
    return board.compose(store(), now, enabled=on, replay_desk=_replay_desk())


@router.get("/api/crypto/candles")
def get_candles(symbol: str = "BTC", tf: str = "15m"):
    sym = (symbol or "").strip().upper()
    coin = candles.COIN_BY_SYMBOL.get(sym)
    if coin is None or not coin["coinbase"]:
        return JSONResponse(status_code=400, content={"detail": {
            "reason": CRYPTO_ERR_UNKNOWN_SYMBOL, "error": f"No chart for {sym or 'that symbol'}", "field": "symbol"}})
    if tf not in CRYPTO_CANDLE_TFS:
        return JSONResponse(status_code=400, content={"detail": {
            "reason": CRYPTO_ERR_UNKNOWN_TF, "error": f"Time frame must be one of {', '.join(CRYPTO_CANDLE_TFS)}",
            "field": "tf"}})
    now = time.time()
    if refresh.enabled():
        refresh.want_candles(sym, tf, now)
    return candles.view(store(), sym, tf, now)
