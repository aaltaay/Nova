"""A lane's scoreboard row as a setup arms (ADR 022, ADR 029): the pillars graded by the template, the
stock filter's verdict, and the detector's levels copied onto the row.

Moved out of ``lane.py`` (2026-10-01) so the lane keeps one concern -- turning detector events into rows,
tape reads and proposals -- with room for the liquidity stamps (``lane_liquidity.py``).
"""
from __future__ import annotations

from typing import Any

from setup_scanner import grade as _grade
from setup_scanner.lane_view import STATE_FILTERED


def graded(lane: Any, sym: str, now: float) -> dict:
    """The symbol's pillars now, graded by this template: ``{grade, pillars}`` (pillars with their checks)."""
    pillars = lane.host.pillars(sym, now)
    g, checks = _grade.grade(pillars, lane.p.grade)
    return {"grade": g,
            "pillars": {**pillars, "checks": checks, "float_note": _grade.float_note(pillars, lane.p.grade)}}


def new_row(lane: Any, sym: str, sid: str, view: dict, now: float) -> dict:
    setup = view.get("setup") or {}
    read = graded(lane, sym, now)
    g, pillars = read["grade"], read["pillars"]
    row = {"id": sid, "session_date": lane.host.session, "symbol": sym, "leg_t": view["setup_key"],
           "armed_at": setup.get("armed_at") or now, **read, **lane.stamp(), "tf5_armed": lane.tf5.get(sym)}
    lane.rows[sid] = row
    why = lane.p.stock.check(pillars, g) if lane.p.stock.active else None
    if why:
        lane.filtered[sid] = why
        lane.journal(STATE_FILTERED, sym, setup_id=sid, reason=why, setup=setup, grade=g,
                     pillars=row["pillars"])
    return row


def copy_setup(row: dict, view: dict) -> None:
    s = view.get("setup") or {}
    row.update({"state": view["state"], "reason": view["reason"], "kind": s.get("kind"),
                "trigger": s.get("trigger"), "entry_planned": s.get("entry"), "stop": s.get("stop"),
                "risk": s.get("risk"), "target1": s.get("target1"), "leg_high": s.get("leg_high"),
                "leg_low": s.get("leg_low"), "leg_pct": s.get("leg_pct"),
                "pullback_bars": s.get("pullback_bars"), "detail": s.get("detail")})
