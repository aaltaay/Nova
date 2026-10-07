"""A lane's scoreboard row as a setup arms (ADR 022, ADR 029): the pillars graded by the template, the
stock filter's verdict, and the detector's levels copied onto the row.

Moved out of ``lane.py`` (2026-10-01) so the lane keeps one concern -- turning detector events into rows,
tape reads and proposals -- with room for the liquidity stamps (``lane_liquidity.py``).
"""
from __future__ import annotations

import logging
from typing import Any

from constants_short_setups import SETUPS_SSR_OFF, SETUPS_SSR_SKIP, SETUPS_SSR_UNKNOWN
from setup_scanner import grade as _grade
from setup_scanner import grade_short as _grade_short
from setup_scanner.lane_view import STATE_FILTERED

logger = logging.getLogger(__name__)


def short_context(lane: Any, sym: str, now: float) -> dict | None:
    """The host's ``{prior_close, ssr_yesterday}`` for a short's detector (ADR 049); None when it has none."""
    ask = getattr(lane.host, "short_context", None)
    if ask is None:
        return None
    try:
        return ask(sym, now)
    except Exception:
        logger.warning("setup scanner: %s's short context could not be read -- SSR reads unknown", sym, exc_info=True)
        return None


def prime(lane: Any, sym: str, det: Any, now: float) -> Any:
    """Hand a short's detector the host's context before it reads a bar (ADR 049); a long's is left alone."""
    if lane.p.short:
        det.context = short_context(lane, sym, now)
    return det


def at_trigger(lane: Any, sym: str) -> dict:
    """What a short's row adds at its trigger: the SSR the trigger met (``{}`` on a long)."""
    return {"ssr": ssr_now(lane, sym)} if lane.p.short else {}


def ssr_now(lane: Any, sym: str) -> str:
    """The short setup's SSR from its detector's bars and context (``on`` / ``off`` / ``unknown``)."""
    det = lane.det.get(sym)
    reader = getattr(det, "ssr", None)
    return reader() if reader is not None else SETUPS_SSR_UNKNOWN


def graded(lane: Any, sym: str, now: float, risk: Any = None) -> dict:
    """The symbol's pillars now, graded by this template: ``{grade, pillars}`` (pillars with their checks). A
    short's are its own five (``grade_short``), read for the setup's ``risk``."""
    pillars = lane.host.pillars(sym, now)
    if lane.p.short:
        return _grade_short.graded(lane, sym, now, pillars, risk)
    g, checks = _grade.grade(pillars, lane.p.grade)
    return {"grade": g,
            "pillars": {**pillars, "checks": checks, "float_note": _grade.float_note(pillars, lane.p.grade)}}


def _ssr_skip(lane: Any, ssr: str) -> str | None:
    """A breakdown template that skips SSR keeps a setup armed while SSR is on or unknown out (ADR 049)."""
    if lane.p.ssr != SETUPS_SSR_SKIP or ssr == SETUPS_SSR_OFF:
        return None
    return f"SSR is {ssr}: this template skips SSR"


def new_row(lane: Any, sym: str, sid: str, view: dict, now: float) -> dict:
    setup = view.get("setup") or {}
    read = graded(lane, sym, now, setup.get("risk"))
    g, pillars = read["grade"], read["pillars"]
    row = {"id": sid, "session_date": lane.host.session, "symbol": sym, "leg_t": view["setup_key"],
           "armed_at": setup.get("armed_at") or now, **read, **lane.stamp(), "tf5_armed": lane.tf5.get(sym)}
    lane.rows[sid] = row
    why = lane.p.stock.check(pillars, g) if lane.p.stock.active else None
    if lane.p.short:
        row["ssr"] = ssr_now(lane, sym)
        skip = _ssr_skip(lane, row["ssr"])
        why = "; ".join(w for w in (why, skip) if w) or None
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
