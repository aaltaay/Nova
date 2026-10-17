"""Loss-aware gap markers, incomplete-window flags, L2 stub, and ISO timestamp helper.

Extracted from ``archive/capture.py`` along the integrity-marker / stub seam
so ``archive/capture.py`` stays focused on core stream writes and under 400 lines.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from archive import db as archive_db
from constants import (
    ARCHIVE_COUNTER_GAPS,
    ARCHIVE_COUNTER_INCOMPLETE_WINDOWS,
    ARCHIVE_COUNTER_L2_SNAPSHOTS,
    ARCHIVE_SOURCE_IBKR,
    ARCHIVE_STREAM_L2,
)

# Optional in-process L2 snapshot store until a dedicated table is justified.
_L2_STUB_ROWS: list[dict[str, Any]] = []


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
    from archive.capture import bump_counter, session_date_for_ts

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
    from archive.capture import bump_counter, session_date_for_ts

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
    Unwired stub for a future changed-book (not just 1 Hz sampled) L2 capture
    path. No production code calls this -- rows never leave process memory
    and are capped/dropped on restart. Do not treat calls to this function or
    increments of ``ARCHIVE_COUNTER_L2_SNAPSHOTS`` as evidence that L2 data
    is durably archived; see ``archive/l2_bridge.py`` for the real path
    (``l2/continuous.py`` -> ``l2/db.py`` -> l2_bridge cold export + R2).
    """
    from archive.capture import bump_counter, session_date_for_ts

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
    """Best-effort ISO-8601 -> unix seconds (UTC)."""
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
