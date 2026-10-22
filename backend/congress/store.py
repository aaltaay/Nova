"""The reports and trades the reader has read, kept across restarts (ADR 066).

Owner of ``<cache_dir>/congress/filings.sqlite3`` (shape in architecture/schema/congress.md, "Persisted files"):
``reports``, ``trades`` (as filed) and ``meta``. ``PRAGMA user_version`` is ``CONGRESS_STORE_VERSION``; a file of
another version is renamed aside and read again from the sites -- never migrated by guesswork. Nothing here is a
source of truth: the sites are, and a lost file is only a slower first read. One writer (the reader thread); every
call takes the lock.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

from congress import files
from congress.constants_congress import CONGRESS_STORE_FILE, CONGRESS_STORE_VERSION

logger = logging.getLogger(__name__)

REPORT_COLS = ("id", "chamber", "filer_name", "filer_first", "filer_last", "filer_state", "filer_district", "bioguide",
               "filed", "kind", "url", "title", "amends", "amended_by", "parser", "read_at", "error", "trades")
TRADE_COLS = ("report", "n", "tx", "notified", "owner", "ticker", "asset", "asset_type", "tx_type", "amount", "status",
              "subholding", "description")
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS reports ({", ".join(c + (" TEXT PRIMARY KEY" if c == "id" else "") for c in REPORT_COLS)});
CREATE TABLE IF NOT EXISTS trades ({", ".join(TRADE_COLS)}, PRIMARY KEY (report, n));
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS trades_report ON trades (report);
"""


def default_path() -> Path:
    return files.folder() / CONGRESS_STORE_FILE


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        self._lock = threading.Lock()
        self._db = self._open()

    def _open(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), check_same_thread=False)
        version = db.execute("PRAGMA user_version").fetchone()[0]
        tables = db.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
        if tables and version != CONGRESS_STORE_VERSION:
            db.close()
            aside = self.path.with_name(f"{self.path.name}.v{version}.{int(time.time())}.bak")
            self.path.replace(aside)
            logger.warning("congress: %s has version %s, not %s: set aside as %s and read again from the sites",
                           self.path.name, version, CONGRESS_STORE_VERSION, aside.name)
            db = sqlite3.connect(str(self.path), check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.executescript(SCHEMA)
        db.execute(f"PRAGMA user_version = {CONGRESS_STORE_VERSION}")
        db.commit()
        return db

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def reports(self) -> dict[str, dict]:
        with self._lock:
            return {r["id"]: dict(r) for r in self._db.execute("SELECT * FROM reports")}

    def rows(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        with self._lock:
            for r in self._db.execute("SELECT * FROM trades ORDER BY report, n"):
                out.setdefault(r["report"], []).append(dict(r))
        return out

    def put(self, report: dict, rows: list[dict] | None) -> None:
        """Keep a report and, when given, replace its rows -- one transaction."""
        rec = {c: report.get(c) for c in REPORT_COLS}
        if rows is not None:
            rec["trades"] = len(rows)
        with self._lock, self._db:
            self._db.execute(f"INSERT OR REPLACE INTO reports ({', '.join(REPORT_COLS)}) VALUES "
                             f"({', '.join('?' for _ in REPORT_COLS)})", [rec[c] for c in REPORT_COLS])
            if rows is not None:
                self._db.execute("DELETE FROM trades WHERE report = ?", (rec["id"],))
                self._db.executemany(f"INSERT INTO trades ({', '.join(TRADE_COLS)}) VALUES "
                                     f"({', '.join('?' for _ in TRADE_COLS)})",
                                     [[rec["id"], n, *[row.get(c) for c in TRADE_COLS[2:]]] for n, row in enumerate(rows)])

    def set_fields(self, report_id: str, **fields) -> None:
        """Change named columns of one report (a match, an amendment's mark)."""
        cols = [c for c in fields if c in REPORT_COLS and c != "id"]
        if not cols:
            return
        with self._lock, self._db:
            self._db.execute(f"UPDATE reports SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?",
                             [fields[c] for c in cols] + [report_id])

    def meta(self, key: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
