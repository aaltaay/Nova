"""Why it's moving (ADR 028):

  GET /api/why/{symbol}   the checks and the likely cause for one symbol (the Trader tab's News panel)

Read-only; no network wait (``move_reason/facts.py`` reads caches, the halt log and the borrow record).
On a Sim replay desk (the Sim off its live edge) the read is the replayed day's as of the playhead, never
today's: ``move_reason/replay_facts.py`` reads each fact from a record that reaches the playhead, and a fact
none reaches is unknown with the reason. Only when no record reaches it at all does the answer say the
moment is not read (``not_read_on_replay``).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from constants_move_reason import (
    MOVE_CONFIDENCE_LIKELY,
    MOVE_KIND_NOT_READ,
    MOVE_NOT_READ_REPLAY_DETAIL,
    MOVE_RULES_VERSION,
    MOVE_SCHEMA_VERSION,
)
from move_reason import facts as facts_mod
from move_reason import replay_facts, rules

logger = logging.getLogger(__name__)
router = APIRouter(tags=["move_reason"])
ET = ZoneInfo("America/New_York")
_FACT_KEYS = ("price", "change_pct", "volume", "rel_volume", "float_shares", "float_contradicted", "short_interest",
              "short_interest_ts", "short_above_float", "days_to_cover", "split", "halts", "borrow", "catalyst")


def _replay_desk() -> bool:
    from sim.mode import is_replay_desk

    try:
        return bool(is_replay_desk())
    except Exception:
        logger.warning("why it's moving: the Sim live edge is unreadable -- the desk counts as a replay", exc_info=True)
        return True


def _playhead() -> float:
    from sim import session_clock

    return session_clock.now_et().timestamp()


def not_read_on_replay(symbol: str, playhead: float) -> dict:
    """The answer on a Sim replay desk no record reaches: the replayed day named, no checks, no facts. The
    absence is certain, so its confidence is ``likely``."""
    day = datetime.fromtimestamp(playhead, ET)
    return {
        "schema_version": MOVE_SCHEMA_VERSION,
        "symbol": (symbol or "").strip().upper(),
        "generated_at": playhead,
        "session_date": day.date().isoformat(),
        "rules_version": MOVE_RULES_VERSION,
        "replay": True,
        "likely": {"kind": MOVE_KIND_NOT_READ, "label": f"Not read on a Sim replay of {day:%b} {day.day}",
                   "detail": MOVE_NOT_READ_REPLAY_DETAIL, "confidence": MOVE_CONFIDENCE_LIKELY},
        "checks": [],
        "facts": {},
    }


def why(symbol: str, now: float | None = None) -> dict:
    if _replay_desk():
        return replay_read(symbol, _playhead())
    now = time.time() if now is None else now
    return _answer(facts_mod.gather(symbol, now), now, replay=False)


def replay_read(symbol: str, playhead: float) -> dict:
    """The replayed day's read as of ``playhead``: every fact from a record that reaches it, nothing after it."""
    facts = replay_facts.gather(symbol, playhead)
    if not replay_facts.readable(facts):
        return not_read_on_replay(symbol, playhead)
    return _answer(facts, playhead, replay=True)


def _answer(facts: dict, now: float, *, replay: bool) -> dict:
    read = rules.read(facts, now)
    return {
        "schema_version": MOVE_SCHEMA_VERSION,
        "symbol": facts["symbol"],
        "generated_at": now,
        "session_date": datetime.fromtimestamp(now, ET).date().isoformat(),
        "rules_version": MOVE_RULES_VERSION,
        "replay": replay,
        "likely": read["likely"],
        "checks": read["checks"],
        "facts": {**{k: facts.get(k) for k in _FACT_KEYS}, **read["derived"]},
    }


@router.get("/api/why/{symbol:path}")
def why_route(symbol: str) -> dict:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol required")
    return why(sym)
