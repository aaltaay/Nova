"""Session metadata for local recorders — ties L2 + tape rows to a wall-clock window."""
from __future__ import annotations

import time
import uuid

from l2.db import get_connection


def start_session(
    symbol: str,
    reason: str,
    *,
    setup: str | None = None,
    signal_ts: float | None = None,
    started_ts: float | None = None,
) -> str:
    session_id = f"{symbol.upper()}:{reason}:{uuid.uuid4().hex[:12]}"
    ts = time.time() if started_ts is None else started_ts
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO record_sessions
                (session_id, symbol, reason, setup, signal_ts, started_ts, ended_ts)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (session_id, symbol.upper(), reason, setup, signal_ts, ts),
        )
        conn.commit()
    finally:
        conn.close()
    return session_id


def end_session(session_id: str, ended_ts: float | None = None) -> None:
    ts = time.time() if ended_ts is None else ended_ts
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE record_sessions SET ended_ts = ? WHERE session_id = ?",
            (ts, session_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_sessions(
    symbol: str | None = None,
    *,
    limit: int = 100,
) -> list[dict]:
    conn = get_connection()
    try:
        if symbol:
            rows = conn.execute(
                """
                SELECT * FROM record_sessions
                WHERE symbol = ?
                ORDER BY started_ts DESC
                LIMIT ?
                """,
                (symbol.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM record_sessions
                ORDER BY started_ts DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def session_covering(symbol: str, ts: float) -> dict | None:
    """Active or ended session whose [started_ts, ended_ts] covers ts."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM record_sessions
            WHERE symbol = ?
              AND started_ts <= ?
              AND (ended_ts IS NULL OR ended_ts >= ?)
            ORDER BY started_ts DESC
            LIMIT 1
            """,
            (symbol.upper(), ts, ts),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
