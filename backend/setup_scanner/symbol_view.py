"""One symbol across every setup's template in play (ADR 036): the lane's row whatever its state,
the levels a forming setup would arm with, and the lane's own indicators.

``GET /api/setups/symbol/{symbol}`` answers this; ``stock_read`` reads it for the Trader's plan,
tiles and drawings. Reads the engine's state (and, for a name no lane reads, today's hot list to say why):
never writes, never arms.
"""
from __future__ import annotations

import logging
from typing import Any

from constants_setups import SETUP_STATE_WATCHING, SETUPS_SCHEMA_VERSION_SYMBOL
from scanner_wire import wire_safe
from setup_scanner import lane_view
from setup_scanner.board import template_view
from setup_scanner.detectors import window, window_state
from setup_scanner.five_minute_lane import is_five_minute

NOT_FOLLOWED = ("{sym} is not on today's hot list and not among the HOD Momo names the scanners follow, so no "
                "lane reads it -- star it to follow it")
REPLAY_DESK = ("a Sim replay desk: the live scanner's lanes are not the replay's -- the Sim eyes follow the "
               "loaded recording")

logger = logging.getLogger(__name__)


def not_followed_note(sym: str) -> str:
    """Why no lane reads ``sym``: a listed name says what keeps it out (ADR 044: HOD Momo's reserved slots
    are full, or IBKR cannot stream it); any other name is outside the names the scanners follow."""
    try:
        from hot_list.following import listed_note

        listed = listed_note(sym)
    except Exception:
        logger.warning("setup scanner: today's hot list could not be read for %s's note", sym, exc_info=True)
        listed = None
    return listed or NOT_FOLLOWED.format(sym=sym)


def rules_of(params: Any) -> dict[str, Any]:
    """The numbers a plan names: the stop cap (dollars, or a share of the entry) and floor, the target rule,
    the entry cent, and the candle's length."""
    return {"stop_cap": getattr(params, "stop_cap", None), "stop_cap_pct": getattr(params, "stop_cap_pct", None),
            "bar_sec": getattr(params, "bar_sec", 60), "min_stop": getattr(params, "min_stop", None),
            "target_r": getattr(params, "target_r", None), "target_mode": getattr(params, "target_mode", "r"),
            "entry_offset": getattr(params, "entry_offset", None),
            "risk_slippage": getattr(params, "risk_slippage", None)}


def lane_entry(lane: Any, sym: str, levels: dict, now: float) -> dict[str, Any]:
    start, end = window(lane.setup, lane.p.pattern)
    level = int((levels.get("levels") or {}).get(lane.setup) or 0)
    row = lane_view.symbol_row(lane, sym)
    if row is None:              # followed, but this lane has not read a bar for it yet
        row = {"symbol": sym, "setup_type": lane.setup, "state": SETUP_STATE_WATCHING, "reason": "warming up",
               "kind": None, "nth": 0, "setup_id": None, "setup": None, "leg": None, "last_price": None,
               "distance": None, "grade": None, "pillars": None, "graded": None, "phase": None, "tape": None,
               "trigger_tape": None, "proposal": None, "outcome": None, "outcome_at": None, "bar_r": None,
               "mfe": None, "mae": None, "failed_at": None, "forming": None, "series": None}
    five = is_five_minute(lane)
    return {**row, "template": template_view(lane), "level": 0 if five else level,
            "chosen": not five and levels.get("chosen") == lane.setup, "timeframe": "5m" if five else "1m",
            "window": {"start": start, "end": end, "state": window_state(now, start, end)},
            "rules": rules_of(lane.p.pattern)}


def symbol_view(engine: Any, symbol: str, now: float | None = None) -> dict[str, Any]:
    now = engine._clock() if now is None else now
    sym = (symbol or "").strip().upper()
    replay = bool(engine._replay_fn())
    followed = sym in engine.universe and not replay
    note = REPLAY_DESK if replay else (None if followed else not_followed_note(sym))
    setups: list[dict[str, Any]] = []
    five: list[dict[str, Any]] = []
    if followed:
        levels = engine.levels()
        setups = [lane_entry(lane, sym, levels, now) for lane in engine.playing_lanes()]
        five = [lane_entry(lane, sym, levels, now) for lane in engine.lanes if is_five_minute(lane)]
    return wire_safe({
        "schema_version": SETUPS_SCHEMA_VERSION_SYMBOL,
        "generated_at": now,
        "session_date": engine.session,
        "symbol": sym,
        "followed": followed,
        "followed_note": note,
        "seeding": sym in engine.seeding,
        "setups": setups,
        "setups_5m": five,          # the 5-minute lanes (five_minute_lane.py): the 5-minute chart's only
    })
