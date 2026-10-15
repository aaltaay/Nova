"""Which stocks live HOD Momo would have watched on a rebuilt day, minute by minute.

Live, HOD Momo evaluates only its active set -- at most ``HOD_MOMO_ACTIVE_SET_CAPACITY`` stocks with an L1 line,
admitted from the Gappers, Gainers and After Hours lists by ``hod_momo_active.build_active_set`` (ADR 008). A
rebuilt day's boards are those lists as they stood each minute (``market`` in the Gainers place, cut to the live
scan's ``HOD_MOMO_REBUILD_GAINER_ROWS``), so the same function over them is the set that minute. The reserved block
(the bot's stocks, the hot list, Former Momo) was the operator's that day and is not on file: it stays empty.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from constants_hod_momo import HOD_MOMO_REBUILD_GAINER_ROWS
from constants_leaderboard import (
    LEADERBOARD_BOARD_AFTERHOURS,
    LEADERBOARD_BOARD_GAPPERS,
    LEADERBOARD_BOARD_MARKET,
    LEADERBOARD_SOURCE_RECONSTRUCTED,
)
from leaderboard import store as board_store

_BOARDS = (LEADERBOARD_BOARD_GAPPERS, LEADERBOARD_BOARD_MARKET, LEADERBOARD_BOARD_AFTERHOURS)
_QUERY = ("SELECT minute_ts, board, symbol, rank, change_pct, prev_close FROM rows"
          " WHERE session_date = ? AND source = ? AND board IN (?, ?, ?)"
          " AND (board != ? OR rank <= ?) ORDER BY minute_ts, board, rank, symbol")


@dataclass
class WatchPlan:
    """The day's boards as HOD Momo would have read them."""

    boards: dict[int, dict[str, list[dict]]] = field(default_factory=dict)   # minute -> board -> rows
    prev_close: dict[str, float] = field(default_factory=dict)
    fingerprint: str = ""

    def active_minutes(self) -> dict[str, list[int]]:
        """``{symbol: [minute, ...]}``: the minutes each stock held an L1 line, by ``build_active_set``."""
        import hod_momo_active as active

        active.clear_session_state()
        out: dict[str, list[int]] = defaultdict(list)
        try:
            for minute in sorted(self.boards):
                lists = self.boards[minute]
                snap = active.build_active_set(
                    gapper_rows=lists.get(LEADERBOARD_BOARD_GAPPERS, []),
                    gainer_rows=lists.get(LEADERBOARD_BOARD_MARKET, []),
                    afterhours_rows=lists.get(LEADERBOARD_BOARD_AFTERHOURS, []),
                    now=float(minute),
                )
                for symbol in snap.active:
                    out[symbol].append(minute)
        finally:
            active.clear_session_state()
        return dict(out)


def _args(day: str) -> tuple:
    return (day, LEADERBOARD_SOURCE_RECONSTRUCTED, *_BOARDS, LEADERBOARD_BOARD_MARKET, HOD_MOMO_REBUILD_GAINER_ROWS)


def fingerprint(db, day: str) -> str | None:
    """A digest of the boards a build reads, or None when the day has no rebuilt boards."""
    digest = hashlib.sha256()
    found = False
    for row in db.execute(_QUERY, _args(day)):
        found = True
        digest.update(repr(tuple(row)).encode())
    return digest.hexdigest() if found else None


def plan(day: str, database: Path | None = None) -> WatchPlan | None:
    """The day's rebuilt boards; None when the store holds none."""
    db = board_store.read_only(database)
    if db is None:
        return None
    try:
        out = WatchPlan()
        digest = hashlib.sha256()
        for row in db.execute(_QUERY, _args(day)):
            digest.update(repr(tuple(row)).encode())
            minute, board, symbol, rank, change, prev_close = row
            out.boards.setdefault(int(minute), {}).setdefault(str(board), []).append(
                {"symbol": str(symbol), "rank": rank, "change_pct": change})
            if prev_close and float(prev_close) > 0:
                out.prev_close.setdefault(str(symbol), float(prev_close))
        if not out.boards:
            return None
        out.fingerprint = digest.hexdigest()
        return out
    finally:
        db.close()
