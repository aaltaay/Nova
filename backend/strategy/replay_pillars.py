"""The Five Pillars of one symbol on a Sim replay desk (operator report, 2026-10-12).

Off the live edge the quote panel shows a past day, so the pillars grade that day's own board row
at the playhead -- the leaderboard store's recorded or rebuilt row (ADR 023) and its catalyst verdict
as known then (#498) -- never today's scanner caches, fundamentals or Contenders rank. On 2026-07-15
at 07:20 the panel graded today's GRML ($6.02, +16.4%, "#22 of the Contenders") over a replay where
GRML traded at $0.19, #98 on the rebuilt board.

A fact the row does not hold stays unknown and its pillar fails with that reason (a rebuilt row has
no float). A ``time_of_day_20`` RVOL is another measure than the desk's daily-average RVOL -- volume so
far over the same minute's 20-session average, never compared across bases -- so the pillar names it
and does not grade it against the daily threshold.

Owner: this module (no state). Reads ``leaderboard.playback.board_at``.
"""
from __future__ import annotations

from typing import Any

from constants_leaderboard import (
    LEADERBOARD_BOARD_AFTERHOURS,
    LEADERBOARD_BOARD_GAINERS,
    LEADERBOARD_BOARD_GAPPERS,
    LEADERBOARD_BOARD_LARGE_CAP,
    LEADERBOARD_BOARD_LOSERS,
    LEADERBOARD_BOARD_MARKET,
    LEADERBOARD_RVOL_BASIS_DAILY,
    LEADERBOARD_RVOL_BASIS_TOD,
)

# The live search order (``symbol_pillars.BOARD_ORDER``); a rebuilt day's ``market`` board is its Gainers.
REPLAY_BOARD_ORDER: tuple[str, ...] = (
    LEADERBOARD_BOARD_GAPPERS, LEADERBOARD_BOARD_GAINERS, LEADERBOARD_BOARD_MARKET, LEADERBOARD_BOARD_LOSERS,
    LEADERBOARD_BOARD_AFTERHOURS, LEADERBOARD_BOARD_LARGE_CAP,
)
# Why a replayed symbol has no grade: no board at the playhead (the gap's own reason), or not on it.
REPLAY_ABSENT_NOT_ON_BOARD = "not_on_board"


def board_row(symbol: str, board: dict[str, Any]) -> tuple[dict | None, str | None]:
    """The symbol's row on a ``board_at`` answer, first in ``REPLAY_BOARD_ORDER``, with its board's name."""
    boards = board.get("boards") or {}
    for name in REPLAY_BOARD_ORDER:
        for row in (boards.get(name) or {}).get("rows") or ():
            if str(row.get("symbol") or "").upper() == symbol:
                return row, name
    return None, None


def candidate(row: dict) -> dict:
    """The grader's candidate from a board row; every fact the row lacks stays None.

    ``rel_volume`` is the desk's daily-average RVOL only; a time-of-day RVOL rides as
    ``rvol_time_of_day``, which the RVOL pillar names and never grades.
    """
    basis = row.get("rvol_basis")
    rvol = row.get("rvol")
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "price": row.get("price"),
        "prev_close": row.get("prev_close"),
        "change_pct": row.get("change_pct"),
        "volume": row.get("volume"),
        "rel_volume": rvol if basis == LEADERBOARD_RVOL_BASIS_DAILY else None,
        "rvol_time_of_day": rvol if basis == LEADERBOARD_RVOL_BASIS_TOD else None,
        "float_shares": row.get("float_shares"),
        "float_contradicted": row.get("float_contradicted"),
        "shares_outstanding": row.get("shares_outstanding"),
        "has_news": row.get("has_news"),
        "catalyst": row.get("catalyst"),
    }


def replay_view(symbol: str, day: str, at: float, board: dict[str, Any]) -> tuple[dict | None, dict]:
    """``(candidate or None, replay)`` for the symbol on ``board`` -- the store's board at ``at``.

    ``replay`` says what the grade came from: the day, the playhead, the board minute and source
    (``recorded`` | ``reconstructed``), the board and the row's rank on it -- or, with no row, why
    (``absent``: the board's gap reason, else ``not_on_board``).
    """
    row, name = board_row(symbol, board)
    gap = board.get("gap") or {}
    replay = {
        "session_date": day,
        "at": float(at),
        "minute_ts": board.get("minute_ts"),
        "board_source": board.get("source"),
        "board": name,
        "board_rank": row.get("rank") if row else None,
        "rvol": row.get("rvol") if row else None,
        "rvol_basis": row.get("rvol_basis") if row else None,
        "absent": None if row else (gap.get("reason") or REPLAY_ABSENT_NOT_ON_BOARD),
    }
    return (candidate(row) if row else None), replay
