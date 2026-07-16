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

from constants import (
    JOURNAL_SIGNALS_DEFAULT_LIMIT,
    JOURNAL_TAGS_DEFAULT_JSON,
    JOURNAL_TAGS_MAX_PER_TRADE,
    JOURNAL_TRADES_DEFAULT_LIMIT,
)
from journal.db import get_connection


def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    cleaned = [str(t).strip() for t in tags if str(t).strip()]
    return cleaned[:JOURNAL_TAGS_MAX_PER_TRADE]


def _tags_to_json(tags: list[str] | None) -> str:
    return json.dumps(_normalize_tags(tags))


def _row_to_trade(row: dict) -> dict:
    trade = dict(row)
    raw = trade.get("tags", JOURNAL_TAGS_DEFAULT_JSON)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            trade["tags"] = parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            trade["tags"] = []
    elif not isinstance(raw, list):
        trade["tags"] = []
    return trade


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
    tags: list[str] | None = None,
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
                exit_price, stop_price, target_price, pnl, adherent, notes, is_mock, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                _tags_to_json(tags),
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
        return [_row_to_trade(dict(row)) for row in rows]
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
        return [_row_to_trade(dict(row)) for row in rows]
    finally:
        conn.close()


def update_trade_tags(trade_id: int, tags: list[str]) -> dict | None:
    """Replace tags on an existing trade. Returns updated row or None if missing."""
    normalized = _normalize_tags(tags)
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE trades SET tags = ? WHERE id = ?",
            (_tags_to_json(normalized), trade_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return _row_to_trade(dict(row)) if row else None
    finally:
        conn.close()


def get_trade_by_id(trade_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return _row_to_trade(dict(row)) if row else None
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
