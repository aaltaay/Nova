"""The scoreboard's durable store: one row per armed setup.

Owner: this module (the only reader and writer of ``setups.db``).
File: ``paths.cache_dir() / SETUPS_DB_FILENAME`` -- operator cache, not git.
Invalidation: none; it is history. A trading day adds rows, nothing expires.
Schema: ``PRAGMA user_version = SETUPS_SCHEMA_VERSION``; an unknown version is
refused loudly rather than read wrong (persisted-state rule).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from constants_setups import SETUPS_DB_FILENAME, SETUPS_SCHEMA_VERSION

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

COLUMNS: tuple[str, ...] = (
    "id", "session_date", "symbol", "kind", "nth", "leg_t", "state", "reason",
    "armed_at", "trigger", "entry_planned", "stop", "risk", "target1",
    "leg_high", "leg_low", "leg_pct", "pullback_bars", "grade", "pillars",
    "near_at", "near_tape", "triggered_at", "entry", "trigger_tape",
    "failed_at", "fail_reason", "disarmed_at",
    "outcome", "outcome_at", "mfe", "mae", "bar_r", "bar_exit_reason", "closed_at",
    "proposal_id", "updated_at",
)
JSON_COLUMNS = frozenset({"pillars", "near_tape", "trigger_tape"})

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS setups (
    id TEXT PRIMARY KEY,
    session_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    {", ".join(f"{c} {'TEXT' if c in JSON_COLUMNS or c in ('kind', 'state', 'reason', 'grade', 'fail_reason', 'outcome', 'bar_exit_reason', 'proposal_id') else 'REAL'}" for c in COLUMNS[3:])}
);
CREATE INDEX IF NOT EXISTS setups_day ON setups (session_date, symbol);
"""


class StoreVersionError(RuntimeError):
    pass


def session_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%Y-%m-%d")


class SetupStore:
    def __init__(self, path: Path | None = None):
        if path is None:
            from paths import cache_dir

            path = cache_dir() / SETUPS_DB_FILENAME
        self.path = Path(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            ver = self._conn.execute("PRAGMA user_version").fetchone()[0]
            tables = self._conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='setups'").fetchone()[0]
            if ver not in (0, SETUPS_SCHEMA_VERSION) or (ver == 0 and tables):
                raise StoreVersionError(
                    f"{self.path.name} has schema version {ver}; this build reads {SETUPS_SCHEMA_VERSION}. "
                    "Move the file aside to start a new scoreboard.")
            self._conn.executescript(_SCHEMA)
            self._conn.execute(f"PRAGMA user_version = {SETUPS_SCHEMA_VERSION}")
            self._conn.commit()

    def upsert(self, row: dict[str, Any]) -> None:
        data = {k: row.get(k) for k in COLUMNS if k in row}
        data["updated_at"] = time.time()
        for k in JSON_COLUMNS & data.keys():
            if data[k] is not None and not isinstance(data[k], str):
                data[k] = json.dumps(data[k], default=str)
        cols = list(data)
        sql = (f"INSERT INTO setups ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)}) "
               f"ON CONFLICT(id) DO UPDATE SET {', '.join(f'{c}=excluded.{c}' for c in cols if c != 'id')}")
        with self._lock:
            self._conn.execute(sql, [data[c] for c in cols])
            self._conn.commit()

    def rows(self, *, date_from: str | None = None, date_to: str | None = None,
             symbol: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        where, args = [], []
        if date_from:
            where.append("session_date >= ?")
            args.append(date_from)
        if date_to:
            where.append("session_date <= ?")
            args.append(date_to)
        if symbol:
            where.append("symbol = ?")
            args.append(symbol.upper())
        sql = "SELECT * FROM setups" + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY armed_at DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self._lock:
            out = [dict(r) for r in self._conn.execute(sql, args).fetchall()]
        for r in out:
            for k in JSON_COLUMNS:
                if r.get(k):
                    try:
                        r[k] = json.loads(r[k])
                    except (TypeError, ValueError):
                        logger.warning("setups.db: bad JSON in %s for %s", k, r.get("id"))
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()
