"""CRUD helpers for recorded Level 2 snapshots and point-in-time range reads.

Writes go through l2.batch (executemany). record_snapshot() still flushes
immediately so existing Phase F callers and tests stay durable without waiting
for the background flush loop.
"""
from __future__ import annotations

import json

from l2 import batch as _batch
from l2.db import db_path, get_connection


def record_snapshot(
    recording_id: str,
    symbol: str,
    setup: str,
    signal_ts: float,
    ts: float,
    book: dict,
    session_id: str | None = None,
    *,
    flush: bool = True,
) -> None:
    row = (
        recording_id,
        symbol,
        setup,
        signal_ts,
        ts,
        json.dumps(book.get("bids", [])),
        json.dumps(book.get("asks", [])),
        int(book.get("l1_fallback", False)),
        session_id,
    )
    _batch.enqueue_snapshot(row)
    if flush:
        _batch.flush()


def record_snapshots_batch(
    rows: list[tuple],
    *,
    flush: bool = False,
) -> None:
    """Enqueue many pre-built snapshot tuples (same shape as enqueue_snapshot)."""
    for row in rows:
        _batch.enqueue_snapshot(row)
    if flush:
        _batch.flush()


def get_recording_ids() -> list[dict]:
    """One row per distinct recording -- symbol, setup, signal_ts, snapshot count."""
    _batch.flush()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT recording_id, symbol, setup, signal_ts, COUNT(*) AS snapshot_count
            FROM l2_snapshots
            GROUP BY recording_id
            ORDER BY signal_ts DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_snapshots(recording_id: str) -> list[dict]:
    """All snapshots for one recording, oldest first, with bids/asks decoded."""
    _batch.flush()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM l2_snapshots WHERE recording_id = ? ORDER BY ts ASC",
            (recording_id,),
        ).fetchall()
        return [_decode_snapshot(row) for row in rows]
    finally:
        conn.close()


def get_snapshots_in_range(symbol: str, start_ts: float, end_ts: float) -> list[dict]:
    """Snapshots for symbol with ts in [start_ts, end_ts], oldest first."""
    _batch.flush()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM l2_snapshots
            WHERE symbol = ? AND ts >= ? AND ts <= ?
            ORDER BY ts ASC
            """,
            (symbol.upper(), start_ts, end_ts),
        ).fetchall()
        return [_decode_snapshot(row) for row in rows]
    finally:
        conn.close()


def get_snapshot_before(symbol: str, ts: float, max_age_sec: float) -> dict | None:
    """Newest snapshot at or before ``ts``, no older than ``max_age_sec``.

    The point-in-time read a replay needs: it never looks ahead of the
    playhead, and one indexed row is the whole result, so cost does not grow
    with the archive (``idx_l2_snapshots_symbol_ts``).

    Two deliberate differences from the readers above. It does not flush the
    writer batch -- queued rows belong to the live recording, never to the
    replayed past, and a read on the replay poll must not take a write side
    effect. And it refuses to create ``l2.db``: absence of the file is the
    answer "nothing was recorded", not a reason to materialize an empty one.
    """
    if not db_path().exists():
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM l2_snapshots
            WHERE symbol = ? AND ts <= ? AND ts >= ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            (symbol.upper(), ts, ts - max_age_sec),
        ).fetchone()
    finally:
        conn.close()
    return _decode_snapshot(row) if row else None


def get_nearest_snapshot(symbol: str, ts: float, window_sec: float) -> dict | None:
    """Closest snapshot to ts within ±window_sec, or None."""
    rows = get_snapshots_in_range(symbol, ts - window_sec, ts + window_sec)
    if not rows:
        return None
    return min(rows, key=lambda r: abs(r["ts"] - ts))


def _decode_snapshot(row) -> dict:
    d = dict(row)
    d["bids"] = json.loads(d.pop("bids_json"))
    d["asks"] = json.loads(d.pop("asks_json"))
    d["l1_fallback"] = bool(d["l1_fallback"])
    return d
