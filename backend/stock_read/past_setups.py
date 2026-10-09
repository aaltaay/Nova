"""Setups that ended on one symbol (ADR 036 amendment, operator ask 2026-09-29): the day's episodes from
the eyes' journal (``eyes/episodes.py``) with what price did after each failed or faded one
(``eyes/aftermath.py``) -- what ``GET /api/stock-read/{symbol}/past-setups`` answers. Read-only.

Today's file is read as it grows (``eyes.journal_day.JournalTail``: appended bytes only) and folded once
for every symbol, so a poll costs the lines written since the last one; another day is folded on each
ask. A source that cannot be read is ``{ok: false, error}`` and the rest still answers.

On a Sim replay desk (ADR 052 amendment, #815) the episodes are the Sim eyes' -- folded from the lines the
replay's lanes wrote up to the playhead (``eyes.sim_past``) -- and what price did next reads the replay's
one-minute bars completed by the playhead (``replay``): nothing after it.

Owner: this module (in memory: today's fold; invalidation: a journal read again from the start folds
again from nothing, and a new date starts a new fold).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

from constants_setups import SETUPS_5M_BAR_SEC, SETUPS_5M_SCORE_WINDOW_MIN, SETUPS_5M_TEMPLATE_ID
from eyes import aftermath
from eyes.episodes import END_CUT, END_FADED, END_FAILED, END_TRIGGERED, EpisodeFold
from eyes.journal_day import JournalTail
from setup_scanner.bars import Bar

logger = logging.getLogger(__name__)
BarsFn = Callable[[str, str], "list[Bar]"]


def _fold(five: bool) -> EpisodeFold:
    return EpisodeFold(SETUPS_5M_TEMPLATE_ID, SETUPS_5M_BAR_SEC) if five else EpisodeFold()


class DayFold:
    """One day's journal, folded as the file grows: the setups in play's, or the 5-minute lanes' (``five``)."""

    def __init__(self, path: Path, date: str, five: bool = False):
        self.tail = JournalTail(path, date)
        self.five = five
        self.fold = _fold(five)
        self.lines = 0

    def refresh(self) -> None:
        generation = self.tail.generation
        rows = self.tail.read()
        if self.tail.generation != generation:
            self.fold, self.lines = _fold(self.five), 0
        for row in rows:
            self.fold.apply(row)
        self.lines += len(rows)


_lock = threading.Lock()
_today: dict[bool, DayFold] = {}         # today's folds: the setups in play (False), the 5-minute lanes (True)



def _journal_path(date: str) -> Path | None:
    """The day's journal, found by listing its folder (the request's date never becomes a path)."""
    from eyes import journal

    return journal.day_path(date)


def _archive_bars(symbol: str, date: str) -> list[Bar]:
    from eyes.recording import archive_bars

    return archive_bars(symbol, date)


def episodes_of(symbol: str, date: str, *, today: bool, path: Path | None = None,
                five: bool = False) -> tuple[list[dict], int]:
    """``symbol``'s episodes on ``date`` and the day's journal lines read -- the 5-minute lanes' with
    ``five``. Today's fold is kept. A day with no journal file raises ``FileNotFoundError`` (the route
    says so)."""
    where = path or _journal_path(date)
    if where is None:
        raise FileNotFoundError(f"no eyes' journal on file for {date}")
    if not today:
        day = DayFold(where, date, five)
        day.refresh()
        return day.fold.episodes(symbol), day.lines
    with _lock:
        held = _today.get(five)
        if held is None or held.tail.date != date or held.tail.path != where:
            held = _today[five] = DayFold(where, date, five)
        held.refresh()
        return held.fold.episodes(symbol), held.lines


def read(symbol: str, date: str, now: float, *, today: bool, path: Path | None = None,
         bars_fn: BarsFn | None = None, five: bool = False) -> dict[str, Any]:
    """The route's body (without ``schema_version``); ``five``: the 5-minute lanes' setups, each failed or
    faded one measured over ``SETUPS_5M_SCORE_WINDOW_MIN``."""
    sym = symbol.upper()
    try:
        eps, lines = episodes_of(sym, date, today=today, path=path, five=five)
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
    return _body(sym, date, now, eps, bars, state, journal, five, replay=False)


def _body(sym: str, date: str | None, now: float, eps: list[dict], bars: list[Bar], state: dict[str, Any],
          journal: dict[str, Any], five: bool, *, replay: bool, note: str | None = None) -> dict[str, Any]:
    """The route's body: each failed or faded episode's ``after`` over ``bars`` at ``now``, and the counts."""
    window = SETUPS_5M_SCORE_WINDOW_MIN if five else aftermath.EYES_EPISODE_AFTER_MIN
    for e in eps:
        e["after"] = aftermath.after(e, bars, now=now, window_min=window) if state["ok"] else None
    counts = {k: sum(1 for e in eps if e["end"] == k) for k in (END_FAILED, END_FADED, END_TRIGGERED, END_CUT)}
    counts["open"] = sum(1 for e in eps if e["end"] is None)
    out = {"symbol": sym, "date": date, "generated_at": now, "timeframe": "5m" if five else "1m",
           "episodes": eps, "counts": counts, "journal": journal, "bars": state, "replay": replay}
    if replay:
        out["note"] = note
    return out


def _loaded_symbol() -> str | None:
    from bot.replay_desk import desk

    here = desk()
    return here["symbol"] if here is not None else None


def replay(symbol: str, date: str | None, *, five: bool = False, eyes: Any = None,
           playhead: float | None = None) -> dict[str, Any]:
    """The route's body on a Sim replay desk (ADR 052 amendment, #815): the Sim eyes' setups that ended on the
    loaded replay, measured on its one-minute bars completed by the moment the lanes stand at -- never a minute
    after the playhead. Nothing while the lanes read the replay or catch up to a rewind (``pending``), and nothing
    for a symbol that is not the loaded replay's (``note`` says which)."""
    from stock_read.replay_read import playhead as read_playhead

    sym = symbol.upper()
    if eyes is None:
        from eyes.sim_eyes import get_sim_eyes

        eyes = get_sim_eyes()
    got = eyes.past(sym)
    at = read_playhead() if playhead is None else playhead
    if got is None and _loaded_symbol() == sym:
        got = {"pending": "the Sim eyes are reading the replay"}      # loaded, not read yet
    if got is None or "pending" in got:
        note = (str(got["pending"]) if got is not None else
                f"the Sim eyes read the loaded replay only, and nothing of {sym} is loaded")
        empty = {"ok": False, "error": note, "lines": 0}
        out = _body(sym, date, at, [], [], {"ok": False, "error": note, "count": 0}, empty, five, replay=True,
                    note=note)
        out["pending"] = got is not None
        return out
    if date and date != got["date"]:
        note = f"the replay is {got['date']}: the Sim eyes read only the day the desk replays"
        return {**_body(sym, date, at, [], [], {"ok": False, "error": note, "count": 0},
                        {"ok": False, "error": note, "lines": 0}, five, replay=True, note=note), "pending": False}
    at = float(got["at"])
    bars = [b for b in got["bars"] if float(b.t) + 60 <= at + 1e-6]       # completed by the playhead
    eps = [dict(e) for e in got["episodes"][five]]
    out = _body(sym, got["date"], at, eps, bars, {"ok": True, "error": None, "count": len(bars)},
                {"ok": True, "error": None, "lines": int(got["lines"])}, five, replay=True)
    out["pending"] = False
    return out
