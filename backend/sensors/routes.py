"""Read-only L2 Brain sensor HTTP surface. No order mutations."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from sensors.adapters import stubs
from sensors.registry import SENSOR_IDS, list_catalog, read_all, read_one
from sensors.symbol import SensorSymbolError, normalize_symbol, resolve_symbol

router = APIRouter(tags=["sensors"])


class MemoryBody(BaseModel):
    symbol: str
    decision: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    outcome: str | None = None
    note: str | None = None


def _symbol(raw: str | None, *, required: bool) -> str | None:
    try:
        if required:
            return resolve_symbol(raw)
        if raw is None or not str(raw).strip():
            return None
        return normalize_symbol(raw, required=False)
    except SensorSymbolError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/sensors")
def sensors_catalog() -> dict:
    return {"count": len(SENSOR_IDS), "sensors": list_catalog()}


@router.get("/sensors/snapshot")
def sensors_snapshot(symbol: str | None = Query(default=None)) -> dict:
    sym = _symbol(symbol, required=True)
    rows = read_all(sym or "")
    return {"symbol": sym, "count": len(rows), "sensors": rows}


@router.get("/sensors/l2")
def sensor_l2(symbol: str | None = Query(default=None)) -> dict:
    return read_one("l2", _symbol(symbol, required=True))


@router.get("/sensors/tape")
def sensor_tape(symbol: str | None = Query(default=None)) -> dict:
    return read_one("tape", _symbol(symbol, required=True))


@router.get("/sensors/vwap")
def sensor_vwap(symbol: str | None = Query(default=None)) -> dict:
    return read_one("vwap", _symbol(symbol, required=True))


@router.get("/sensors/macd")
def sensor_macd(symbol: str | None = Query(default=None)) -> dict:
    return read_one("macd", _symbol(symbol, required=True))


@router.get("/sensors/rvol")
def sensor_rvol(symbol: str | None = Query(default=None)) -> dict:
    return read_one("rvol", _symbol(symbol, required=True))


@router.get("/sensors/day-volume")
def sensor_day_volume(symbol: str | None = Query(default=None)) -> dict:
    return read_one("day-volume", _symbol(symbol, required=True))


@router.get("/sensors/spread")
def sensor_spread(symbol: str | None = Query(default=None)) -> dict:
    return read_one("spread", _symbol(symbol, required=True))


@router.get("/sensors/session-phase")
def sensor_session_phase() -> dict:
    return read_one("session-phase", None)


@router.get("/sensors/flow")
def sensor_flow(symbol: str | None = Query(default=None)) -> dict:
    return read_one("flow", _symbol(symbol, required=True))


@router.get("/sensors/last-move")
def sensor_last_move(symbol: str | None = Query(default=None)) -> dict:
    return read_one("last-move", _symbol(symbol, required=True))


@router.get("/sensors/liquidity")
def sensor_liquidity(symbol: str | None = Query(default=None)) -> dict:
    return read_one("liquidity", _symbol(symbol, required=True))


@router.get("/sensors/emas")
def sensor_emas(symbol: str | None = Query(default=None)) -> dict:
    return read_one("emas", _symbol(symbol, required=True))


@router.get("/sensors/news")
def sensor_news(symbol: str | None = Query(default=None)) -> dict:
    return read_one("news", _symbol(symbol, required=True))


@router.get("/sensors/risk")
def sensor_risk(symbol: str | None = Query(default=None)) -> dict:
    return read_one("risk", _symbol(symbol, required=False))


@router.get("/sensors/halt")
def sensor_halt(symbol: str | None = Query(default=None)) -> dict:
    return read_one("halt", _symbol(symbol, required=True))


@router.get("/sensors/memory")
def sensor_memory(symbol: str | None = Query(default=None)) -> dict:
    return read_one("memory", _symbol(symbol, required=True))


@router.post("/sensors/memory")
def sensor_memory_write(body: MemoryBody) -> dict:
    try:
        symbol = resolve_symbol(body.symbol)
    except SensorSymbolError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    try:
        return stubs.write_memory(
            symbol=symbol or "",
            decision=body.decision,
            confidence=body.confidence,
            outcome=body.outcome,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sensors/regime")
def sensor_regime(symbol: str | None = Query(default=None)) -> dict:
    return read_one("regime", _symbol(symbol, required=True))


@router.get("/sensors/macro")
def sensor_macro(symbol: str | None = Query(default=None)) -> dict:
    return read_one("macro", _symbol(symbol, required=False))


@router.get("/sensors/book-pulls")
def sensor_book_pulls(symbol: str | None = Query(default=None)) -> dict:
    return read_one("book-pulls", _symbol(symbol, required=True))


@router.get("/sensors/book-pulls/events")
def sensor_book_pull_events(
    since: float | None = Query(default=None, ge=0),
    symbol: str | None = Query(default=None),
) -> dict:
    """The book watcher's flags newer than ``since``, oldest first (ADR 031) -- for a poller."""
    from book_watch.view import book_pull_events

    return book_pull_events(since, _symbol(symbol, required=False))
