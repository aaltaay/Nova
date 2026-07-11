"""
Strategy signal routes — READ-ONLY. These endpoints never place, modify, or
cancel any order. They only score existing scanner data against the Five
Pillars and the Gap and Go setup so a future UI can display a checkmark /
signal. See backend/strategy/five_pillars.py and gap_and_go.py.

Endpoints:
  GET /api/strategy/five-pillars            -- score every current gapper
  GET /api/strategy/five-pillars/{symbol}    -- score one symbol's latest gapper row
  GET /api/strategy/gap-and-go/{symbol}      -- Gap and Go signal for one symbol
  GET /api/strategy/watchlist                -- ranked Five Pillars watchlist (gappers + gainers)
  GET /api/strategy/setups/{symbol}          -- Gap and Go + Bull Flag + ABCD signals for one symbol
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from bars import fetch_bars as _fetch_bars
from strategy.five_pillars import evaluate_many
from strategy.gap_and_go import evaluate_gap_and_go
from strategy.setups import evaluate_setups
from strategy.watchlist import build_watchlist

router = APIRouter(prefix="/api/strategy", tags=["strategy"])

_TRANSPARENCY_NOTE = (
    "Signal only. This endpoint never places, modifies, or cancels orders."
)


def _gapper_cache() -> list[dict]:
    # Lazy import — main.py imports this router, so importing main at module
    # load time would be circular. Same pattern as hod_momo_enrichment.py.
    import main as _main
    return _main._gapper_cache


def _gainer_cache() -> list[dict]:
    import main as _main
    return _main._gainer_cache


def _find_gapper(symbol: str) -> dict | None:
    symbol = symbol.upper()
    for g in _gapper_cache():
        if g.get("symbol") == symbol:
            return g
    return None


def _watchlist_universe() -> list[dict]:
    """Gappers + gainers, deduped by symbol (gapper row wins on collision since
    it carries premarket gap % rather than intraday change %)."""
    seen: dict[str, dict] = {g["symbol"]: g for g in _gainer_cache() if g.get("symbol")}
    for g in _gapper_cache():
        if g.get("symbol"):
            seen[g["symbol"]] = g
    return list(seen.values())


@router.get("/five-pillars")
def five_pillars_all() -> dict:
    """Score every symbol currently in the gapper cache against the Five Pillars."""
    results = evaluate_many(_gapper_cache())
    return {
        "note": _TRANSPARENCY_NOTE,
        "count": len(results),
        "results": [r.to_dict() for r in results],
    }


@router.get("/five-pillars/{symbol}")
def five_pillars_one(symbol: str) -> dict:
    """Score a single symbol using its latest gapper cache row, if present."""
    candidate = _find_gapper(symbol)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} is not in the current gapper list")
    [result] = evaluate_many([candidate])
    return {"note": _TRANSPARENCY_NOTE, **result.to_dict()}


@router.get("/gap-and-go/{symbol}")
def gap_and_go_one(symbol: str) -> dict:
    """Gap and Go signal for one symbol. Fetches today's 5-min bars for the
    pre-market-high calculation; combines with the current gapper cache row."""
    candidate = _find_gapper(symbol) or {"symbol": symbol.upper()}
    bars_payload = _fetch_bars(symbol.upper(), timeframe="5Min", limit=200)
    signal = evaluate_gap_and_go(candidate, bars_payload.get("bars", []))
    return {"note": _TRANSPARENCY_NOTE, **signal.to_dict()}


@router.get("/watchlist")
def watchlist() -> dict:
    """Ranked Five Pillars watchlist across gappers + gainers.

    All-pillars-pass symbols are always ranked first; the composite score
    (change %, relative volume, float tightness, catalyst freshness) breaks
    ties within each group. See strategy/watchlist.py for the formula.
    """
    entries = build_watchlist(_watchlist_universe())
    return {
        "note": _TRANSPARENCY_NOTE,
        "count": len(entries),
        "entries": [e.to_dict() for e in entries],
    }


@router.get("/setups/{symbol}")
def setups_one(symbol: str) -> dict:
    """Gap and Go + Bull Flag + ABCD signals for one symbol, using 1-min bars."""
    candidate = _find_gapper(symbol) or {"symbol": symbol.upper()}
    bars_payload = _fetch_bars(symbol.upper(), timeframe="1Min", limit=100)
    return {"note": _TRANSPARENCY_NOTE, **evaluate_setups(candidate, bars_payload.get("bars", []))}
