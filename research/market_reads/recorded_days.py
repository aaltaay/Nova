"""Which days the operator recorded, and which stocks each day (ADR 059, #1064): the Session Records on disk.

``<NOVA_SIM_CAPTURE_DIR>/<day>/<SYMBOL>/`` holds one Session Record per recorded stock-day (``recordings.py``). This
lists them read-only -- it never creates the root or a folder -- with what each recording's own manifest says it
holds: its status, its recorded stretches merged (first / last ET, minutes recorded), its gaps and how many were not
planned stops. A folder whose manifest is missing or unreadable is listed with its ``problem``, never dropped.

Not here: the tape archive (``archive.db`` ``tape_ibkr``: every print the desk's tape line saw, 2026-07-15 on, any
symbol it streamed) and ``l2.db`` (depth samples while a depth session was open). Listing every symbol-day those hold
means scanning a multi-gigabyte table, so ``recorded_tape`` / ``recorded_depth`` answer them one stock-day at a time
(their ``recorded_days`` say which days a symbol has there).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_reads import REPO, recordings, roots  # noqa: F401  (REPO puts backend/ on sys.path)

ET = ZoneInfo("America/New_York")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COLUMNS = ["day", "symbol", "status", "first_et", "last_et", "recorded_min", "stretches", "gaps", "unplanned_gaps",
           "problem"]
RULE = ("one row per Session Record folder <day>/<SYMBOL>; first_et / last_et / recorded_min come from the manifest's "
        "recorded segments merged (ET, Nova's clock); gaps are the stops between them, unplanned_gaps those that were "
        "not a planned stop; a folder with no readable manifest is listed with its problem")
NOT_HERE = ("the tape archive (archive.db tape_ibkr, every print the desk's tape line saw, 2026-07-15 on, any symbol) and "
            "l2.db (depth samples) are not listed here: recorded_tape / recorded_depth answer them per stock-day")


def _hhmmss(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S")


def _checked(day: str | None) -> str | None:
    if day is None:
        return None
    date.fromisoformat(day)                  # a malformed day raises ValueError naming it
    return day


def _row(day: str, symbol: str) -> dict[str, Any]:
    state = recordings.capture_state(symbol, day)
    spans, coverage = state["spans"], state["coverage"]
    gaps = coverage.get("gaps") or []
    return {"day": day, "symbol": symbol, "status": coverage.get("status"),
            "first_et": _hhmmss(spans[0][0]) if spans else None, "last_et": _hhmmss(spans[-1][1]) if spans else None,
            "recorded_min": round(sum(stop - start for start, stop in spans) / 60.0, 1) if spans else None,
            "stretches": len(spans), "gaps": len(gaps), "unplanned_gaps": sum(not g.get("planned") for g in gaps),
            "problem": state["problem"]}


def recorded_days(date_from: str | None = None, date_to: str | None = None,
                  symbol: str | None = None) -> pd.DataFrame:
    """The Session Records on disk, newest day first, then by symbol (``COLUMNS``); ``attrs`` say how many days and
    stocks, the folder read and what is not listed (``NOT_HERE``). ``LookupError`` when the folder is not on disk."""
    lo, hi = _checked(date_from), _checked(date_to)
    if lo and hi and lo > hi:
        raise ValueError("date_from is after date_to")
    root = roots.sim_capture()
    if not root.is_dir():
        raise LookupError(f"{root} is not on disk (NOVA_SIM_CAPTURE_DIR names the Session Records folder)")
    wanted = symbol.strip().upper() if symbol else None
    rows = []
    for day_dir in sorted((p for p in root.iterdir() if p.is_dir() and _DAY.match(p.name)), reverse=True):
        if (lo and day_dir.name < lo) or (hi and day_dir.name > hi):
            continue
        for folder in sorted(p for p in day_dir.iterdir() if p.is_dir()):
            if wanted and folder.name.upper() != wanted:
                continue
            try:
                rows.append(_row(day_dir.name, folder.name))
            except ValueError:               # a folder that names no ticker is not a Session Record
                continue
    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame.attrs.update(source=str(root), rule=RULE, not_here=NOT_HERE, days=int(frame["day"].nunique()),
                       symbols=int(frame["symbol"].nunique()), units="*_et ET HH:MM:SS; recorded_min minutes",
                       asked={"date_from": lo, "date_to": hi, "symbol": wanted})
    return frame
