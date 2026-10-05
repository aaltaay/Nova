"""WAL-safe SQLite copies of Nova's local databases.

Each copy is written beside its final name and renamed into place, so a copy
under its final name is complete; ``backup_complete`` reads the day's folder
that way. Archive maintenance takes one backup a day with it (#720): it had
copied 5 GB again every hour.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from constants import (
    SQLITE_BACKUP_DIRNAME,
    SQLITE_BACKUP_FILENAMES,
    SQLITE_BACKUP_RETENTION_DAYS,
)
from paths import cache_dir

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


def _day_dir(when: datetime) -> Path:
    return cache_dir() / SQLITE_BACKUP_DIRNAME / when.strftime("%Y-%m-%d")


def backup_complete(*, now: datetime | None = None) -> bool:
    """The day's folder (Eastern date) holds a copy of every local SQLite file that exists."""
    dest = _day_dir(now or datetime.now(tz=_ET))
    return all(
        (dest / name).is_file()
        for name in SQLITE_BACKUP_FILENAMES
        if (cache_dir() / name).is_file()
    )


def backup_sqlite_once(*, now: datetime | None = None) -> dict:
    """Copy the five local SQLite files into cache_dir/backups/{date}/."""
    when = now or datetime.now(tz=_ET)
    date = when.strftime("%Y-%m-%d")
    dest = _day_dir(when)
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    skipped: list[str] = []
    for name in SQLITE_BACKUP_FILENAMES:
        src = cache_dir() / name
        if not src.is_file():
            skipped.append(name)
            continue
        dst = dest / name
        part = dest / f"{name}.part"
        part.unlink(missing_ok=True)
        src_conn = sqlite3.connect(str(src))
        dst_conn = sqlite3.connect(str(part))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()
        os.replace(part, dst)
        copied.append(name)
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
