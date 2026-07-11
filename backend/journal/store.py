"""
CRUD helpers for the journal database. Thin wrappers around db.get_connection()
-- no business logic here beyond turning rows into plain dicts.

record_trade() exists for Phase D (paper execution) to call once it closes a
bracket order; nothing in this codebase places an order today, so the trades
table stays empty until that phase ships. See journal/metrics.py for how an
empty trades table is reported honestly rather than faked.
"""
from __future__ import annotations

import json
import time

from constants import JOURNAL_SIGNALS_DEFAULT_LIMIT, JOURNAL_TRADES_DEFAULT_LIMIT
from journal.db import get_connection


def record_signal(
    symbol: str,
    setup: str,
    entry_price: float | None,
    stop_price: float | None,
    target_price: float | None,
    payload: dict,
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO signals (ts, symbol, setup, entry_price, stop_price, target_price, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (time.time(), symbol, setup, entry_price, stop_price, target_price, json.dumps(payload)),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def get_signals(limit: int = JOURNAL_SIGNALS_DEFAULT_LIMIT) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM signals ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def record_trade(
    symbol: str,
    setup: str | None,
    side: str,
    qty: int,
    entry_price: float,
    stop_price: float | None,
    target_price: float | None,
    exit_price: float | None,
    pnl: float | None,
    adherent: bool | None,
    opened_ts: float | None = None,
    closed_ts: float | None = None,
    notes: str = "",
    is_mock: bool = False,
) -> int:
    """is_mock=True tags a synthetic row inserted by journal/mock_data.py for
    UI/logic testing before Phase D (paper execution) exists. Real callers
    (Phase D, once built) must never pass is_mock=True."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO trades (
                opened_ts, closed_ts, symbol, setup, side, qty, entry_price,
                exit_price, stop_price, target_price, pnl, adherent, notes, is_mock
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opened_ts if opened_ts is not None else time.time(),
                closed_ts,
                symbol,
                setup,
                side,
                qty,
                entry_price,
                exit_price,
                stop_price,
                target_price,
                pnl,
                None if adherent is None else int(adherent),
                notes,
                int(is_mock),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def get_trades(limit: int = JOURNAL_TRADES_DEFAULT_LIMIT, include_mock: bool = False) -> list[dict]:
    conn = get_connection()
    try:
        where = "" if include_mock else "WHERE is_mock = 0"
        rows = conn.execute(
            f"SELECT * FROM trades {where} ORDER BY opened_ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_closed_trades(include_mock: bool = False) -> list[dict]:
    """All trades with a recorded pnl -- the population metrics.py scores.
    Excludes mock rows by default so real-money go/no-go metrics can never be
    silently inflated by test data."""
    conn = get_connection()
    try:
        mock_clause = "" if include_mock else "AND is_mock = 0"
        rows = conn.execute(
            f"SELECT * FROM trades WHERE pnl IS NOT NULL {mock_clause} ORDER BY opened_ts ASC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def clear_mock_trades() -> int:
    """Delete every mock-tagged trade. Returns the number of rows removed."""
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM trades WHERE is_mock = 1")
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
