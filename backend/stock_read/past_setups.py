"""Setups that ended on one symbol (ADR 036 amendment, operator ask 2026-09-29): the day's episodes from
the eyes' journal (``eyes/episodes.py``) with what price did after each failed or faded one
(``eyes/aftermath.py``) -- what ``GET /api/stock-read/{symbol}/past-setups`` answers. Read-only.

Today's file is read as it grows (``eyes.journal_day.JournalTail``: appended bytes only) and folded once
for every symbol, so a poll costs the lines written since the last one; another day is folded on each
ask. A source that cannot be read is ``{ok: false, error}`` and the rest still answers.

Owner: this module (in memory: today's fold; invalidation: a journal read again from the start folds
again from nothing, and a new date starts a new fold).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

from eyes import aftermath
from eyes.episodes import END_CUT, END_FADED, END_FAILED, END_TRIGGERED, EpisodeFold
from eyes.journal_day import JournalTail
from setup_scanner.bars import Bar

logger = logging.getLogger(__name__)
BarsFn = Callable[[str, str], "list[Bar]"]


class DayFold:
    """One day's journal, folded as the file grows."""

    def __init__(self, path: Path, date: str):
        self.tail = JournalTail(path, date)
        self.fold = EpisodeFold()
        self.lines = 0

    def refresh(self) -> None:
        generation = self.tail.generation
        rows = self.tail.read()
        if self.tail.generation != generation:
            self.fold, self.lines = EpisodeFold(), 0
        for row in rows:
            self.fold.apply(row)
        self.lines += len(rows)


_lock = threading.Lock()
_today: DayFold | None = None


def _journal_path(date: str) -> Path | None:
    """The day's journal, found by listing its folder (the request's date never becomes a path)."""
    from eyes import journal

    return journal.day_path(date)


def _archive_bars(symbol: str, date: str) -> list[Bar]:
    from eyes.recording import archive_bars

    return archive_bars(symbol, date)


def episodes_of(symbol: str, date: str, *, today: bool, path: Path | None = None) -> tuple[list[dict], int]:
    """``symbol``'s episodes on ``date`` and the day's journal lines read. Today's fold is kept. A day
    with no journal file raises ``FileNotFoundError`` (the route says so)."""
    global _today
    where = path or _journal_path(date)
    if where is None:
        raise FileNotFoundError(f"no eyes' journal on file for {date}")
    if not today:
        day = DayFold(where, date)
        day.refresh()
        return day.fold.episodes(symbol), day.lines
    with _lock:
        if _today is None or _today.tail.date != date or _today.tail.path != where:
            _today = DayFold(where, date)
        _today.refresh()
        return _today.fold.episodes(symbol), _today.lines


def read(symbol: str, date: str, now: float, *, today: bool, path: Path | None = None,
         bars_fn: BarsFn | None = None) -> dict[str, Any]:
    """The route's body (without ``schema_version``)."""
    sym = symbol.upper()
    try:
        eps, lines = episodes_of(sym, date, today=today, path=path)
        journal = {"ok": True, "error": None, "lines": lines}
    except FileNotFoundError as exc:          # no journal that day: a stated absence, not a fault
        eps, journal = [], {"ok": False, "error": str(exc)[:200], "lines": 0}
    except Exception as exc:
        logger.warning("past setups: the journal of %s could not be read", date, exc_info=True)
        eps, journal = [], {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200], "lines": 0}
    bars: list[Bar] = []
    state = {"ok": True, "error": None, "count": 0}
    if any(aftermath.died(e) for e in eps):
        try:
            bars = (bars_fn or _archive_bars)(sym, date)
            state["count"] = len(bars)
        except Exception as exc:
            logger.warning("past setups: the bars of %s on %s could not be read", sym, date, exc_info=True)
            state = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200], "count": 0}
    for e in eps:
        e["after"] = aftermath.after(e, bars, now=now) if state["ok"] else None
    counts = {k: sum(1 for e in eps if e["end"] == k) for k in (END_FAILED, END_FADED, END_TRIGGERED, END_CUT)}
    counts["open"] = sum(1 for e in eps if e["end"] is None)
    return {"symbol": sym, "date": date, "generated_at": now, "episodes": eps, "counts": counts,
            "journal": journal, "bars": state}
