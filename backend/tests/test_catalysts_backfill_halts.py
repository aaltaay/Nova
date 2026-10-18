"""Nasdaq halt history load: padded halt times keep their start, and ``--dry-run`` writes nothing (#1069).

The raw page is the repo's padded fixture (one real 2026-06-15 item) copied into a temp directory, and the
leaderboard store is a temp file -- never F:.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

RESEARCH = Path(__file__).resolve().parents[2] / "research" / "catalysts"
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

import backfill_halts  # noqa: E402  (research/catalysts/backfill_halts.py)

PADDED = Path(__file__).with_name("fixtures") / "nasdaq_trade_halts_padded_time.xml"


@pytest.fixture
def store(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    shutil.copy(PADDED, raw / "2026-06-15.xml")
    monkeypatch.setattr(backfill_halts, "RAW", raw)
    monkeypatch.setenv("NOVA_LEADERBOARD_DIR", str(tmp_path / "leaderboard"))
    return tmp_path / "leaderboard" / "leaderboard.sqlite3"


def _events(path: Path) -> list[tuple]:
    with sqlite3.connect(path) as db:
        return db.execute("SELECT symbol, event, code FROM halt_events ORDER BY event").fetchall()


def test_load_keeps_the_start_of_a_padded_halt_time(store):
    backfill_halts.load()
    assert _events(store) == [("ROKU", "end", "T3"), ("ROKU", "start", "T3")]


def test_dry_run_counts_the_missing_start_and_writes_nothing(store, capsys):
    backfill_halts.load()
    with sqlite3.connect(store) as db:
        db.execute("DELETE FROM halt_events WHERE event = 'start'")
    capsys.readouterr()
    backfill_halts.load(dry_run=True)
    out = capsys.readouterr().out
    assert "1 would be new ({'start': 1})" in out
    assert "nothing written" in out
    assert _events(store) == [("ROKU", "end", "T3")]


def test_dry_run_without_a_store_refuses_and_creates_none(store):
    with pytest.raises(SystemExit):
        backfill_halts.load(dry_run=True)
    assert not store.exists()
