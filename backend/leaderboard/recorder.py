"""Always-on leaderboard recorder (ADR 022): one board snapshot per list per minute.

No button: the loop runs whenever the backend runs, and records 04:00-20:00 ET
on exchange days. Each minute it writes a heartbeat (``minutes``), one
``coverage`` row per board and the board's rows exactly as the desk served
them (``scanner_surface.surface_rows``: blocklist out, reference columns in).
With the IBKR feed down it writes the heartbeat and ``feed_down`` coverage but
no rows -- a stale board is never recorded as a live one. Everything is
enqueued; ``leaderboard.queue`` writes from a worker thread (ADR 010).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from constants_leaderboard import (
    LEADERBOARD_RECORD_END_MIN_ET,
    LEADERBOARD_RECORD_INTERVAL_SEC,
    LEADERBOARD_RECORD_SETTLE_SEC,
    LEADERBOARD_RECORD_START_MIN_ET,
    LEADERBOARD_RECORDED_BOARDS,
    LEADERBOARD_ROWS_PER_BOARD_MAX,
    LEADERBOARD_RUN_STOP_SHUTDOWN,
    LEADERBOARD_SOURCE_RECORDED,
    LEADERBOARD_STATE_FEED_DOWN,
    LEADERBOARD_STATE_FROZEN,
    LEADERBOARD_STATE_LIVE,
    LEADERBOARD_STATE_UNAVAILABLE,
)
from constants_nova_os import NOVA_OS_NYSE_HOLIDAYS
from leaderboard import queue
from leaderboard.rows import ET, from_desk_row, headline_ts, session_date_for

logger = logging.getLogger(__name__)

_RECORDED_STATES = (LEADERBOARD_STATE_LIVE, LEADERBOARD_STATE_FROZEN)

_run_id: str | None = None
_running = False
_last_minute_ts: int | None = None
# (session_date, symbol) -> earliest headline time seen by that minute.
_news_first_seen: dict[tuple[str, str], float] = {}


def exchange_day(when: datetime) -> bool:
    return when.weekday() < 5 and when.date().isoformat() not in NOVA_OS_NYSE_HOLIDAYS


def in_record_window(minute_ts: int) -> bool:
    when = datetime.fromtimestamp(minute_ts, ET)
    minutes = when.hour * 60 + when.minute
    return exchange_day(when) and LEADERBOARD_RECORD_START_MIN_ET <= minutes <= LEADERBOARD_RECORD_END_MIN_ET


def _first_seen(session_date: str, symbol: str, headline: float | None) -> float | None:
    key = (session_date, symbol)
    if headline is not None:
        known = _news_first_seen.get(key)
        if known is None or headline < known:
            _news_first_seen[key] = headline
    return _news_first_seen.get(key)


def build_minute(
    minute_ts: int,
    tables: dict[str, tuple[list[dict], str]],
    *,
    feed_live: bool,
    halt_feed_ok: bool,
    run_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """Rows, coverage and the heartbeat for one minute. Pure apart from the news memo.

    ``tables`` maps board -> (surfaced rows in the desk's order, table state).
    Recorded ranks are the desk's own order; a bad row is skipped, not guessed.
    """
    session_date = session_date_for(minute_ts)
    rows: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for board in LEADERBOARD_RECORDED_BOARDS:
        board_rows, table_state = tables.get(board, ([], LEADERBOARD_STATE_UNAVAILABLE))
        state = table_state if table_state in _RECORDED_STATES + (LEADERBOARD_STATE_UNAVAILABLE,) else LEADERBOARD_STATE_UNAVAILABLE
        if not feed_live:
            state = LEADERBOARD_STATE_FEED_DOWN
        kept: list[dict[str, Any]] = []
        if state in _RECORDED_STATES:
            for position, raw in enumerate(board_rows[:LEADERBOARD_ROWS_PER_BOARD_MAX], start=1):
                symbol = str(raw.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                try:
                    kept.append(from_desk_row(
                        raw, minute_ts=minute_ts, board=board, rank=position,
                        news_first_seen_ts=_first_seen(session_date, symbol, headline_ts(raw, minute_ts)),
                    ))
                except (TypeError, ValueError):
                    logger.debug("leaderboard: skipped a malformed %s row %r", board, symbol, exc_info=True)
        rows.extend(kept)
        coverage.append({
            "session_date": session_date, "minute_ts": minute_ts,
            "source": LEADERBOARD_SOURCE_RECORDED, "board": board,
            "state": state, "row_count": len(kept), "run_id": run_id,
        })
    minute = {
        "session_date": session_date, "minute_ts": minute_ts, "run_id": run_id,
        "feed_live": 1 if feed_live else 0, "halt_feed_ok": 1 if halt_feed_ok else 0,
    }
    return {"rows": rows, "coverage": coverage, "minutes": [minute]}


def _live_tables() -> dict[str, tuple[list[dict], str]]:
    from ibkr import scanner_session as _ss
    from runtime_state import get_runtime_state
    from scanner_surface import surface_rows

    state = get_runtime_state()
    sources = {
        _ss.TABLE_GAPPERS: (state.gapper_cache, state.gapper_table),
        _ss.TABLE_GAINERS: (state.gainer_cache, state.gainer_table),
        _ss.TABLE_LOSERS: (state.loser_cache, state.loser_table),
        _ss.TABLE_AFTERHOURS: (state.afterhours_cache, state.afterhours_table),
        _ss.TABLE_LARGE_CAP: (state.large_cap_cache, state.large_cap_table),
    }
    out: dict[str, tuple[list[dict], str]] = {}
    for board, (rows, meta) in sources.items():
        try:
            out[board] = (surface_rows(list(rows or []), board), getattr(meta, "state", LEADERBOARD_STATE_UNAVAILABLE))
        except Exception:
            logger.warning("leaderboard: could not surface the %s board", board, exc_info=True)
            out[board] = ([], LEADERBOARD_STATE_UNAVAILABLE)
    return out


def _feed_live() -> bool:
    try:
        from ibkr import client as _client

        return bool(_client.is_connected())
    except Exception:
        logger.debug("leaderboard: IBKR connection check failed", exc_info=True)
        return False


def _halt_feed_ok() -> bool:
    try:
        from ibkr import nasdaq_halt_feed

        return nasdaq_halt_feed.desk_snapshot()["feed"]["status"] in ("ok", "empty")
    except Exception:
        logger.debug("leaderboard: halt feed status check failed", exc_info=True)
        return False


def record_minute(minute_ts: int) -> int:
    """Snapshot the live desk for ``minute_ts`` and enqueue it. Returns rows enqueued."""
    global _last_minute_ts
    if _run_id is None or not in_record_window(minute_ts):
        return 0
    batch = build_minute(
        minute_ts, _live_tables(), feed_live=_feed_live(), halt_feed_ok=_halt_feed_ok(), run_id=_run_id,
    )
    for kind, items in batch.items():
        queue.enqueue(kind, items)
    _last_minute_ts = minute_ts
    day = session_date_for(minute_ts)
    for stale in [key for key in _news_first_seen if key[0] != day]:
        _news_first_seen.pop(stale, None)
    return len(batch["rows"])


def _run_op(fn_name: str, *args: Any) -> None:
    from leaderboard import store

    try:
        with store.connect() as db:
            getattr(store, fn_name)(db, *args)
    except Exception:
        logger.warning("leaderboard: run bookkeeping %s failed", fn_name, exc_info=True)


def next_boundary(now: float) -> int:
    return (int(now) // LEADERBOARD_RECORD_INTERVAL_SEC + 1) * LEADERBOARD_RECORD_INTERVAL_SEC


async def run() -> None:
    """The recorder loop. Cancelled at shutdown, which stamps the run as closed."""
    global _run_id, _running
    _run_id = uuid.uuid4().hex
    started = time.time()
    await asyncio.to_thread(_run_op, "start_run", _run_id, started)
    _running = True
    logger.info("leaderboard: recorder run %s started", _run_id)
    try:
        while True:
            boundary = next_boundary(time.time())
            await asyncio.sleep(max(0.0, boundary + LEADERBOARD_RECORD_SETTLE_SEC - time.time()))
            try:
                record_minute(boundary)
                await asyncio.to_thread(_run_op, "beat_run", _run_id, time.time())
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("leaderboard: minute %s snapshot failed", boundary)
    except asyncio.CancelledError:
        _running = False
        try:
            queue.flush_blocking()
            _run_op("stop_run", _run_id, time.time(), LEADERBOARD_RUN_STOP_SHUTDOWN)
        except Exception:
            logger.warning("leaderboard: shutdown bookkeeping failed", exc_info=True)
        raise
    finally:
        _running = False


def status() -> dict[str, Any]:
    """``/api/ibkr/status`` ``leaderboard_recorder``: quiet unless the store cannot be written."""
    health = queue.health()
    return {
        "recording": bool(_running and _last_minute_ts is not None and in_record_window(_last_minute_ts)),
        "ok": bool(health["ok"]),
        "error": health["error"],
        "since": health["since"],
        "run_id": _run_id,
    }


def reset_for_tests() -> None:
    global _run_id, _running, _last_minute_ts
    _run_id = None
    _running = False
    _last_minute_ts = None
    _news_first_seen.clear()


def start_for_tests(run_id: str = "test-run") -> None:
    global _run_id
    _run_id = run_id
