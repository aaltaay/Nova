"""WAL-safe SQLite backup of the five local DBs."""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.backup as backup


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "cache_dir", lambda: tmp_path)
    yield tmp_path


def test_backup_sqlite_once_copies_existing_db(tmp_path, isolated_cache):
    src = isolated_cache / "journal.db"
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    now = datetime(2026, 8, 17, tzinfo=ZoneInfo("America/New_York"))
    result = backup.backup_sqlite_once(now=now)
    assert result["ok"] is True
    assert "journal.db" in result["copied"]
    dest = isolated_cache / "backups" / "2026-08-17" / "journal.db"
    assert dest.is_file()
    copied = sqlite3.connect(dest)
    try:
        assert copied.execute("SELECT id FROM t").fetchone()[0] == 1
    finally:
        copied.close()


def test_prune_old_backups(isolated_cache):
    old = isolated_cache / "backups" / "2026-01-01"
    old.mkdir(parents=True)
    (old / "journal.db").write_text("x", encoding="utf-8")
    now = datetime(2026, 8, 17, tzinfo=ZoneInfo("America/New_York"))
    removed = backup.prune_old_backups(keep_days=7, now=now)
    assert "2026-01-01" in removed
    assert not old.exists()


def _db(path, value=1):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")
    conn.execute("INSERT INTO t VALUES (?)", (value,))
    conn.commit()
    conn.close()


def test_backup_complete_reads_the_days_folder(isolated_cache):
    """#720: maintenance takes one backup a day instead of copying 5 GB every hour."""
    now = datetime(2026, 8, 17, 21, tzinfo=ZoneInfo("America/New_York"))
    _db(isolated_cache / "journal.db")
    _db(isolated_cache / "archive.db")
    assert backup.backup_complete(now=now) is False
    backup.backup_sqlite_once(now=now)
    assert backup.backup_complete(now=now) is True
    assert backup.backup_complete(now=datetime(2026, 8, 18, 1, tzinfo=ZoneInfo("America/New_York"))) is False


def test_backup_leaves_no_partial_copy_under_its_final_name(isolated_cache):
    """A copy is written as ``.part`` and renamed, so a final name is always a whole copy."""
    now = datetime(2026, 8, 17, 21, tzinfo=ZoneInfo("America/New_York"))
    _db(isolated_cache / "journal.db")
    dest = isolated_cache / "backups" / "2026-08-17"
    dest.mkdir(parents=True)
    (dest / "journal.db.part").write_text("left by a crash", encoding="utf-8")
    backup.backup_sqlite_once(now=now)
    assert sorted(p.name for p in dest.iterdir()) == ["journal.db"]
    copied = sqlite3.connect(dest / "journal.db")
    try:
        assert copied.execute("SELECT id FROM t").fetchone()[0] == 1
    finally:
        copied.close()
