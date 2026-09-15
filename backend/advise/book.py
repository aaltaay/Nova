"""SQLite Advise book.

Owner: advise.book
Invalidation: new runs use today's 04:00 ET session date; history is append-only
schema_version: ADVISE_SCHEMA_VERSION (unknown versions refuse loud)
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from constants_advise import ADVISE_DB_FILENAME, ADVISE_SCHEMA_VERSION
from advise.models import cache_key, empty_result
from market import session_key_et
from paths import cache_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS advise_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS advise_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    session_date TEXT NOT NULL,
    created_ts REAL NOT NULL,
    finished_ts REAL,
    model TEXT NOT NULL,
    graph_version INTEGER NOT NULL,
    depth INTEGER NOT NULL,
    status TEXT NOT NULL,
    fail_reason TEXT,
    transcript_json TEXT NOT NULL DEFAULT '[]',
    result_json TEXT,
    cache_key TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_advise_runs_cache
    ON advise_runs(cache_key, status, created_ts);
CREATE INDEX IF NOT EXISTS idx_advise_runs_symbol
    ON advise_runs(symbol, created_ts);
"""


class AdviseBookError(RuntimeError):
    pass


def _db_path() -> Path:
    return cache_dir() / ADVISE_DB_FILENAME


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        row = conn.execute(
            "SELECT value FROM advise_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO advise_meta(key, value) VALUES ('schema_version', ?)",
                (str(ADVISE_SCHEMA_VERSION),),
            )
        else:
            stored = int(row["value"])
            if stored != ADVISE_SCHEMA_VERSION:
                raise AdviseBookError(
                    f"advise_book schema_version {stored} unsupported "
                    f"(expected {ADVISE_SCHEMA_VERSION})"
                )
        conn.commit()
    finally:
        conn.close()


def _parse_json(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def row_to_run(row: sqlite3.Row | dict) -> dict[str, Any]:
    data = dict(row)
    version = int(data.get("schema_version") or 0)
    if version != ADVISE_SCHEMA_VERSION:
        raise AdviseBookError(
            f"advise run {data.get('id')} schema_version {version} unsupported"
        )
    transcript = _parse_json(data.get("transcript_json"), [])
    result = _parse_json(data.get("result_json"), None)
    return {
        "id": int(data["id"]),
        "schema_version": version,
        "symbol": data["symbol"],
        "session_date": data["session_date"],
        "created_ts": data["created_ts"],
        "finished_ts": data["finished_ts"],
        "model": data["model"],
        "graph_version": int(data["graph_version"]),
        "depth": int(data["depth"]),
        "status": data["status"],
        "fail_reason": data["fail_reason"],
        "transcript": transcript if isinstance(transcript, list) else [],
        "result": result if isinstance(result, dict) else empty_result(),
        "cache_key": data["cache_key"],
    }


def create_run(
    *,
    symbol: str,
    model: str,
    graph_version: int,
    depth: int,
    session_date: str | None = None,
) -> dict[str, Any]:
    init_db()
    day = session_date or session_key_et()
    key = cache_key(symbol, day, model, graph_version, depth)
    now = time.time()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO advise_runs (
                schema_version, symbol, session_date, created_ts, finished_ts,
                model, graph_version, depth, status, fail_reason,
                transcript_json, result_json, cache_key
            ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, 'queued', NULL, '[]', NULL, ?)
            """,
            (ADVISE_SCHEMA_VERSION, symbol, day, now, model, graph_version, depth, key),
        )
        conn.commit()
        run_id = int(cur.lastrowid)
    finally:
        conn.close()
    loaded = get_run(run_id)
    assert loaded is not None
    return loaded


def get_run(run_id: int) -> dict[str, Any] | None:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM advise_runs WHERE id = ?", (run_id,)).fetchone()
        return row_to_run(row) if row else None
    finally:
        conn.close()


def list_history(symbol: str, limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM advise_runs
            WHERE symbol = ?
            ORDER BY created_ts DESC
            LIMIT ?
            """,
            (symbol, limit),
        ).fetchall()
        return [row_to_run(row) for row in rows]
    finally:
        conn.close()


def find_complete_cached(
    *,
    symbol: str,
    session_date: str,
    model: str,
    graph_version: int,
    depth: int,
) -> dict[str, Any] | None:
    init_db()
    key = cache_key(symbol, session_date, model, graph_version, depth)
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM advise_runs
            WHERE cache_key = ? AND status = 'complete'
            ORDER BY created_ts DESC
            LIMIT 1
            """,
            (key,),
        ).fetchone()
        return row_to_run(row) if row else None
    finally:
        conn.close()


def update_status(
    run_id: int,
    status: str,
    *,
    fail_reason: str | None = None,
    finished: bool = False,
) -> None:
    init_db()
    conn = get_connection()
    try:
        if finished:
            conn.execute(
                """
                UPDATE advise_runs
                SET status = ?, fail_reason = ?, finished_ts = ?
                WHERE id = ?
                """,
                (status, fail_reason, time.time(), run_id),
            )
        else:
            conn.execute(
                """
                UPDATE advise_runs
                SET status = ?, fail_reason = ?
                WHERE id = ?
                """,
                (status, fail_reason, run_id),
            )
        conn.commit()
    finally:
        conn.close()


def append_event(run_id: int, event: dict[str, Any]) -> list[dict[str, Any]]:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT schema_version, transcript_json FROM advise_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return []
        if int(row["schema_version"]) != ADVISE_SCHEMA_VERSION:
            raise AdviseBookError("advise run schema_version unsupported")
        transcript = _parse_json(row["transcript_json"], [])
        if not isinstance(transcript, list):
            transcript = []
        transcript.append(event)
        conn.execute(
            "UPDATE advise_runs SET transcript_json = ? WHERE id = ?",
            (json.dumps(transcript), run_id),
        )
        conn.commit()
        return transcript
    finally:
        conn.close()


def set_result(run_id: int, result: dict[str, Any]) -> None:
    init_db()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE advise_runs SET result_json = ? WHERE id = ?",
            (json.dumps(result), run_id),
        )
        conn.commit()
    finally:
        conn.close()
