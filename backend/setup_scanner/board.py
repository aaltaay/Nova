"""The Setups board payload (ADR 022, ADR 029, ADR 031): each setup's
template in play, one row per symbol worth looking at, nearest-to-trigger
first, and one summary per setup with a scanner. Pure: reads the engine's
state, writes nothing.

Row: ``{symbol, setup_type, state, reason, kind, nth, setup_id, setup, leg,
last_price, distance, grade, pillars, tape, proposal, outcome, bar_r, mfe, mae,
failed_at}``; ``setups[]``: ``{id, level, chosen, proposing, template,
templates_watched, window: {start, end, state}, counts}``; the payload names
its ``source`` (``live``).
"""
from __future__ import annotations

from typing import Any

from constants_bot import BOT_LEVEL_EYES
from constants_setups import SETUPS_SCHEMA_VERSION
from scanner_wire import wire_safe
from setup_scanner.detectors import window, window_state


def template_view(lane: Any) -> dict[str, Any] | None:
    if lane is None:
        return None
    return {"id": lane.p.template_id, "rev": lane.p.template_rev, "name": lane.p.name,
            "params_hash": lane.p.params_hash}


def setup_summary(lane: Any, lanes: list[Any], levels: dict, now: float, *, can_propose: bool) -> dict[str, Any]:
    """One setup's card: its level, whether it proposes, its template, window and today's counts."""
    setup = lane.setup
    level = int((levels.get("levels") or {}).get(setup) or 0)
    start, end = window(setup, lane.p.pattern)
    return {
        "id": setup, "level": level, "chosen": levels.get("chosen") == setup,
        "proposing": can_propose and level >= BOT_LEVEL_EYES,
        "template": template_view(lane),
        "templates_watched": sum(1 for other in lanes if other.setup == setup),
        "window": {"start": start, "end": end, "state": window_state(now, start, end)},
        "counts": lane.counts(),
    }


def board_body(lanes: list[Any], all_lanes: list[Any], levels: dict, now: float, *, can_propose: bool) -> dict:
    """``setups``, ``rows`` and ``proposals`` for the playing lanes (the live board and the Sim eyes')."""
    setups = [setup_summary(lane, all_lanes, levels, now, can_propose=can_propose) for lane in lanes]
    rows: list[dict] = []
    proposals: list[dict] = []
    for lane in lanes:
        rows += lane.board_rows(now)
        proposals += lane.open_proposals()
    return {"proposing": any(s["proposing"] for s in setups), "setups": setups, "rows": rows,
            "proposals": proposals}


def build_board(engine: Any, now: float) -> dict[str, Any]:
    body = board_body(engine.playing_lanes(), engine.lanes, engine.levels(), now,
                      can_propose=not engine._replay_fn())
    return wire_safe({
        "schema_version": SETUPS_SCHEMA_VERSION,
        "generated_at": now,
        "session_date": engine.session,
        "source": "live",
        "universe": len(engine.universe),
        "seeding": len(engine.seeding),
        "scoreboard": engine.store_error is None,
        "scoreboard_error": engine.store_error,
        "replay": None,
        **body,
    })
