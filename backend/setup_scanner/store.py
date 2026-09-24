"""The scoreboard's durable store: one row per armed setup.

Owner: this module (the only reader and writer of ``setups.db``).
File: ``paths.cache_dir() / SETUPS_DB_FILENAME`` -- operator cache, not git.
Invalidation: none; it is history. A trading day adds rows, nothing expires.
Schema: ``PRAGMA user_version = SETUPS_DB_SCHEMA_VERSION``; an unknown version is
refused loudly rather than read wrong (persisted-state rule). Version 2 (ADR
029) stamps every row with the template that armed it (``template_id``,
``template_rev``, ``params_hash``); a version-1 file is migrated in place and
its rows become the default template's -- the rules that armed them. Version 3
(ADR 031) adds the setup that armed the row (``setup_type``) and its own facts
(``detail``, JSON); a version-2 file is migrated in place, its rows the first
pullback's, and a version-1 file migrates through 2.
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

from constants_bot import BOT_SETUP_FIRST_PULLBACK
from constants_setups import (
    SETUP_TEMPLATE_DEFAULT_ID,
    SETUP_TEMPLATE_DEFAULT_REV,
    SETUPS_DB_FILENAME,
    SETUPS_DB_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

COLUMNS: tuple[str, ...] = (
    "id", "session_date", "symbol", "kind", "nth", "leg_t", "state", "reason",
    "armed_at", "trigger", "entry_planned", "stop", "risk", "target1",
    "leg_high", "leg_low", "leg_pct", "pullback_bars", "grade", "pillars",
    "near_at", "near_tape", "triggered_at", "entry", "trigger_tape",
    "failed_at", "fail_reason", "disarmed_at",
    "outcome", "outcome_at", "mfe", "mae", "bar_r", "bar_exit_reason", "closed_at",
    "proposal_id", "updated_at", "template_id", "template_rev", "params_hash",
    "setup_type", "detail",
)
JSON_COLUMNS = frozenset({"pillars", "near_tape", "trigger_tape", "detail"})
TEXT_COLUMNS = JSON_COLUMNS | {"kind", "state", "reason", "grade", "fail_reason", "outcome", "bar_exit_reason",
                               "proposal_id", "template_id", "params_hash", "setup_type"}
INT_COLUMNS = frozenset({"template_rev"})


def _type(column: str) -> str:
    return "TEXT" if column in TEXT_COLUMNS else "INTEGER" if column in INT_COLUMNS else "REAL"


_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS setups (
    id TEXT PRIMARY KEY,
    session_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    {", ".join(f"{c} {_type(c)}" for c in COLUMNS[3:])}
);
CREATE INDEX IF NOT EXISTS setups_day ON setups (session_date, symbol);
CREATE INDEX IF NOT EXISTS setups_template ON setups (template_id, template_rev);
CREATE INDEX IF NOT EXISTS setups_setup_type ON setups (setup_type, template_id, template_rev);
"""
_V2_COLUMNS = ("template_id", "template_rev", "params_hash")
_V3_COLUMNS = ("setup_type", "detail")


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
            if ver not in (0, 1, 2, SETUPS_DB_SCHEMA_VERSION) or (ver == 0 and tables):
                raise StoreVersionError(
                    f"{self.path.name} has schema version {ver}; this build reads {SETUPS_DB_SCHEMA_VERSION}. "
                    "Move the file aside to start a new scoreboard.")
            if ver == 1:
                self._migrate_v1()
            if ver in (1, 2):
                self._migrate_v2()
            self._conn.executescript(_SCHEMA)
            self._conn.execute(f"PRAGMA user_version = {SETUPS_DB_SCHEMA_VERSION}")
            self._conn.commit()

    def _migrate_v1(self) -> None:
        """v1 -> v2: the template stamp; every older row is the default template's (ADR 029)."""
        from constants_bot import BOT_SETUP_FIRST_PULLBACK
        from setup_templates.catalogue import defaults, fingerprint

        have = {r[1] for r in self._conn.execute("PRAGMA table_info(setups)").fetchall()}
        for col in _V2_COLUMNS:
            if col not in have:
                self._conn.execute(f"ALTER TABLE setups ADD COLUMN {col} {_type(col)}")
        self._conn.execute(
            "UPDATE setups SET template_id = ?, template_rev = ?, params_hash = ? WHERE template_id IS NULL",
            (SETUP_TEMPLATE_DEFAULT_ID, SETUP_TEMPLATE_DEFAULT_REV,
             fingerprint(defaults(BOT_SETUP_FIRST_PULLBACK))))
        logger.info("setups.db migrated to schema 2: earlier rows are the default template's")

    def _migrate_v2(self) -> None:
        """v2 -> v3: the setup that armed the row; every older row is the first pullback's (ADR 031)."""
        have = {r[1] for r in self._conn.execute("PRAGMA table_info(setups)").fetchall()}
        for col in _V3_COLUMNS:
            if col not in have:
                self._conn.execute(f"ALTER TABLE setups ADD COLUMN {col} {_type(col)}")
        self._conn.execute("UPDATE setups SET setup_type = ? WHERE setup_type IS NULL", (BOT_SETUP_FIRST_PULLBACK,))
        logger.info("setups.db migrated to schema 3: earlier rows are the first pullback's")

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
             symbol: str | None = None, limit: int | None = None, template_id: str | None = None,
             template_rev: int | None = None, setup_type: str | None = None) -> list[dict[str, Any]]:
        where, args = [], []
        if setup_type:
            # A row written without a setup (schema 2, a test) is the first pullback's.
            where.append("(setup_type = ? OR (setup_type IS NULL AND ? = ?))")
            args += [setup_type, setup_type, BOT_SETUP_FIRST_PULLBACK]
        if template_id:
            where.append("template_id = ?")
            args.append(template_id)
        if template_rev is not None:
            where.append("template_rev = ?")
            args.append(int(template_rev))
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
