"""CRUD helpers for recorded Level 2 snapshots -- thin wrappers around
l2.db.get_connection(), no business logic beyond turning rows into dicts."""
from __future__ import annotations

import json

from l2.db import get_connection


def record_snapshot(
    recording_id: str,
    symbol: str,
    setup: str,
    signal_ts: float,
    ts: float,
    book: dict,
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO l2_snapshots (recording_id, symbol, setup, signal_ts, ts, bids_json, asks_json, l1_fallback)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recording_id, symbol, setup, signal_ts, ts,
                json.dumps(book.get("bids", [])),
                json.dumps(book.get("asks", [])),
                int(book.get("l1_fallback", False)),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def get_recording_ids() -> list[dict]:
    """One row per distinct recording -- symbol, setup, signal_ts, snapshot count."""
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
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM l2_snapshots WHERE recording_id = ? ORDER BY ts ASC",
            (recording_id,),
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["bids"] = json.loads(d.pop("bids_json"))
            d["asks"] = json.loads(d.pop("asks_json"))
            d["l1_fallback"] = bool(d["l1_fallback"])
            out.append(d)
        return out
    finally:
        conn.close()
