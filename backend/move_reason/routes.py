"""Why it's moving (ADR 028):

  GET /api/why/{symbol}   the checks and the likely cause for one symbol (the Trader tab's News panel)

Read-only; no network wait (``move_reason/facts.py`` reads caches, the halt log and the borrow record).
"""
from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from constants_move_reason import MOVE_RULES_VERSION, MOVE_SCHEMA_VERSION
from move_reason import facts as facts_mod
from move_reason import rules

router = APIRouter(tags=["move_reason"])
ET = ZoneInfo("America/New_York")
_FACT_KEYS = ("price", "change_pct", "volume", "rel_volume", "float_shares", "short_interest", "days_to_cover",
              "split", "halts", "borrow", "catalyst")


def why(symbol: str, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    facts = facts_mod.gather(symbol, now)
    read = rules.read(facts, now)
    return {
        "schema_version": MOVE_SCHEMA_VERSION,
        "symbol": facts["symbol"],
        "generated_at": now,
        "session_date": datetime.fromtimestamp(now, ET).date().isoformat(),
        "rules_version": MOVE_RULES_VERSION,
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
