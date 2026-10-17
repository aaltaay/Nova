"""
Loss-aware local capture APIs for Nova OS P6.

Write path into ``archive.db``. Callers should treat failures as non-fatal for
live UI (log + gap marker) so a disk issue never blanks the quote panel.

L2 depth is NOT captured through ``record_l2_snapshot`` (re-exported from
``archive.capture_gaps``) -- that function is an unwired, in-memory-only stub
with no production caller. The real, durable L2 + tape capture is the
pre-existing ``l2/continuous.py`` sampler (1 Hz while a depth session is open)
writing to ``l2/db.py``'s ``l2_snapshots``/``tape_trades`` tables.
``archive/l2_bridge.py`` exports that data into the same checksummed
cold-archive + R2 pattern used here for bars/tape_ibkr (see ``archive.compact``
/ ``archive.r2``).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from archive import db as archive_db
from archive.capture_gaps import (  # noqa: F401 -- compatibility re-exports (ADR 004)
    _L2_STUB_ROWS,
    clear_l2_stub_for_tests,
    l2_stub_count,
    mark_incomplete_window,
    parse_iso_to_unix,
    record_gap,
    record_l2_snapshot,
)
from constants import (
    ARCHIVE_COUNTER_BARS_1D,
    ARCHIVE_COUNTER_BARS_1M,
    ARCHIVE_COUNTER_ENRICHMENT_SNAPSHOTS,
    ARCHIVE_COUNTER_L1_TICKS,
    ARCHIVE_COUNTER_TAPE_RECEIVED,
    ARCHIVE_SOURCE_IBKR,
    ARCHIVE_STREAM_BARS_1D,
    ARCHIVE_STREAM_BARS_1M,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


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


def record_l1_tick(
    *,
    symbol: str,
    ts: float,
    price: float,
    volume: float | None = None,
    day_high: float | None = None,
    session_date: str | None = None,
) -> None:
    """Persist one HOD-decision L1 tick (what ``on_trade_update`` received)."""
    if ts <= 0:
        return
    symbol = symbol.upper()
    day = session_date or session_date_for_ts(ts)
    conn = archive_db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO l1_ticks
                (symbol, ts, price, volume, day_high, session_date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                float(ts),
                float(price),
                float(volume) if volume is not None else None,
                float(day_high) if day_high is not None else None,
                day,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    bump_counter(ARCHIVE_COUNTER_L1_TICKS)


def record_enrichment_snapshot(
    *,
    symbol: str,
    ts: float,
    avg_volume: float | None = None,
    float_shares: float | None = None,
    fifty_two_week_high: float | None = None,
    rvol_source: str | None = None,
    session_date: str | None = None,
) -> None:
    """UPSERT one per-symbol enrichment snapshot for the session (G6)."""
    symbol = symbol.upper()
    day = session_date or session_date_for_ts(ts)
    conn = archive_db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO enrichment_snapshots
                (symbol, session_date, ts, avg_volume, float_shares,
                 fifty_two_week_high, rvol_source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, session_date) DO UPDATE SET
                ts = excluded.ts,
                avg_volume = excluded.avg_volume,
                float_shares = excluded.float_shares,
                fifty_two_week_high = excluded.fifty_two_week_high,
                rvol_source = excluded.rvol_source
            """,
            (
                symbol,
                day,
                float(ts),
                float(avg_volume) if avg_volume is not None else None,
                float(float_shares) if float_shares is not None else None,
                float(fifty_two_week_high) if fifty_two_week_high is not None else None,
                rvol_source,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    bump_counter(ARCHIVE_COUNTER_ENRICHMENT_SNAPSHOTS)


def load_enrichment_snapshot(
    symbol: str,
    *,
    session_date: str | None = None,
) -> dict[str, Any] | None:
    """Return the latest enrichment snapshot row for symbol/session, if any."""
    symbol = symbol.upper()
    day = session_date or session_date_for_ts()
    conn = archive_db.get_connection()
    try:
        row = conn.execute(
            """
            SELECT symbol, session_date, ts, avg_volume, float_shares,
                   fifty_two_week_high, rvol_source
            FROM enrichment_snapshots
            WHERE symbol = ? AND session_date = ?
            """,
            (symbol, day),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return dict(row)
