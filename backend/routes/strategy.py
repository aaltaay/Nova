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
  GET /api/strategy/watchlist/{symbol}       -- one symbol's Five Pillars, ranked or not (quote panel)
  GET /api/strategy/setups/{symbol}          -- Gap and Go + Bull Flag + ABCD signals for one symbol
  GET /api/strategy/risk                     -- current discipline state (P&L, streaks, size, halt)
  POST /api/strategy/risk/validate-trade     -- check a proposed entry/stop/target against risk rules
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alpaca import _get_discovery_provider
from chart_bars import fetch_chart_bars as _fetch_chart_bars
from scanner_surface import surface_rows
from strategy.five_pillars import evaluate_many
from strategy.gap_and_go import evaluate_gap_and_go
from strategy.risk import get_state as _get_risk_state, validate_trade_plan
from strategy.setups import evaluate_setups
from strategy.symbol_pillars import SOURCE_QUOTE, find_board_row, live_quote, quote_row, raw_boards, with_catalyst
from strategy.replay_pillars import replay_view, replay_watchlist
from strategy.watchlist import build_watchlist, score_watchlist_entry
from strategy.watchlist_catalyst import attach as _attach_catalysts, compact as _compact_catalyst
from runtime_state import get_runtime_state

router = APIRouter(prefix="/api/strategy", tags=["strategy"])
logger = logging.getLogger(__name__)

_TRANSPARENCY_NOTE = (
    "Signal only. This endpoint never places, modifies, or cancels orders."
)

# The wire carries a move as a fraction (0.978 = +97.8%). The graders take a
# fraction up to 1.0 or a percent above it, so a move past +100% (1.56) would
# be read as 1.56% -- it is handed over in percent instead.
_GRADED_PCT_KEYS = ("change_pct", "gap_percent")


def _graded(row: dict) -> dict:
    """A surfaced row in the units the Five Pillars / watchlist graders read."""
    out = dict(row)
    for key in _GRADED_PCT_KEYS:
        value = out.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) > 1.0:
            out[key] = value * 100
    return out


def _surfaced(rows: list[dict] | None) -> list[dict]:
    """Rows as the Scanner shows them (QA W6, 2026-09-22).

    The raw caches carry no RVOL, float or news -- those are added at read
    time by ``surface_rows`` (ADR 008), so grading the raw rows marked every
    name "no relative volume data / float unknown / no news" while the same
    row on the board showed all three.
    """
    return [_graded(r) for r in surface_rows(rows)]


def _gapper_cache() -> list[dict]:
    return _surfaced(get_runtime_state().gapper_cache)


def _gainer_cache() -> list[dict]:
    return _surfaced(get_runtime_state().gainer_cache)


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
    try:
        bars_payload = _fetch_chart_bars(symbol.upper(), timeframe="5Min", limit=200, discovery_provider=_get_discovery_provider())
    except HTTPException as exc:
        raise HTTPException(status_code=exc.status_code, detail=f"Bars unavailable for gap-and-go: {exc.detail}") from exc
    signal = evaluate_gap_and_go(candidate, bars_payload.get("bars", []))
    return {"note": _TRANSPARENCY_NOTE, **signal.to_dict()}


@router.get("/watchlist")
def watchlist() -> dict:
    """Ranked Five Pillars watchlist across gappers + gainers.

    All-pillars-pass symbols are always ranked first; the composite score
    (change %, relative volume, float tightness, catalyst freshness) breaks
    ties within each group. On a Sim replay desk off the live edge, ranks the
    replayed day's board at the playhead instead of today's live caches (#881).
    """
    at = _replay_playhead()
    if at is not None:
        return _replay_watchlist(at)
    entries = build_watchlist(_watchlist_universe())
    return {
        "note": _TRANSPARENCY_NOTE,
        "count": len(entries),
        "entries": _attach_catalysts([e.to_dict() for e in entries]),
        "source": "live",
        "replay": None,
    }


