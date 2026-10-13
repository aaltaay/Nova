"""FINRA short interest as it stood published at a past moment: a Sim replay's short facts (ADR 028 amendment
2026-10-12).

Massive's reference archive keeps FINRA's twice-monthly settlements, one file per settlement month
(``<NOVA_MARKET_DATA_DIR>/store/reference/short_interest/<YYYY-MM>.jsonl``, rows ``{settlement_date, ticker,
short_interest, avg_daily_volume, days_to_cover}``). FINRA publishes a settlement about seven business days after
it, after the close, so here a settlement counts only from the ``MOVE_FINRA_PUBLISH_BUSINESS_DAYS``th business
day after its date -- never earlier. SDEV on 2026-10-02 reads Sep 15's 1,212,152 shares, not Sep 30's 3,436,239,
which came out about Oct 9. The lag is a conservative rule, not FINRA's own calendar, and the read says so.

Owner: this module (read-only; an LRU of (month file, symbol) reads, keyed by the file's size and time so a file
the downloader is still writing is read again). No state on disk.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from constants_move_reason import (
    MOVE_FINRA_PUBLISH_BUSINESS_DAYS,
    MOVE_REPLAY_SHORT_CACHE,
    MOVE_REPLAY_SHORT_MONTHS_BACK,
    MOVE_REPLAY_SHORT_SUBDIR,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def directory() -> Path:
    """Under the Massive root the Sim reads (``sim.massive_files.root``, ADR 046)."""
    from sim.massive_files import root

    return root().joinpath(*MOVE_REPLAY_SHORT_SUBDIR)


def counts_from(settlement: date) -> date:
    """The first day a settlement counts: ``MOVE_FINRA_PUBLISH_BUSINESS_DAYS`` exchange days after it."""
    from sim.trading_day import last_open_day

    day, n = settlement, 0
    while n < MOVE_FINRA_PUBLISH_BUSINESS_DAYS:
        day += timedelta(days=1)
        if last_open_day(day) == day:
            n += 1
    return day


def _months(day: date) -> list[str]:
    """The replayed day's settlement month and the ones before it, newest first."""
    out, y, m = [], day.year, day.month
    for _ in range(MOVE_REPLAY_SHORT_MONTHS_BACK + 1):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


@lru_cache(maxsize=MOVE_REPLAY_SHORT_CACHE)
def _read(path: str, stamp: tuple[int, int], ticker: str) -> tuple[dict[str, Any], ...]:
    needle = f'"{ticker}"'
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if needle in line:
                row = json.loads(line)
                if row.get("ticker") == ticker:
                    out.append(row)
    return tuple(out)


def _rows(month: str, ticker: str) -> tuple[dict[str, Any], ...]:
    path = directory() / f"{month}.jsonl"
    try:
        st = path.stat()
    except FileNotFoundError:
        return ()
    return _read(str(path), (st.st_size, st.st_mtime_ns), ticker)


def published_at(symbol: str, at: float) -> dict[str, Any]:
    """The newest settlement that counts by ``at``.

    ``{row, counts_from, pending}``: ``row`` the settlement (None when none counts yet), ``pending`` the newest
    settlement on file that does not count yet (``{settlement_date, counts_from}``) -- or ``{"reason": why}`` when
    the archive is not on this desk. Every row returned has ``counts_from <= at``'s date.
    """
    sym = (symbol or "").strip().upper()
    if not directory().is_dir():
        return {"reason": "Massive's FINRA short-interest archive is not on this desk"}
    day = datetime.fromtimestamp(at, ET).date()
    best = pending = None
    for month in _months(day):
        for row in _rows(month, sym):
            try:
                settled = date.fromisoformat(str(row["settlement_date"]))
            except (KeyError, ValueError):
                logger.warning("move_reason: a FINRA row of %s has no settlement date: %r", sym, row)
                continue
            if settled > day:
                continue
            start = counts_from(settled)
            if start <= day:
                if best is None or settled > best[0]:
                    best = (settled, start, row)
            elif pending is None or settled > pending[0]:
                pending = (settled, start)
    return {
        "row": best[2] if best else None,
        "counts_from": best[1] if best else None,
        "pending": {"settlement_date": pending[0], "counts_from": pending[1]}
        if pending and (best is None or pending[0] > best[0]) else None,
    }
