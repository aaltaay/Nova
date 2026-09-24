"""The Setups board payload (ADR 022, ADR 029): the lane of the template in
play, one row per symbol worth looking at, nearest-to-trigger first. Pure:
reads the engine's state, writes nothing.

Row: ``{symbol, state, reason, kind, nth, setup_id, setup, leg, last_price,
distance, grade, pillars, tape, proposal, outcome, bar_r, mfe, mae}``; the
payload names its ``source`` (``live``) and the ``template`` in play.
"""
from __future__ import annotations

from typing import Any

from constants_setups import SETUPS_SCHEMA_VERSION
from scanner_wire import wire_safe


def template_view(lane: Any) -> dict[str, Any] | None:
    if lane is None:
        return None
    return {"id": lane.p.template_id, "rev": lane.p.template_rev, "name": lane.p.name,
            "params_hash": lane.p.params_hash}


def build_board(engine: Any, now: float) -> dict[str, Any]:
    lane = engine.playing
    return wire_safe({
        "schema_version": SETUPS_SCHEMA_VERSION,
        "generated_at": now,
        "session_date": engine.session,
        "source": "live",
        "template": template_view(lane),
        "templates_watched": len(engine.lanes),
        "universe": len(engine.universe),
        "seeding": len(engine.seeding),
        "scoreboard": engine.store_error is None,
        "scoreboard_error": engine.store_error,
        "proposing": not engine._replay_fn(),
        "replay": None,
        "rows": lane.board_rows(now) if lane is not None else [],
        "proposals": lane.open_proposals() if lane is not None else [],
    })