@router.get("/watchlist/{symbol:path}")
def watchlist_one(symbol: str) -> dict:
    """One symbol's Five Pillars, whether or not the ranked watchlist holds it.

    Graded from the symbol's own scanner row when a board holds it (surfaced as
    the Scanner shows it), else from its live L1 quote decorated the same way.
    ``rank`` is its 1-based place on the ranked watchlist, or null. On a Sim
    replay desk, graded from the replayed day's board at the playhead instead.
    """
    sym = symbol.strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol required")
    at = _replay_playhead()
    if at is not None:
        return _replay_pillars(sym, at)
    raw, source = find_board_row(sym, raw_boards())
    if raw is None:
        raw, source = quote_row(sym, live_quote(sym)), SOURCE_QUOTE
    # A blocklisted symbol leaves the boards, not the quote panel: grade its row as is.
    surfaced = surface_rows([raw]) or [dict(raw)]
    row = with_catalyst(_graded(surfaced[0]))
    rank = None
    if source in ("gappers", "gainers"):
        ranked = [e.symbol for e in build_watchlist(_watchlist_universe())]
        rank = ranked.index(sym) + 1 if sym in ranked else None
    [entry] = _attach_catalysts([score_watchlist_entry(row).to_dict()])
    return {"note": _TRANSPARENCY_NOTE, "symbol": sym, "source": source, "rank": rank, "entry": entry, "replay": None}


def _replay_playhead() -> float | None:
    from sim.replay_playhead import replay_playhead

    return replay_playhead()


def _replay_pillars(sym: str, at: float) -> dict:
    """One symbol's pillars on a Sim replay desk: its own row on the replayed day's board at ``at``.

    Nothing of today's: no scanner cache, no fundamentals, no live catalyst verdict and no Contenders
    rank (``rank`` is null; the row's place on its board is ``replay.board_rank``). No row at the
    playhead is ``entry: null`` with the reason in ``replay.absent`` -- never a grade from today.
    """
    from leaderboard import playback
    from leaderboard.rows import session_date_for

    day = session_date_for(at)
    found, replay = replay_view(sym, day, at, playback.board_at(day, at))
    entry = None
    if found is not None:
        entry = score_watchlist_entry(_graded(found)).to_dict()
        entry["catalyst"] = _compact_catalyst(found.get("catalyst"))
    return {"note": _TRANSPARENCY_NOTE, "symbol": sym, "source": "replay", "rank": None, "entry": entry,
            "replay": replay}


def _replay_watchlist(at: float) -> dict:
    """The whole Contenders list on a Sim replay desk (#881): the replayed day's board at ``at``.

    Uses only the leaderboard store's rows and catalysts at the playhead -- never today's
    scanner caches, fundamentals or live catalyst verdicts.
    """
    from leaderboard import playback
    from leaderboard.rows import session_date_for

    day = session_date_for(at)
    candidates, replay = replay_watchlist(day, at, playback.board_at(day, at))
    by_sym = {c["symbol"]: c for c in candidates}
    graded = build_watchlist([_graded(c) for c in candidates])
    entries: list[dict] = []
    for item in graded:
        row = item.to_dict()
        cand = by_sym.get(item.symbol) or {}
        row["catalyst"] = _compact_catalyst(cand.get("catalyst"))
        entries.append(row)
    return {
        "note": _TRANSPARENCY_NOTE,
        "count": len(entries),
        "entries": entries,
        "source": "replay",
        "replay": replay,
    }



@router.get("/setups/{symbol}")
def setups_one(symbol: str) -> dict:
    """Gap and Go + Bull Flag + ABCD signals for one symbol, using 1-min bars."""
    candidate = _find_gapper(symbol) or {"symbol": symbol.upper()}
    try:
        bars_payload = _fetch_chart_bars(symbol.upper(), timeframe="1Min", limit=100, discovery_provider=_get_discovery_provider())
    except HTTPException as exc:
        raise HTTPException(status_code=exc.status_code, detail=f"Bars unavailable for setups: {exc.detail}") from exc
    return {"note": _TRANSPARENCY_NOTE, **evaluate_setups(candidate, bars_payload.get("bars", []))}


class TradePlanRequest(BaseModel):
    entry_price: float
    stop_price: float
    target_price: float


@router.get("/risk")
def risk_status() -> dict:
    """Current discipline state: today's realized P&L, streaks, position size,
    and whether the walk-away guardrails have halted trading for the day."""
    return {"note": _TRANSPARENCY_NOTE, **_get_risk_state().to_dict()}


@router.post("/risk/validate-trade")
def risk_validate_trade(body: TradePlanRequest) -> dict:
    """Check a proposed entry/stop/target against the stop-distance ceiling
    and minimum profit/loss ratio. Does not place, size, or track a trade."""
    ok, issues = validate_trade_plan(body.entry_price, body.stop_price, body.target_price)
    return {"note": _TRANSPARENCY_NOTE, "ok": ok, "issues": issues}
