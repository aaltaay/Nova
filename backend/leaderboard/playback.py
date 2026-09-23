"""Reading the leaderboard back (ADR 023): the board at a moment, its gaps, the days.

Never after the playhead: a recorded snapshot stamped ``m`` was taken within
``LEADERBOARD_RECORD_SETTLE_SEC`` after ``m``, so the playhead sees it only
from ``m + settle``; a rebuilt minute ``m`` is built from bars closed by ``m``.
Never across a gap: a playhead in an unrecorded or feed-down stretch gets no
board, just the reason and the stretch's bounds.
"""
from __future__ import annotations

import time
from datetime import date as date_cls, datetime, time as time_cls
from typing import Any

from constants_leaderboard import (
    LEADERBOARD_BOARD_GAINERS,
    LEADERBOARD_BOARD_MARKET,
    LEADERBOARD_GAP_FEED_DOWN,
    LEADERBOARD_GAP_NOT_RECORDED,
    LEADERBOARD_GAP_NOT_RUNNING,
    LEADERBOARD_GAP_OUTSIDE_SESSION,
    LEADERBOARD_RECORD_END_MIN_ET,
    LEADERBOARD_RECORD_SETTLE_SEC,
    LEADERBOARD_RECORD_START_MIN_ET,
    LEADERBOARD_RUN_STOP_SHUTDOWN,
    LEADERBOARD_SCHEMA_VERSION,
    LEADERBOARD_SOURCE_RECONSTRUCTED,
    LEADERBOARD_SOURCE_RECORDED,
)
from leaderboard import halts as halt_log
from leaderboard import store
from leaderboard.ranking import LEADERS_RULES, rank_rows
from leaderboard.rows import ET


def session_bounds(day: str) -> tuple[int, int]:
    d = date_cls.fromisoformat(day)
    start = datetime.combine(d, time_cls(0, 0), tzinfo=ET).timestamp() + LEADERBOARD_RECORD_START_MIN_ET * 60
    end = datetime.combine(d, time_cls(0, 0), tzinfo=ET).timestamp() + LEADERBOARD_RECORD_END_MIN_ET * 60
    return int(start), int(end)


