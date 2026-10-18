"""Halts through the front door (``research/market_reads/halts.py``): one row per halt, a start paired with its
resumption even on a later day, a resumption whose start the log lacks answered as such (never invented), and many
stock-days answered at once without double-counting the two sources."""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import halts  # noqa: E402

ET = ZoneInfo("America/New_York")
RSS, IB = "nasdaq_trade_halt_rss", "ibkr_ticker_halted"
DDL = """CREATE TABLE halt_events (symbol TEXT NOT NULL, ts REAL NOT NULL, event TEXT NOT NULL, kind TEXT,
    code TEXT, source TEXT NOT NULL, session_date TEXT NOT NULL, recorded_ts REAL NOT NULL,
    PRIMARY KEY (symbol, source, event, ts));
CREATE INDEX halt_events_day ON halt_events(session_date, symbol, ts);"""


def ts(day: str, hhmmss: str) -> float:
    return datetime.fromisoformat(f"{day}T{hhmmss}").replace(tzinfo=ET).timestamp()


def ev(symbol, day, hhmmss, event, code, source=RSS, kind=None):
    t = ts(day, hhmmss)
    return (symbol, t, event, code if kind is None else kind, code, source, day, t)


EVENTS = [
    ev("RUNR", "2024-05-01", "09:41:00", "start", "LUDP"), ev("RUNR", "2024-05-01", "09:46:00", "end", "LUDP"),
    ev("RUNR", "2024-05-01", "10:02:30", "start", "LUDP"), ev("RUNR", "2024-05-01", "10:07:30", "end", "LUDP"),
    ev("NEWS", "2024-05-01", "15:50:00", "start", "T3"), ev("NEWS", "2024-05-02", "09:30:00", "end", "T3"),
    ev("GONE", "2026-06-15", "07:30:00", "end", "T3"),                           # Nasdaq's start time unparsed
    ev("BOTH", "2026-10-01", "10:00:00", "start", "LUDP"), ev("BOTH", "2026-10-01", "10:05:00", "end", "LUDP"),
    ev("BOTH", "2026-10-01", "10:00:01", "start", "2", source=IB, kind="luld"),
    ev("BOTH", "2026-10-01", "10:05:02", "end", None, source=IB),
    ev("IBONLY", "2026-10-02", "11:00:00", "start", "2", source=IB, kind="luld"),
    ev("IBONLY", "2026-10-02", "11:05:00", "end", None, source=IB),
]


@pytest.fixture
def log(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_LEADERBOARD_DIR", str(tmp_path))
    db = sqlite3.connect(tmp_path / "leaderboard.sqlite3")
    db.executescript(DDL)
    db.executemany("INSERT INTO halt_events VALUES (?,?,?,?,?,?,?,?)", EVENTS)
    db.commit()
    db.close()
    return tmp_path


def test_a_start_is_paired_with_its_resumption(log):
    frame = halts.halts(symbol="runr", day="2024-05-01")
    assert list(frame["start_et"]) == ["09:41:00", "10:02:30"]
    assert list(frame["end_et"]) == ["09:46:00", "10:07:30"]
    assert list(frame["duration_s"]) == [300.0, 300.0] and frame["resumed"].all()
    assert frame.attrs["rule"].startswith("a halt counts at its start") and "2021-09-21" in frame.attrs["coverage"]


def test_a_halt_resumed_next_day_counts_on_the_day_it_started(log):
    started = halts.halts(symbol="NEWS", day="2024-05-01")
    assert len(started) == 1 and started.iloc[0]["end_date"] == "2024-05-02" and bool(started.iloc[0]["resumed"])
    assert started.iloc[0]["duration_s"] == pytest.approx(ts("2024-05-02", "09:30:00") - ts("2024-05-01", "15:50:00"))
    assert halts.halts(symbol="NEWS", day="2024-05-02").empty


def test_a_resumption_without_a_logged_start_keeps_its_start_unknown(log):
    import pandas as pd
    row = halts.halts(day="2026-06-15").iloc[0]
    assert row["symbol"] == "GONE" and pd.isna(row["start_ts"]) and row["start_et"] is None
    assert row["end_et"] == "07:30:00" and bool(row["resumed"]) and row["code"] == "T3"


def test_a_read_without_a_symbol_or_a_day_is_refused(log):
    with pytest.raises(ValueError, match="needs a symbol, a day or a date range"):
        halts.halts()
    with pytest.raises(ValueError, match="not both"):
        halts.events(day="2024-05-01", date_from="2024-05-01")


def test_events_are_the_raw_log_and_a_source_alias_filters(log):
    raw = halts.events(symbol="BOTH", source="ibkr")
    assert list(raw["event"]) == ["start", "end"] and set(raw["source"]) == {IB}
    assert list(raw["et"]) == ["10:00:01", "10:05:02"]
    assert len(halts.halts(symbol="BOTH")) == 2                  # one halt, seen by both sources
    with pytest.raises(ValueError, match="one of"):
        halts.events(symbol="BOTH", source="cboe")


def test_for_pairs_answers_many_stock_days_one_source_each(log):
    out = halts.for_pairs([("2024-05-01", "RUNR"), ("2024-05-01", "NEWS"), ("2026-10-01", "both"),
                           ("2026-10-02", "IBONLY"), ("2026-06-15", "GONE"), ("2024-05-01", "QUIET"),
                           ("2020-01-02", "RUNR")])
    assert out[("2024-05-01", "RUNR")] == {"halts": 2, "first_halt_et": "09:41:00", "codes": ["LUDP"], "luld": 2,
                                           "news": 0, "start_unknown": 0, "source": RSS, "covered": True}
    assert out[("2024-05-01", "NEWS")]["news"] == 1 and out[("2024-05-01", "NEWS")]["luld"] == 0
    assert out[("2026-10-01", "BOTH")]["halts"] == 1 and out[("2026-10-01", "BOTH")]["source"] == RSS
    assert out[("2026-10-02", "IBONLY")] == {"halts": 1, "first_halt_et": "11:00:00", "codes": ["2"], "luld": 1,
                                             "news": 0, "start_unknown": 0, "source": IB, "covered": True}
    gone = out[("2026-06-15", "GONE")]
    assert gone["halts"] == 1 and gone["start_unknown"] == 1 and gone["first_halt_et"] is None
    assert out[("2024-05-01", "QUIET")]["halts"] == 0                   # covered: none logged is none
    assert out[("2020-01-02", "RUNR")]["halts"] is None                 # before the backfill: unknown, not 0


def test_for_pairs_chunks_its_reads(log, monkeypatch):
    monkeypatch.setattr(halts, "_PARAM_CHUNK", 3)
    pairs = [("2024-05-01", "RUNR"), ("2024-05-02", "NEWS"), ("2026-10-01", "BOTH"), ("2026-10-02", "IBONLY")]
    out = halts.for_pairs(pairs)
    assert [out[p]["halts"] for p in pairs] == [2, 0, 1, 1]


def test_a_missing_store_says_where_it_looked(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_LEADERBOARD_DIR", str(tmp_path / "nowhere"))
    with pytest.raises(LookupError, match="not on disk"):
        halts.halts(symbol="RUNR")
