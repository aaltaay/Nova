"""Nova's eyes at a past moment (operator ask, 2026-09-24): the live journal
folded up to a playhead into the Setups board's shape.

"i want this stuff to be recorded when they show up ... viewable in the sim ...
when something pops up": off the live edge the Sim desk draws every setup card --
its rows, today's funnel and the open proposals -- as Nova's live eyes had them
at the playhead, from the lines ``eyes/journal.py`` wrote then. Nothing is
recomputed with today's rules (a Session Record replay does that:
``eyes/sim_eyes.py``), no line after the playhead is read, and a stretch the
journal did not record is a stated gap, never the board carried across it.

``Playback`` folds a ``JournalDay`` (``eyes/journal_day.py``) forward to a moment
-- the engine's lines (a start, the lanes, the names followed, the beat) here,
each lane's in a ``LaneFold`` (``eyes/lane_fold.py``) -- and answers the board
body. Pure apart from the file read.

Owner: this module (in memory; invalidation: a rewind folds the day again from
its first line; a journal read again from the start does too).
"""
from __future__ import annotations

import bisect
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from constants_bot import BOT_SCANNER_SETUPS, BOT_SETUP_FIRST_PULLBACK
from constants_eyes import EYES_PLAYBACK_GAP_SEC, EYES_SCHEMA_VERSION
from constants_setups import SETUP_TEMPLATE_DEFAULT_ID
from eyes.journal_day import JournalDay
from eyes.lane_fold import COUNT_KEYS, LaneFold

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
# ``window_of(setup, template_id) -> (start, end)``: the arming window the card shows.
WindowOf = Callable[[str, "str | None"], "tuple[str, str] | None"]


def clock(ts: float | None) -> str:
    return datetime.fromtimestamp(float(ts), ET).strftime("%H:%M:%S") if ts else "--:--:--"


class Playback:
    """A day's live journal folded forward to a moment."""

    def __init__(self, day: JournalDay):
        self.day = day
        self._reset()

    def _reset(self) -> None:
        self.at: float | None = None
        self.k = 0                                   # lines folded
        self.lanes: dict[tuple[str, str], LaneFold] = {}
        self.playing: dict[str, str] = {}            # setup -> its template in play
        self.meta: dict[tuple[str, str], dict[str, Any]] = {}
        self.running: dict[str, int] | None = None   # setup -> lanes, from the session's latest "lanes" line
        self.universe: set[str] = set()
        self.last: dict[str, float] = {}
        self.last_line_ts: float | None = None
        self.beating = False                         # this session writes beats: a silence is a gap
        self._generation = self.day.generation

    def advance(self, at: float) -> list[dict[str, Any]]:
        """Fold every line at or before ``at``; the proposals raised on the way. A moment
        before the last one folds the day again from its first line."""
        if self._generation != self.day.generation or (self.at is not None and at < self.at):
            self._reset()
        stop = bisect.bisect_right(self.day.ts, at)
        raised: list[dict[str, Any]] = []
        for line in self.day.lines[self.k:stop]:
            prop = self._apply(line)
            if prop is not None:
                raised.append(prop)
        self.k = max(self.k, stop)
        self.at = at
        return raised

    def _apply(self, line: dict[str, Any]) -> dict | None:
        ev = str(line.get("event") or "")
        ts = float(line.get("ts") or 0.0)
        sym = line.get("symbol")
        self.last_line_ts = ts
        if sym and line.get("last") is not None:
            self.last[sym] = float(line["last"])
        if sym and ev == "triggered" and line.get("price") is not None:
            self.last[sym] = float(line["price"])
        if ev == "session":                          # Nova started: the eyes began again from nothing
            self.lanes, self.universe, self.running, self.beating = {}, set(), None, False
        elif ev == "lanes":
            self._lanes(line)
        elif ev == "watch":
            self.universe |= {str(s) for s in line.get("added") or []}
            for gone in line.get("removed") or []:
                self.universe.discard(gone)
                for lane in self.lanes.values():
                    lane.syms.pop(gone, None)
                    lane.tape.pop(gone, None)
        elif ev == "beat":
            self.beating = True
        elif sym:
            setup = line.get("setup_type") or BOT_SETUP_FIRST_PULLBACK
            template = line.get("template") or SETUP_TEMPLATE_DEFAULT_ID
            if line.get("playing"):
                self.playing[setup] = template
            self.meta.setdefault((setup, template), {"id": template, "rev": line.get("rev"), "name": template,
                                                     "params_hash": None})
            lane = self.lanes.get((setup, template))
            if lane is None:
                lane = self.lanes[(setup, template)] = LaneFold(setup, template)
            return lane.apply(ev, sym, line, ts)
        return None

    def _lanes(self, line: dict[str, Any]) -> None:
        self.running = {}
        for item in line.get("lanes") or []:
            setup = item.get("setup_type") or BOT_SETUP_FIRST_PULLBACK
            template = item.get("template") or SETUP_TEMPLATE_DEFAULT_ID
            self.meta[(setup, template)] = {"id": template, "rev": item.get("rev"),
                                            "name": item.get("name") or template,
                                            "params_hash": item.get("params_hash")}
            self.running[setup] = self.running.get(setup, 0) + 1
            if item.get("playing"):
                self.playing[setup] = template

    # -- what the moment shows ---------------------------------------------------------
    def gap(self) -> dict[str, Any] | None:
        """Why the journal holds nothing for the moment, or None."""
        first = self.day.first_ts
        if first is None:
            return {"reason": "no_record", "since": None, "until": None}
        if self.at is None or self.k == 0:
            return {"reason": "before_record", "since": None, "until": first}
        if self.beating and self.last_line_ts is not None and self.at - self.last_line_ts > EYES_PLAYBACK_GAP_SEC:
            until = self.day.ts[self.k] if self.k < len(self.day.ts) else None
            return {"reason": "not_running", "since": self.last_line_ts, "until": until}
        return None

    def _running(self, setup: str) -> int:
        if self.running is not None:
            return self.running.get(setup, 0)
        return sum(1 for (s, _t) in self.lanes if s == setup)

    def body(self, levels: dict[str, Any], window_of: WindowOf | None = None) -> dict[str, Any]:
        """``setups``, ``rows``, ``proposals`` and ``universe`` at the folded moment -- the live
        board's shape; nothing proposes (a replay desk), and a gap draws nothing."""
        from setup_scanner.detectors import window_state

        at = float(self.at or 0.0)
        gap = self.gap()
        setups: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        proposals: list[dict[str, Any]] = []
        for setup in BOT_SCANNER_SETUPS:
            template = self.playing.get(setup)
            lane = self.lanes.get((setup, template)) if template else None
            recorded = gap is None and self._running(setup) > 0
            win = window_of(setup, template) if window_of is not None else None
            counts = {k: 0 for k in COUNT_KEYS}
            if recorded:
                counts = lane.counts(len(self.universe)) if lane is not None else {**counts,
                                                                                    "watching": len(self.universe)}
            level = int((levels.get("levels") or {}).get(setup) or 0)
            setups.append({
                "id": setup, "level": level, "chosen": levels.get("chosen") == setup, "proposing": False,
                "template": self.meta.get((setup, template)) if template else None,
                "templates_watched": self._running(setup),
                "window": ({"start": win[0], "end": win[1], "state": window_state(at, win[0], win[1])} if win
                           else {"start": None, "end": None, "state": None}),
                "counts": counts, "recorded": recorded,
            })
            if recorded and lane is not None:
                rows += lane.board_rows(at, self.last)
                proposals += [p for p in lane.proposals.values() if p.get("status") == "open"]
        return {"proposing": False, "setups": setups, "rows": rows, "proposals": proposals,
                "universe": len(self.universe) if gap is None else 0,
                "universe_symbols": sorted(self.universe) if gap is None else []}

    def journal_view(self) -> dict[str, Any]:
        return {"path": str(self.day.path), "exists": self.day.exists, "lines": len(self.day.lines),
                "folded": self.k, "first_ts": self.day.first_ts, "last_ts": self.day.last_ts,
                "line_ts": self.last_line_ts, "skipped": self.day.skipped}


