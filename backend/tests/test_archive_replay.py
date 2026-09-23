"""Cold-day reads in archive/replay.py (fixture JSONL day).

The decide() replay and the evening review were retired (ADR 025); the bar
reads and the no-hindsight slice stay because the backtest engine uses them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.capture as capture
import archive.compact as compact
import archive.db as archive_db
import archive.replay as replay
from constants import ARCHIVE_SOURCE_IBKR


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(compact, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    capture.clear_l2_stub_for_tests()
    yield tmp_path


def _seed_replay_day(session_date: str = "2026-07-10") -> None:
    # Pre-market through open-ish bars so setups have something to chew on.
    base = 1_720_000_000.0
    for i in range(30):
        px = 10.0 + i * 0.05
        capture.record_bar(
            symbol="TEST",
            ts=base + i * 60,
            open_=px,
            high=px + 0.1,
            low=px - 0.05,
            close=px + 0.02,
            volume=50_000 + i * 100,
            source=ARCHIVE_SOURCE_IBKR,
            timeframe="1m",
            session_date=session_date,
        )
    capture.record_tape_print(
        symbol="TEST",
        ts=base + 100,
        price=10.5,
        size=200,
        source=ARCHIVE_SOURCE_IBKR,
        session_date=session_date,
    )
    compact.compact_day(session_date)


class TestNoHindsight:
    """P9 hardening: a replayed moment never sees bars that had not closed."""

    def test_slice_bars_as_of_requires_the_interval_to_have_closed(self):
        """#385: ``ts`` is the bar's OPENING stamp, so a 1m bar opening at 100
        is only known from 160 onward — inclusive at close, never before."""
        bars = [{"ts": 100.0}, {"ts": 200.0}, {"ts": 300.0}]
        assert replay.slice_bars_as_of(bars, 105.0) == []       # +5s into the minute
        assert replay.slice_bars_as_of(bars, 159.0) == []       # one second early
        assert replay.slice_bars_as_of(bars, 160.0) == [{"ts": 100.0}]  # exact close
        assert replay.slice_bars_as_of(bars, 161.0) == [{"ts": 100.0}]
        assert replay.slice_bars_as_of(bars, 260.0) == [{"ts": 100.0}, {"ts": 200.0}]
        assert replay.slice_bars_as_of(bars, 50.0) == []
        assert replay.slice_bars_as_of(bars, 360.0) == bars

    def test_final_minute_ohlcv_is_not_revealed_before_close(self):
        """The issue's own probe, as an executable regression (#385).

        A bar opening at 1789738200 must not hand its high/close/volume to a
        decision made 55 seconds before that minute ends — and must hand them
        over once it has closed. We suppress lookahead, not data.
        """
        bar = {"ts": 1789738200.0, "o": 100.0, "h": 200.0, "l": 99.0, "c": 99.0, "v": 1000}
        early = replay.slice_bars_as_of([bar], 1789738205.0)
        assert early == []

        at_close = replay.slice_bars_as_of([bar], 1789738260.0)
        assert at_close == [bar]


class TestColdDayReads:
    def test_bars_by_symbol_for_day_reads_the_compacted_day_sorted(self):
        _seed_replay_day()
        by_symbol = replay.bars_by_symbol_for_day("2026-07-10")
        bars = by_symbol["TEST"]
        assert len(bars) == 30
        assert [b["ts"] for b in bars] == sorted(b["ts"] for b in bars)
        assert set(bars[0]) >= {"t", "o", "h", "l", "c", "v", "ts"}

    def test_missing_day_reads_as_empty(self):
        assert replay.bars_by_symbol_for_day("1999-01-01") == {}
