"""Nasdaq halt history: padded halt times keep their start, ``--dry-run`` writes nothing (#1069), and a bot-check
page is never kept as a downloaded day (#1075).

The raw pages are the repo's fixtures copied into a temp directory, and the leaderboard store is a temp file -- never
F:. ``download()`` reads a fake Nasdaq (``_fetch`` patched): never the network.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

RESEARCH = Path(__file__).resolve().parents[2] / "research" / "catalysts"
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

import backfill_halts  # noqa: E402  (research/catalysts/backfill_halts.py)

FIXTURES = Path(__file__).with_name("fixtures")
PADDED = FIXTURES / "nasdaq_trade_halts_padded_time.xml"
BOT_CHECK = FIXTURES / "nasdaq_trade_halts_bot_check.html"   # made up, shaped like Nasdaq's Incapsula answer
RSS = FIXTURES / "nasdaq_trade_halts_xyz.xml"                 # made up: one XYZ halt on 2026-01-05
NO_HALTS = FIXTURES / "nasdaq_trade_halts_empty.xml"          # RSS with no items, under 200 bytes
DAY = date(2026, 1, 5)


@pytest.fixture
def store(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    shutil.copy(PADDED, raw / "2026-06-15.xml")
    monkeypatch.setattr(backfill_halts, "RAW", raw)
    monkeypatch.setenv("NOVA_LEADERBOARD_DIR", str(tmp_path / "leaderboard"))
    return tmp_path / "leaderboard" / "leaderboard.sqlite3"


@pytest.fixture
def nasdaq(tmp_path, monkeypatch):
    """``download()`` over one trading day into a temp raw folder. Nasdaq answers ``answers`` in order, the last
    one again for every later ask; ``asked`` lists the days it was asked for."""
    raw = tmp_path / "raw"
    monkeypatch.setattr(backfill_halts, "RAW", raw)
    monkeypatch.setenv("NOVA_LEADERBOARD_DIR", str(tmp_path / "leaderboard"))
    monkeypatch.setattr(backfill_halts, "trading_days", lambda: [DAY])
    monkeypatch.setattr(backfill_halts, "RETRY_PAUSE_SEC", 0.0)
    monkeypatch.setattr(backfill_halts, "DAY_PAUSE_SEC", 0.0)
    asked: list[date] = []
    answers: list[bytes] = []

    def fetch(d: date) -> bytes:
        asked.append(d)
        return answers.pop(0) if len(answers) > 1 else answers[0]

    monkeypatch.setattr(backfill_halts, "_fetch", fetch)
    return SimpleNamespace(raw=raw, page=raw / f"{DAY.isoformat()}.xml", asked=asked, answers=answers,
                           store=tmp_path / "leaderboard" / "leaderboard.sqlite3")


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


def test_the_parser_reads_the_rss_fixtures_and_not_the_bot_check():
    assert backfill_halts.is_rss(RSS.read_bytes()) and backfill_halts.is_rss(NO_HALTS.read_bytes())
    assert not backfill_halts.is_rss(BOT_CHECK.read_bytes())


def test_a_stored_bot_check_page_is_asked_for_again_and_its_halts_then_load(nasdaq, capsys):
    nasdaq.raw.mkdir()
    shutil.copy(BOT_CHECK, nasdaq.page)
    assert nasdaq.page.stat().st_size > 200        # the old rule (any page over 200 bytes) kept it as the day
    nasdaq.answers.append(RSS.read_bytes())
    backfill_halts.download()
    assert nasdaq.asked == [DAY]
    assert nasdaq.page.read_bytes() == RSS.read_bytes()
    assert "download: 1 new pages; 0 already on disk; 0 days without an RSS page" in capsys.readouterr().out
    backfill_halts.load()
    assert _events(nasdaq.store) == [("XYZ", "end", "LUDP"), ("XYZ", "start", "LUDP")]


def test_a_bot_check_answer_is_not_saved_as_the_day_and_the_next_run_asks_again(nasdaq, capsys):
    nasdaq.answers.append(BOT_CHECK.read_bytes())
    backfill_halts.download()
    out = capsys.readouterr().out
    assert not nasdaq.page.exists()
    assert len(nasdaq.asked) == backfill_halts.ATTEMPTS
    assert "the answer is not RSS" in out and "a bot-check page is not saved" in out
    assert f"{DAY}: no RSS after {backfill_halts.ATTEMPTS} attempts; not saved as the day" in out
    assert "download: 0 new pages; 0 already on disk; 1 days without an RSS page" in out

    nasdaq.answers[:] = [RSS.read_bytes()]
    backfill_halts.download()
    assert nasdaq.page.read_bytes() == RSS.read_bytes()


def test_a_bot_check_answer_is_retried_and_the_rss_that_follows_is_kept(nasdaq):
    nasdaq.answers.extend([BOT_CHECK.read_bytes(), RSS.read_bytes()])
    backfill_halts.download()
    assert nasdaq.asked == [DAY, DAY]
    assert nasdaq.page.read_bytes() == RSS.read_bytes()


@pytest.mark.parametrize("page", [RSS, NO_HALTS], ids=["a day with a halt", "a day with no halts"])
def test_a_stored_rss_page_is_never_asked_for_again(nasdaq, page, capsys):
    nasdaq.raw.mkdir()
    shutil.copy(page, nasdaq.page)
    nasdaq.answers.append(BOT_CHECK.read_bytes())
    backfill_halts.download()
    assert nasdaq.asked == []
    assert nasdaq.page.read_bytes() == page.read_bytes()
    assert "download: 0 new pages; 1 already on disk; 0 days without an RSS page" in capsys.readouterr().out