def _minute_for(at: float, source: str) -> int:
    effective = at - (LEADERBOARD_RECORD_SETTLE_SEC if source == LEADERBOARD_SOURCE_RECORDED else 0.0)
    return int(effective // 60) * 60


def _spans(minutes: list[int]) -> list[list[int]]:
    """Contiguous covered minutes as half-open [start, end) spans."""
    out: list[list[int]] = []
    for m in minutes:
        if out and out[-1][1] == m:
            out[-1][1] = m + 60
        else:
            out.append([m, m + 60])
    return out


def _run_stop(db: Any, minute_ts: int | None) -> str | None:
    """How the run that wrote ``minute_ts`` ended: shutdown, unexpected, or still running."""
    if minute_ts is None:
        return None
    for run in store.runs_between(db, minute_ts, minute_ts):
        if run.get("stopped_ts") is not None:
            return "shutdown" if run.get("stop_reason") == LEADERBOARD_RUN_STOP_SHUTDOWN else "unexpected"
        return "unexpected" if run.get("last_beat_ts", 0) < time.time() - 180 else None
    return None


def _recorded_gaps(db: Any, day: str, minutes: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
    open_ts, close_ts = session_bounds(day)
    horizon = min(close_ts + 60, int(now) // 60 * 60)
    if not minutes:
        return [{"start": open_ts, "end": horizon, "reason": LEADERBOARD_GAP_NOT_RECORDED, "stop": None}] if horizon > open_ts else []
    gaps: list[dict[str, Any]] = []
    cursor = open_ts
    last_minute: int | None = None
    for row in minutes:
        m = int(row["minute_ts"])
        if m > cursor:
            gaps.append({"start": cursor, "end": m, "reason": LEADERBOARD_GAP_NOT_RUNNING, "stop": _run_stop(db, last_minute)})
        if not row["feed_live"]:
            if gaps and gaps[-1]["reason"] == LEADERBOARD_GAP_FEED_DOWN and gaps[-1]["end"] == m:
                gaps[-1]["end"] = m + 60
            else:
                gaps.append({"start": m, "end": m + 60, "reason": LEADERBOARD_GAP_FEED_DOWN, "stop": None})
        cursor = m + 60
        last_minute = m
    # A tail within two minutes of now is the recording still going, not a gap.
    if horizon - cursor > 120:
        gaps.append({"start": cursor, "end": horizon, "reason": LEADERBOARD_GAP_NOT_RUNNING, "stop": _run_stop(db, last_minute)})
    return gaps


def coverage(day: str, source: str | None = None, *, now: float | None = None) -> dict[str, Any]:
    now_ts = time.time() if now is None else float(now)
    open_ts, close_ts = session_bounds(day)
    with store.connect() as db:
        chosen = source or _default_source(db, day)
        if chosen == LEADERBOARD_SOURCE_RECORDED:
            minutes = store.minutes_for_day(db, day)
            spans = _spans([int(r["minute_ts"]) for r in minutes if r["feed_live"]])
            gaps = _recorded_gaps(db, day, minutes, now_ts)
        else:
            covered = store.coverage_minutes(db, day, LEADERBOARD_SOURCE_RECONSTRUCTED)
            spans = _spans(covered)
            gaps = _between(spans, open_ts, close_ts + 60, LEADERBOARD_GAP_NOT_RECORDED)
    return {"date": day, "source": chosen, "session_open": open_ts, "session_close": close_ts, "spans": spans, "gaps": gaps}


def _between(spans: list[list[int]], start: int, end: int, reason: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = start
    for a, b in spans:
        if a > cursor:
            out.append({"start": cursor, "end": a, "reason": reason, "stop": None})
        cursor = max(cursor, b)
    if end > cursor:
        out.append({"start": cursor, "end": end, "reason": reason, "stop": None})
    return out


def _default_source(db: Any, day: str) -> str:
    if store.has_source(db, day, LEADERBOARD_SOURCE_RECORDED):
        return LEADERBOARD_SOURCE_RECORDED
    if store.has_source(db, day, LEADERBOARD_SOURCE_RECONSTRUCTED):
        return LEADERBOARD_SOURCE_RECONSTRUCTED
    # Today with nothing written yet is still the recorded day being built.
    return LEADERBOARD_SOURCE_RECORDED


def _api_row(row: dict[str, Any], halted: bool | None) -> dict[str, Any]:
    out = {key: value for key, value in row.items() if key != "session_date"}
    has_news = out.get("has_news")
    out["has_news"] = None if has_news is None else bool(has_news)
    out["halted"] = halted
    return out


def _gap_at(gaps: list[dict[str, Any]], at: float) -> dict[str, Any] | None:
    for gap in gaps:
        if gap["start"] <= at < gap["end"]:
            return gap
    return None


def board_at(day: str, at: float, source: str | None = None, *, now: float | None = None) -> dict[str, Any]:
    """The board at ``at`` (epoch s) on ``day``, never after it and never across a gap."""
    now_ts = time.time() if now is None else float(now)
    open_ts, close_ts = session_bounds(day)
    base: dict[str, Any] = {
        "schema_version": LEADERBOARD_SCHEMA_VERSION, "date": day, "at": at,
        "minute_ts": None, "covered": False, "gap": None, "boards": {},
        "leaders": {"board": None, "symbols": [], "rules": LEADERS_RULES.to_dict()},
    }
    with store.connect() as db:
        chosen = source or _default_source(db, day)
        base["source"] = chosen
        if at < open_ts or at >= close_ts + 60:
            base["gap"] = {"reason": LEADERBOARD_GAP_OUTSIDE_SESSION, "start": None, "end": None, "stop": None}
            return base
        minute = _minute_for(at, chosen)
        leaders_board = LEADERBOARD_BOARD_GAINERS
        if chosen == LEADERBOARD_SOURCE_RECORDED:
            beat = store.minute_row(db, day, minute)
            if beat is None and now_ts - at < 150:
                # The newest minute may still be in the write queue: the one
                # before it is the board as of now, not a gap.
                previous = store.minute_row(db, day, minute - 60)
                if previous is not None:
                    minute, beat = minute - 60, previous
            if beat is None or not beat["feed_live"]:
                gaps = _recorded_gaps(db, day, store.minutes_for_day(db, day), now_ts)
                base["gap"] = _gap_at(gaps, at) or {
                    "reason": LEADERBOARD_GAP_NOT_RUNNING if beat is None else LEADERBOARD_GAP_FEED_DOWN,
                    "start": minute, "end": minute + 60, "stop": None,
                }
                return base
            halt_feed_ok = bool(beat["halt_feed_ok"])
        else:
            leaders_board = LEADERBOARD_BOARD_MARKET
            covered = store.coverage_minutes(db, day, chosen)
            if minute not in set(covered):
                gaps = _between(_spans(covered), open_ts, close_ts + 60, LEADERBOARD_GAP_NOT_RECORDED)
                base["gap"] = _gap_at(gaps, at) or {
                    "reason": LEADERBOARD_GAP_NOT_RECORDED, "start": minute, "end": minute + 60, "stop": None,
                }
                return base
            halt_feed_ok = False
        states = store.coverage_at(db, day, chosen, minute)
        rows = store.rows_at(db, day, chosen, minute)
        events = store.halt_events(db, day, until=minute)
    boards: dict[str, dict[str, Any]] = {
        entry["board"]: {"state": entry["state"], "rows": []} for entry in states
    }
    for row in rows:
        halted: bool | None = True if halt_log.halted_at(events, row["symbol"], minute) else (False if halt_feed_ok else None)
        boards.setdefault(row["board"], {"state": None, "rows": []})["rows"].append(_api_row(row, halted))
    leaders = rank_rows(boards.get(leaders_board, {}).get("rows", []), LEADERS_RULES)
    base.update({
        "minute_ts": minute, "covered": True, "boards": boards,
        "leaders": {"board": leaders_board, "symbols": [r["symbol"] for r in leaders], "rules": LEADERS_RULES.to_dict()},
    })
    return base


def days(limit: int) -> dict[str, Any]:
    out: dict[str, dict[str, Any]] = {}
    ok, error = True, None
    try:
        with store.connect() as db:
            for row in store.days(db, limit):
                entry = out.setdefault(row["session_date"], {"date": row["session_date"], "recorded": None, "reconstructed": None})
                summary = {"minutes": row["minutes"], "first_ts": row["first_ts"], "last_ts": row["last_ts"]}
                if row["source"] == LEADERBOARD_SOURCE_RECORDED:
                    summary["boards"] = sorted(set((row.get("boards") or "").split(","))) if row.get("boards") else []
                entry[row["source"]] = summary
    except Exception as exc:  # the store is unreadable: say so, never a 500
        ok, error = False, f"{type(exc).__name__}: {exc}"
    listed = sorted(out.values(), key=lambda d: d["date"], reverse=True)[: int(limit)]
    return {
        "schema_version": LEADERBOARD_SCHEMA_VERSION,
        "store": {"path": str(store.path()), "ok": ok, "error": error},
        "days": listed,
    }


def halts(day: str, until: float | None = None) -> dict[str, Any]:
    with store.connect() as db:
        events = store.halt_events(db, day, until=until)
    return {"date": day, "events": events}
