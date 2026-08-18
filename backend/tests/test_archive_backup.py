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
