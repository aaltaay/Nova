"""WAL-safe SQLite copies of Nova's local databases."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from constants import (
    SQLITE_BACKUP_DIRNAME,
    SQLITE_BACKUP_FILENAMES,
    SQLITE_BACKUP_RETENTION_DAYS,
)
from paths import cache_dir

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


def backup_sqlite_once(*, now: datetime | None = None) -> dict:
    """Copy the five local SQLite files into cache_dir/backups/{date}/."""
    when = now or datetime.now(tz=_ET)
    date = when.strftime("%Y-%m-%d")
    dest = cache_dir() / SQLITE_BACKUP_DIRNAME / date
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    skipped: list[str] = []
    for name in SQLITE_BACKUP_FILENAMES:
        src = cache_dir() / name
        if not src.is_file():
            skipped.append(name)
            continue
        dst = dest / name
        src_conn = sqlite3.connect(str(src))
        dst_conn = sqlite3.connect(str(dst))
        try:
            src_conn.backup(dst_conn)
            copied.append(name)
        finally:
            dst_conn.close()
            src_conn.close()
    pruned = prune_old_backups(keep_days=SQLITE_BACKUP_RETENTION_DAYS, now=when)
    return {"ok": True, "date": date, "copied": copied, "skipped": skipped, "pruned": pruned}


def prune_old_backups(*, keep_days: int, now: datetime | None = None) -> list[str]:
    root = cache_dir() / SQLITE_BACKUP_DIRNAME
    if not root.is_dir():
        return []
    when = now or datetime.now(tz=_ET)
    cutoff = (when - timedelta(days=max(1, int(keep_days)))).strftime("%Y-%m-%d")
    removed: list[str] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if child.name < cutoff:
            import shutil

            shutil.rmtree(child, ignore_errors=True)
            removed.append(child.name)
    return removed
