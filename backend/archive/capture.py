"""
Loss-aware local capture APIs for Nova OS P6.

Write path into ``archive.db``. Callers should treat failures as non-fatal for
live UI (log + gap marker) so a disk issue never blanks the quote panel.

``record_l2_snapshot`` is ready for a changed-book hook from ``ibkr/depth``;
wiring that hook is deferred until write-volume is benchmarked against the
existing 1 Hz continuous sampler (see package docstring TODO).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from archive import db as archive_db
from constants import (
    ARCHIVE_COUNTER_BARS_1D,
    ARCHIVE_COUNTER_BARS_1M,
    ARCHIVE_COUNTER_GAPS,
    ARCHIVE_COUNTER_INCOMPLETE_WINDOWS,
    ARCHIVE_COUNTER_L2_SNAPSHOTS,
    ARCHIVE_COUNTER_TAPE_RECEIVED,
    ARCHIVE_SOURCE_IBKR,
    ARCHIVE_STREAM_BARS_1D,
    ARCHIVE_STREAM_BARS_1M,
    ARCHIVE_STREAM_L2,
    ARCHIVE_STREAM_TAPE,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# Optional in-process L2 snapshot store until a dedicated table is justified.
_L2_STUB_ROWS: list[dict[str, Any]] = []


def session_date_for_ts(ts: float | None = None) -> str:
    """Calendar date in America/New_York for compaction partitioning."""
    when = datetime.fromtimestamp(ts if ts is not None else time.time(), tz=_ET)
    return when.strftime("%Y-%m-%d")


def bump_counter(name: str, delta: int = 1) -> int:
    """Increment a named integrity counter; returns the new value."""
    now = time.time()
    conn = archive_db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO integrity_counters (name, value, updated_ts)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                value = value + excluded.value,
                updated_ts = excluded.updated_ts
            """,
            (name, int(delta), now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT value FROM integrity_counters WHERE name = ?", (name,)
        ).fetchone()
        return int(row["value"] if row else delta)
    finally:
        conn.close()


def get_counter(name: str) -> int:
    conn = archive_db.get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM integrity_counters WHERE name = ?", (name,)
        ).fetchone()
        return int(row["value"]) if row else 0
    finally:
        conn.close()


def record_bar(
    *,
    symbol: str,
    ts: float,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 0.0,
    timeframe: str = "1m",
    source: str = ARCHIVE_SOURCE_IBKR,
    session_date: str | None = None,
) -> None:
    """Persist one OHLC bar (``timeframe`` is ``1m`` or ``1d``)."""
    symbol = symbol.upper()
    day = session_date or session_date_for_ts(ts)
    if timeframe == "1d":
        table = "bars_1d"
        counter = ARCHIVE_COUNTER_BARS_1D
        stream = ARCHIVE_STREAM_BARS_1D
    elif timeframe == "1m":
        table = "bars_1m"
        counter = ARCHIVE_COUNTER_BARS_1M
        stream = ARCHIVE_STREAM_BARS_1M
    else:
        raise ValueError(f"unsupported bar timeframe: {timeframe}")

    conn = archive_db.get_connection()
    try:
        conn.execute(
            f"""
            INSERT INTO {table}
                (symbol, ts, open, high, low, close, volume, source, session_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, ts, source) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                session_date = excluded.session_date
            """,
            (symbol, float(ts), float(open_), float(high), float(low),
             float(close), float(volume), source, day),
        )
        conn.commit()
    finally:
        conn.close()
    bump_counter(counter)
    _ = stream  # documented stream name for gap markers


def record_tape_print(
    *,
    symbol: str,
    ts: float,
    price: float,
    size: float,
    exchange: str = "",
    conditions: str = "",
    side: str | None = None,
    bid: float | None = None,
    ask: float | None = None,
    seq: int | None = None,
    receive_ts: float | None = None,
    source: str = ARCHIVE_SOURCE_IBKR,
    session_date: str | None = None,
) -> None:
    """Persist one IBKR (or other) time & sales print."""
    symbol = symbol.upper()
    recv = receive_ts if receive_ts is not None else time.time()
    day = session_date or session_date_for_ts(ts)
    conn = archive_db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO tape_ibkr
                (symbol, ts, price, size, exchange, conditions, side,
                 bid, ask, seq, receive_ts, source, session_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol, float(ts), float(price), float(size),
                exchange or "", conditions or "", side,
                bid, ask, seq, float(recv), source, day,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    bump_counter(ARCHIVE_COUNTER_TAPE_RECEIVED)


def record_gap(
    *,
    stream: str,
    start_ts: float,
    end_ts: float,
    symbol: str | None = None,
    reason: str = "",
    session_date: str | None = None,
) -> None:
    """Mark an explicit missing window (loss-aware integrity)."""
    marked = time.time()
    day = session_date or session_date_for_ts(start_ts)
    conn = archive_db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO capture_gaps
                (stream, symbol, start_ts, end_ts, reason, marked_ts, session_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stream,
                symbol.upper() if symbol else None,
                float(start_ts),
                float(end_ts),
                reason or "",
                marked,
                day,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    bump_counter(ARCHIVE_COUNTER_GAPS)


def mark_incomplete_window(
    *,
    stream: str,
    start_ts: float,
    end_ts: float,
    symbol: str | None = None,
    note: str = "",
    session_date: str | None = None,
) -> None:
    """Flag a session window that must not be treated as complete for trim."""
    marked = time.time()
    day = session_date or session_date_for_ts(start_ts)
    conn = archive_db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO incomplete_windows
                (stream, symbol, start_ts, end_ts, note, marked_ts, session_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stream,
                symbol.upper() if symbol else None,
                float(start_ts),
                float(end_ts),
                note or "",
                marked,
                day,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    bump_counter(ARCHIVE_COUNTER_INCOMPLETE_WINDOWS)


def record_l2_snapshot(
    *,
    symbol: str,
    ts: float,
    bids: list[dict[str, Any]] | None = None,
    asks: list[dict[str, Any]] | None = None,
    source: str = ARCHIVE_SOURCE_IBKR,
    session_date: str | None = None,
) -> None:
    """
    Stub for changed-book L2 capture.

    TODO(P6 follow-up): wire from ``ibkr/depth`` on book change (not only the
    1 Hz continuous sampler). Until then, rows stay in-memory for tests and
    bump the integrity counter so the capture surface is callable.
    """
    symbol = symbol.upper()
    day = session_date or session_date_for_ts(ts)
    _L2_STUB_ROWS.append({
        "symbol": symbol,
        "ts": float(ts),
        "bids": bids or [],
        "asks": asks or [],
        "source": source,
        "session_date": day,
        "payload": json.dumps({"bids": bids or [], "asks": asks or []}),
    })
    # Cap stub memory so an accidental hot loop cannot OOM.
    if len(_L2_STUB_ROWS) > 10_000:
        del _L2_STUB_ROWS[:5_000]
    bump_counter(ARCHIVE_COUNTER_L2_SNAPSHOTS)
    _ = ARCHIVE_STREAM_L2


def clear_l2_stub_for_tests() -> None:
    _L2_STUB_ROWS.clear()


def l2_stub_count() -> int:
    return len(_L2_STUB_ROWS)


def parse_iso_to_unix(ts_iso: str) -> float:
    """Best-effort ISO-8601 → unix seconds (UTC)."""
    raw = ts_iso.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return time.time()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()