def template_window(store: Any) -> WindowOf:
    """``window_of`` over a template store: the template that played then, else the one in play now."""

    def window_of(setup: str, template_id: str | None) -> tuple[str, str] | None:
        from setup_scanner.detectors import window
        from setup_scanner.lane_params import lane_params

        try:
            t = next((t for t in store.templates(setup) if t.id == template_id and not t.error), None)
            return window(setup, lane_params(t or store.in_play(setup)).pattern)
        except Exception:
            logger.warning("eyes playback: no arming window for %s", setup, exc_info=True)
            return None

    return window_of


def board_at(path: Path, date: str, at: float, *, levels: dict[str, Any],
             window_of: WindowOf | None = None) -> dict[str, Any]:
    """One day's live journal folded to ``at``: the board body, its gap and the journal it read."""
    pb = Playback(JournalDay(path, date))
    pb.day.refresh()
    pb.advance(at)
    gap = pb.gap()
    return {"schema_version": EYES_SCHEMA_VERSION, "date": date, "at": at, "gap": gap,
            "note": gap_note(gap, date), "journal": pb.journal_view(), **pb.body(levels, window_of)}


def gap_note(gap: dict[str, Any] | None, date: str) -> str | None:
    """The stated absence the Sim desk shows instead of a board it does not have."""
    if gap is None:
        return None
    reason = gap.get("reason")
    if reason == "no_record":
        return f"Nova's eyes recorded nothing for {date}: there is no journal for that day."
    if reason == "before_record":
        return f"Nova's eyes' record for {date} starts at {clock(gap.get('until'))} ET."
    until = gap.get("until")
    to = f" until {clock(until)} ET" if until else ""
    return (f"Nova's eyes recorded nothing from {clock(gap.get('since'))} ET{to}: Nova was closed or its eyes "
            "were off. Nothing is carried across the gap.")
