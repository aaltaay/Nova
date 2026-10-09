"""The Sim eyes' setups that ended (ADR 052 amendment, #815): what the chart's past setups are on a Sim replay.

The lines the replay's lanes write (``setup_scanner/lane_journal.py``) are folded into episodes as they are written
(``eyes.episodes``, the fold the live journal's past setups use), the setups in play's and the 5-minute strategies'.
The fold is the replay's own: a rebuild (a rewind, a template change, another replay) starts a new one and replays
the lanes up to the playhead, so it never holds a line from after it. The day's journal file is never read here: on
a replay it holds the lines of every play of the day, and a rebuild journals nothing it passed.

``view`` is what the Sim eyes publish for the loaded symbol: the episodes, the replay's one-minute bars and the
moment they stand at. ``stock_read.past_setups.replay`` cuts the bars at that moment before it measures what price
did next. ``past_view`` is the loop's answer, never one from after the playhead.

Owner: ``eyes.sim_eyes`` (worker-owned fold; invalidation: every rebuild). Pure.
"""
from __future__ import annotations

from typing import Any

from constants_setups import SETUPS_5M_BAR_SEC, SETUPS_5M_TEMPLATE_ID
from eyes.episodes import EpisodeFold
from eyes.sim_board import ahead
from eyes.sim_target import LANE_KINDS


class PastFold:
    """One rebuild's fold: the setups in play's lines (``False``) and the 5-minute ones' (``True``)."""

    def __init__(self) -> None:
        self.folds = {False: EpisodeFold(), True: EpisodeFold(SETUPS_5M_TEMPLATE_ID, SETUPS_5M_BAR_SEC)}
        self.lines = 0

    def apply(self, line: dict[str, Any]) -> None:
        for fold in self.folds.values():
            fold.apply(line)
        self.lines += 1

    def view(self, symbol: str, bars: list, at: float, date: str) -> dict[str, Any]:
        return {"symbol": symbol, "date": date, "at": at, "lines": self.lines, "bars": bars,
                "episodes": {five: fold.episodes(symbol) for five, fold in self.folds.items()}}


def past_view(target: dict | None, view: dict, symbol: str) -> dict[str, Any] | None:
    """The loaded symbol's setups that ended as published; ``{"pending": why}`` while nothing at the playhead can be
    shown yet; ``None`` when the desk follows no loaded replay of ``symbol``."""
    if target is None or target["kind"] not in LANE_KINDS or str(target.get("symbol") or "").upper() != symbol:
        return None
    if view.get("loading") or view.get("error"):
        return {"pending": view.get("error") or "the Sim eyes are reading the replay"}
    if ahead(target, view):
        return {"pending": "the Sim eyes are catching up to the playhead after a rewind"}
    return view.get("past") or {"pending": "the Sim eyes are reading the replay"}
