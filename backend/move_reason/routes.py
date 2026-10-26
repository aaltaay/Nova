"""Why it's moving (ADR 028):

  GET /api/why/{symbol}                 the checks and the likely cause for one symbol (the Trader tab's News panel)
  GET /api/why?symbols=A,B&board=gappers the same read for many symbols at once (the Catalyst column); ``board``
                                         reads each symbol's row on that board at the price the board shows

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
    MOVE_BATCH_BOARDS,
    MOVE_BATCH_MAX_SYMBOLS,
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
_FACT_KEYS = ("board", "priced_by", "last_trade", "price", "change_pct", "volume", "rel_volume", "float_shares", "float_contradicted", "short_interest",
              "short_interest_ts", "short_above_float", "days_to_cover", "split", "halts", "borrow", "catalyst",
              "quote_type", "fund")


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
    # The playhead off the live edge (``sim.replay_playhead``; an unreadable edge counts as a replay), else None.
    from sim.replay_playhead import replay_playhead

    playhead = replay_playhead()
    if playhead is not None:
        return replay_read(symbol, playhead)
    now = time.time() if now is None else now
    return _answer(facts_mod.gather(symbol, now), now, replay=False)


def why_many(symbols: list[str], board: str | None = None, now: float | None = None) -> dict:
    """Each symbol's read, as ``why`` answers it; with ``board``, each read at that board's row and price. One
    symbol's failure is that symbol's (``errors``), never the batch's. The halt log is read once for all, and on a
    Sim replay so is the board at the playhead."""
    from sim.replay_playhead import replay_playhead

    playhead = replay_playhead()
    at = playhead if playhead is not None else (time.time() if now is None else now)
    halts = facts_mod.halts_many(symbols, at)
    # On a replay the board at the playhead is read once for the batch, not once per symbol.
    snapshot = replay_facts.board_snapshot(playhead) if playhead is not None else None
    reads: dict[str, dict | None] = {}
    errors: dict[str, str] = {}
    for sym in symbols:
        try:
            if playhead is not None:
                reads[sym] = replay_read(sym, playhead, board, snapshot, (halts or {}).get(sym))
            else:
                facts = facts_mod.gather(sym, at, board=board, halts=(halts or {}).get(sym))
                reads[sym] = _answer(facts, at, replay=False)
        except Exception as exc:  # noqa: BLE001 -- one symbol's read fails alone, and says so
            logger.warning("move_reason: the read of %s failed", sym, exc_info=True)
            reads[sym], errors[sym] = None, f"{type(exc).__name__}: {exc}"[:200]
    return {"schema_version": MOVE_SCHEMA_VERSION, "rules_version": MOVE_RULES_VERSION, "board": board,
            "replay": playhead is not None, "generated_at": at, "reads": reads, "errors": errors}


def replay_read(symbol: str, playhead: float, board: str | None = None, snapshot: dict | None = None,
                halts: dict | None = None) -> dict:
    """The replayed day's read as of ``playhead``: every fact from a record that reaches it, nothing after it."""
    facts = replay_facts.gather(symbol, playhead, board, snapshot, halts)
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


@router.get("/api/why")
def why_batch_route(symbols: str = "", board: str | None = None) -> dict:
    syms = list(dict.fromkeys(s.strip().upper() for s in symbols.split(",") if s.strip()))
    if not syms:
        raise HTTPException(status_code=400, detail="symbols required")
    if len(syms) > MOVE_BATCH_MAX_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"at most {MOVE_BATCH_MAX_SYMBOLS} symbols")
    if board is not None and board not in MOVE_BATCH_BOARDS:
        raise HTTPException(status_code=400, detail=f"board must be one of {', '.join(MOVE_BATCH_BOARDS)}")
    return why_many(syms, board)


@router.get("/api/why/{symbol:path}")
def why_route(symbol: str) -> dict:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol required")
    return why(sym)
