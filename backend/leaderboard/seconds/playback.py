"""A rebuilt day's Gappers at one playhead second: ``GET /api/leaderboard/{date}/seconds?at=`` (ADR 023 amendment
2026-10-13).

The list is the day's built file read at ``at`` (``build.list_at``); every other column is the stored rebuilt row of
that minute (``gappers``, else ``market``, else ``losers``), so ``rvol`` stays the minute's. ``has_news`` turns
true once the next minute's ``news_first_seen_ts`` is at or before the second; ``halted`` and ``catalyst`` are read
at the second as the minute board reads them at ``at``. Never after the playhead: a print at 07:45:01.3 is first
seen at 07:45:02.
"""
from __future__ import annotations

import math
from typing import Any

from constants_leaderboard import (
    LEADERBOARD_BOARD_GAPPERS,
    LEADERBOARD_BOARD_LOSERS,
    LEADERBOARD_BOARD_MARKET,
    LEADERBOARD_SECONDS_BOARD,
    LEADERBOARD_SECONDS_NONE,
    LEADERBOARD_SECONDS_READY,
    LEADERBOARD_SECONDS_SCHEMA_VERSION,
    LEADERBOARD_SOURCE_RECONSTRUCTED,
    LEADERBOARD_STATE_FROZEN,
    LEADERBOARD_STATE_REBUILT,
)
from leaderboard import catalyst_verdicts, halts as halt_log, playback as board_playback, store as board_store
from leaderboard.schema import ROW_COLUMNS
from leaderboard.seconds import build, inputs, job, store

BOARD = LEADERBOARD_SECONDS_BOARD
# The stored row a second's row takes its other columns from, first found first.
_BASE_BOARDS = (LEADERBOARD_BOARD_GAPPERS, LEADERBOARD_BOARD_MARKET, LEADERBOARD_BOARD_LOSERS)
# What a stock new to the list inside a minute takes from the next minute's row (it has none of its own).
_DAY_FACTS = ("exchange", "float_shares")
_JOB_FIELDS = ("status", "reason", "stage", "done", "total", "error", "summary")


def _stored(db, day: str, minute: int, symbols: list[str]) -> dict[str, dict[str, Any]]:
    """The symbols' stored rows of one minute, by symbol, the first of ``_BASE_BOARDS`` that holds each.

    One exact primary-key lookup per board: ``rows_at`` reads the whole day's rows to find one minute's."""
    out: dict[str, dict[str, Any]] = {}
    if not symbols:
        return out
    marks = ", ".join("?" for _ in symbols)
    for board in _BASE_BOARDS:
        for row in db.execute(
                f"SELECT {', '.join(ROW_COLUMNS)} FROM rows WHERE session_date = ? AND source = ? AND board = ?"
                f" AND minute_ts = ? AND symbol IN ({marks})",
                (day, LEADERBOARD_SOURCE_RECONSTRUCTED, board, int(minute), *symbols)).fetchall():
            out.setdefault(row["symbol"], dict(row))
    return out


def _row(listed: dict[str, Any], base: dict[str, Any] | None, later: dict[str, Any] | None,
         day: str, minute: int, second: int) -> dict[str, Any]:
    row: dict[str, Any] = {column: None for column in ROW_COLUMNS}
    if base is not None:
        row.update(base)
    elif later is not None:
        # Facts of the day, not of the minute; the next minute's rvol would count volume after the second.
        row.update({key: later.get(key) for key in _DAY_FACTS})
    row.update(session_date=day, minute_ts=minute, board=LEADERBOARD_BOARD_GAPPERS,
               source=LEADERBOARD_SOURCE_RECONSTRUCTED, **{key: listed[key] for key in (
                   "symbol", "rank", "price", "prev_close", "change_pct", "gap_pct", "volume")})
    seen = (later or {}).get("news_first_seen_ts")
    if not row.get("has_news") and seen is not None and float(seen) <= second:
        row.update(has_news=True, news_first_seen_ts=seen)
    row["second_ts"] = second
    return row


def answer(day: str, at: float) -> dict[str, Any]:
    state = job.status(day)
    out: dict[str, Any] = {"schema_version": LEADERBOARD_SECONDS_SCHEMA_VERSION, "date": day, "board": BOARD,
                           **{key: state.get(key) for key in _JOB_FIELDS}, "at": at, "second_ts": None,
                           "minute_ts": None, "state": None, "rows": []}
    if out["status"] != LEADERBOARD_SECONDS_READY:
        return out
    if not job.current(state, day):             # built from a rebuilt day since replaced: never its rows
        out.update(status=LEADERBOARD_SECONDS_NONE, reason=job.STALE)
        return out
    second = int(math.floor(float(at)))
    first, last = inputs.premarket_minutes(day)[0], inputs.frozen_minutes(day)[-1] + 60
    if not first <= second < last:
        return out
    minute = second - second % 60
    db = store.open_data(day, BOARD)
    if db is None:
        out["status"] = LEADERBOARD_SECONDS_NONE
        return out
    try:
        candidates = store.candidates_at(db, minute)
        seconds = store.seconds_between(db, [c.symbol for c in candidates], minute, second)
    finally:
        db.close()
    listed = build.list_at(second, candidates, seconds)
    symbols = {row["symbol"] for row in listed}
    with board_store.connect() as bdb:
        here = _stored(bdb, day, minute, sorted(symbols))
        later = _stored(bdb, day, minute + 60, sorted(symbols))
        checks = board_store.catalyst_checks(bdb, day)
        events = board_store.halt_events(bdb, day, until=second)
        catalysts = catalyst_verdicts.for_board(bdb, day, second, checks, events, symbols)
    rows = []
    for item in listed:
        symbol = item["symbol"]
        # A rebuilt day has no halt feed: true only while a logged halt is open, else unknown.
        halted = True if halt_log.halted_at(events, symbol, second) else None
        rows.append(board_playback.api_row(_row(item, here.get(symbol), later.get(symbol), day, minute, second),
                                           halted, catalysts.get(symbol)))
    out.update(second_ts=second, minute_ts=minute, rows=rows,
               state=LEADERBOARD_STATE_FROZEN if minute >= inputs.freeze_ts(day) else LEADERBOARD_STATE_REBUILT)
    return out
