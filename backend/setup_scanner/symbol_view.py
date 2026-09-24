"""One symbol across every setup's template in play (ADR 036): the lane's row whatever its state,
the levels a forming setup would arm with, and the lane's own indicators.

``GET /api/setups/symbol/{symbol}`` answers this; ``stock_read`` reads it for the Trader's plan,
tiles and drawings. Pure over the engine's state: reads, never writes, never arms.
"""
from __future__ import annotations

from typing import Any

from constants_setups import SETUP_STATE_WATCHING, SETUPS_SCHEMA_VERSION_SYMBOL
from scanner_wire import wire_safe
from setup_scanner import lane_view
from setup_scanner.board import template_view
from setup_scanner.detectors import window, window_state

NOT_FOLLOWED = ("the setup scanner follows the HOD Momo active names; {sym} is not one of them right now, "
                "so no lane reads it")
REPLAY_DESK = ("a Sim replay desk: the live scanner's lanes are not the replay's -- the Sim eyes follow the "
               "loaded recording")


def rules_of(params: Any) -> dict[str, Any]:
    """The numbers a plan names: the stop cap and floor, the target rule, the entry cent."""
    return {"stop_cap": getattr(params, "stop_cap", None), "min_stop": getattr(params, "min_stop", None),
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
               "distance": None, "grade": None, "pillars": None, "tape": None, "proposal": None, "outcome": None,
               "bar_r": None, "mfe": None, "mae": None, "failed_at": None, "forming": None, "series": None}
    return {**row, "template": template_view(lane), "level": level, "chosen": levels.get("chosen") == lane.setup,
            "window": {"start": start, "end": end, "state": window_state(now, start, end)},
            "rules": rules_of(lane.p.pattern)}


def symbol_view(engine: Any, symbol: str, now: float | None = None) -> dict[str, Any]:
    now = engine._clock() if now is None else now
    sym = (symbol or "").strip().upper()
    replay = bool(engine._replay_fn())
    followed = sym in engine.universe and not replay
    note = REPLAY_DESK if replay else (None if followed else NOT_FOLLOWED.format(sym=sym))
    setups: list[dict[str, Any]] = []
    if followed:
        levels = engine.levels()
        setups = [lane_entry(lane, sym, levels, now) for lane in engine.playing_lanes()]
    return wire_safe({
        "schema_version": SETUPS_SCHEMA_VERSION_SYMBOL,
        "generated_at": now,
        "session_date": engine.session,
        "symbol": sym,
        "followed": followed,
        "followed_note": note,
        "seeding": sym in engine.seeding,
        "setups": setups,
    })
