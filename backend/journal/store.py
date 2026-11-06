"""
CRUD helpers for the journal database. Thin wrappers around db.get_connection()
-- no business logic here beyond turning rows into plain dicts.

record_trade() writes one closed round trip (journal.round_trip, the importers);
upsert_round_trips() keeps Paper's round trips up to the practice ledger
(journal.paper_trips). Every reader takes a venue and a view (ADR 069
decision 6, architecture/schema/journal.md): ``live`` -- the default, and all
the risk engine and the metrics ever read -- is every row that is not Paper's.
See journal/metrics.py for how an empty trades table is reported honestly
rather than faked.
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from constants import (
    JOURNAL_SIGNALS_DEFAULT_LIMIT,
    JOURNAL_TAGS_DEFAULT_JSON,
    JOURNAL_TAGS_MAX_PER_TRADE,
    JOURNAL_TRADES_DEFAULT_LIMIT,
)
from constants_owners import JOURNAL_VENUE_LIVE, JOURNAL_VENUE_PAPER, OWNER_BOTS, OWNER_YOU
from journal.db import get_connection

_ET = ZoneInfo("America/New_York")

# What a round trip's ledger decides; an upsert rewrites these and keeps the rest (tags, notes, adherent).
_FIGURES = ("opened_ts", "closed_ts", "side", "qty", "entry_price", "exit_price", "stop_price", "pnl",
            "commission", "fill_ids", "owner", "bot")


def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    cleaned = [str(t).strip() for t in tags if str(t).strip()]
    return cleaned[:JOURNAL_TAGS_MAX_PER_TRADE]


def _tags_to_json(tags: list[str] | None) -> str:
    return json.dumps(_normalize_tags(tags))


def _row_to_trade(row: dict) -> dict:
    trade = dict(row)
    for column in ("venue", "owner", "bot"):    # a journal from before, read as it is, has none of the three
        trade.setdefault(column, None)
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
    close_key: str | None = None,
    commission: float | None = None,
    fill_ids: str | None = None,
    venue: str | None = None,
    owner: str | None = None,
    bot: str | None = None,
) -> int:
    """is_mock=True tags a synthetic row inserted by journal/mock_data.py for
    UI/logic testing before Phase D (paper execution) exists. Real callers
    (Phase D, once built) must never pass is_mock=True.

    close_key is a unique idempotency token (round-trip / executor). A
    duplicate insert returns 0 instead of a second row.

    venue / owner / bot say whose trade (ADR 069): ``paper`` for Paper's round
    trips, null for the rest; ``you`` | ``bots`` and the holder inside the bots'
    book. Left null, a trade reads as yours.
    """
    conn = get_connection()
    key = (close_key or "").strip() or None
    try:
        cur = conn.execute(
            """
            INSERT INTO trades (
                opened_ts, closed_ts, symbol, setup, side, qty, entry_price,
                exit_price, stop_price, target_price, pnl, adherent, notes,
                is_mock, tags, close_key, commission, fill_ids, venue, owner, bot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                key,
                commission,
                (fill_ids or "").strip() or None,
                venue,
                owner,
                bot,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        return 0
    finally:
        conn.close()


def upsert_round_trips(rows: list[dict], *, venue: str) -> int:
    """Write one venue's round trips (``record_trade``'s fields, each with a ``close_key``) in one transaction:
    a new key is inserted, a stored one is rewritten only when its ledger figures (``_FIGURES``) changed -- its
    tags, notes and adherent flag stay. Nothing is deleted. Returns how many rows were inserted or updated."""
    if not rows:
        return 0
    conn = get_connection()
    try:
        stored = {
            row["close_key"]: row
            for row in conn.execute(
                f"SELECT close_key, {', '.join(_FIGURES)} FROM trades WHERE venue = ? AND close_key IS NOT NULL",
                (venue,),
            )
        }
        cols = ("symbol", "setup", "notes", "is_mock", "tags", "close_key", "venue", *_FIGURES)
        written = 0
        for row in rows:
            old = stored.get(row["close_key"])
            if old is None:
                values = {**{c: row.get(c) for c in cols}, "notes": row.get("notes") or "", "is_mock": 0,
                          "tags": _tags_to_json(row.get("tags")), "venue": venue}
                conn.execute(
                    f"INSERT INTO trades ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                    [values[c] for c in cols],
                )
            elif any(old[c] != row.get(c) for c in _FIGURES):
                conn.execute(
                    f"UPDATE trades SET {', '.join(f'{c} = ?' for c in _FIGURES)} WHERE close_key = ?",
                    [*(row.get(c) for c in _FIGURES), row["close_key"]],
                )
            else:
                continue
            written += 1
        conn.commit()
        return written
    finally:
        conn.close()


def _et_day_start(day: str, plus_days: int = 0) -> float:
    start = datetime.combine(date.fromisoformat(day) + timedelta(days=plus_days), datetime.min.time(), _ET)
    return start.timestamp()


def _read_only(database: Path) -> sqlite3.Connection:
    """A journal file opened read-only: never created, migrated or written."""
    conn = sqlite3.connect(f"{Path(database).resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _view_clauses(conn: sqlite3.Connection, venue: str, owner: str | None,
                  bot: str | None) -> tuple[list[str], list] | None:
    """The venue's and the view's SQL (ADR 069 decision 6): ``live`` is every row that is not Paper's, ``paper``
    Paper's round trips (and the demo rows, which belong to no venue); ``you`` your book -- an owner left null
    reads as yours -- and ``bots`` the bots' book, or one ``bot`` in it. None when the file (a journal from
    before, read as it is) can hold no such row."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
    clauses: list[str] = []
    args: list = []
    paper = venue == JOURNAL_VENUE_PAPER
    if "venue" in columns:
        clauses.append("(venue = ? OR is_mock = 1)" if paper else "(venue IS NULL OR venue <> ?)")
        args.append(JOURNAL_VENUE_PAPER)
    elif paper:
        return None
    book = OWNER_BOTS if bot else owner
    if book is None:
        return clauses, args
    if "owner" not in columns:
        return (clauses, args) if book == OWNER_YOU else None
    if book == OWNER_YOU:
        clauses.append("(owner IS NULL OR owner <> ?)")
        args.append(OWNER_BOTS)
        return clauses, args
    clauses.append("owner = ?")
    args.append(OWNER_BOTS)
    if bot:
        clauses.append("bot = ?")
        args.append(bot)
    return clauses, args


def get_trades(limit: int = JOURNAL_TRADES_DEFAULT_LIMIT, include_mock: bool = False, *,
               symbol: str | None = None, setup: str | None = None, tag: str | None = None,
               adherent: bool | None = None, date_from: str | None = None,
               date_to: str | None = None, database: Path | None = None,
               venue: str = JOURNAL_VENUE_LIVE, owner: str | None = None, bot: str | None = None) -> list[dict]:
    """The newest ``limit`` trades that match every filter given: ``symbol`` and ``setup`` exact (any case), ``tag``
    one of the trade's tags (any case), ``adherent`` the plan flag (a trade with none matches neither), ``date_from``
    / ``date_to`` the ET day the trade opened (YYYY-MM-DD, inclusive), and the venue and view (``_view_clauses``).
    ``ValueError`` on a malformed day.
    ``database``: read that journal file read-only (the research front door's ``journal_trades``, which must never
    create or change the desk's journal) instead of the desk's own connection."""
    clauses, args = ([] if include_mock else ["is_mock = 0"]), []
    for clause, value in (("upper(symbol) = ?", symbol and symbol.strip().upper()),
                          ("lower(setup) = ?", setup and setup.strip().lower()),
                          ("opened_ts >= ?", date_from and _et_day_start(date_from)),
                          ("opened_ts < ?", date_to and _et_day_start(date_to, 1))):
        if value:
            clauses.append(clause)
            args.append(value)
    if adherent is not None:
        clauses.append("adherent = ?")
        args.append(1 if adherent else 0)
    wanted_tag = (tag or "").strip().lower()
    conn = get_connection() if database is None else _read_only(database)
    try:
        view = _view_clauses(conn, venue, owner, bot)
        if view is None:
            return []
        clauses.extend(view[0])
        args.extend(view[1])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        if wanted_tag:      # tags are a JSON list: matched here, so the limit counts matches
            rows = conn.execute(f"SELECT * FROM trades {where} ORDER BY opened_ts DESC", args).fetchall()
            trades = [t for t in (_row_to_trade(dict(row)) for row in rows)
                      if wanted_tag in {str(x).lower() for x in t["tags"]}]
            return trades[:limit]
        rows = conn.execute(
            f"SELECT * FROM trades {where} ORDER BY opened_ts DESC LIMIT ?", (*args, limit)
        ).fetchall()
        return [_row_to_trade(dict(row)) for row in rows]
    finally:
        conn.close()


def get_closed_trades(include_mock: bool = False, *, venue: str = JOURNAL_VENUE_LIVE,
                      owner: str | None = None, bot: str | None = None) -> list[dict]:
    """All trades with a recorded pnl -- the population metrics.py scores.
    Excludes mock rows by default so real-money go/no-go metrics can never be
    silently inflated by test data. ``venue`` / ``owner`` / ``bot``: the
    Reports tab's venue and view (``_view_clauses``); the default, ``live``,
    never reads a Paper round trip, so the risk engine's and the metrics'
    population is the journal as it was."""
    conn = get_connection()
    try:
        view = _view_clauses(conn, venue, owner, bot)
        if view is None:
            return []
        clauses = ["pnl IS NOT NULL", *([] if include_mock else ["is_mock = 0"]), *view[0]]
        rows = conn.execute(
            f"SELECT * FROM trades WHERE {' AND '.join(clauses)} ORDER BY opened_ts ASC", view[1],
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


def update_trade_net(
    trade_id: int,
    *,
    pnl: float,
    commission: float | None,
    notes: str,
    fill_ids: str | None = None,
) -> dict | None:
    """Rewrite stored P/L after a late CommissionReport. Does not invent fees."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            UPDATE trades
            SET pnl = ?, commission = ?, notes = ?, fill_ids = ?
            WHERE id = ?
            """,
            (
                float(pnl),
                commission,
                notes,
                (fill_ids or "").strip() or None,
                int(trade_id),
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (int(trade_id),)).fetchone()
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
