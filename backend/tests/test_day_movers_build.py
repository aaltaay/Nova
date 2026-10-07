"""The day movers builder (ADR 050): one row per stock per session that moved, from tiny synthetic Massive files.

The prior close is the session before's official close, on today's share basis through a listed split; the high
and low count premarket and after hours from the minute bars, with the first minute that printed them; the marks
are the first minute the high reached +N%; a quiet stock is counted, not stored; a split suspect is kept.
"""
from __future__ import annotations

import gzip
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("pandas")

RESEARCH = Path(__file__).resolve().parents[2] / "research"
for folder in (RESEARCH / "movers", RESEARCH / "leaderboard"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import build_movers as bm  # noqa: E402
import lb_io  # noqa: E402

from day_movers import store  # noqa: E402

ET = ZoneInfo("America/New_York")
HEADER = "ticker,volume,open,close,high,low,window_start,transactions\n"
D0, D1 = date(2026, 6, 1), date(2026, 6, 2)


def ts(d: date, hh: int, mm: int) -> int:
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).timestamp())


def _path(root: Path, kind: str, d: date) -> Path:
    p = root / kind / f"{d:%Y}" / f"{d:%m}" / f"{d.isoformat()}.csv.gz"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def write_days(root: Path, d: date, bars: dict[str, tuple[float, float, float, float, float]]) -> Path:
    """bars: ticker -> (open, high, low, close, volume), the regular session."""
    path = _path(root, "day_aggs_v1", d)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(HEADER)
        for t, (o, h, lo, c, v) in sorted(bars.items()):
            fh.write(f"{t},{v},{o},{c},{h},{lo},{ts(d, 0, 0) * 1_000_000_000},1\n")
    return path


def write_minutes(root: Path, d: date, bars: list[tuple]) -> Path:
    """bars: (ticker, hh, mm, open, high, low, close, volume)."""
    path = _path(root, "minute_aggs_v1", d)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(HEADER)
        for t, hh, mm, o, h, lo, c, v in sorted(bars, key=lambda b: (b[0], b[1], b[2])):
            fh.write(f"{t},{v},{o},{c},{h},{lo},{ts(d, hh, mm) * 1_000_000_000},1\n")
    return path


@pytest.fixture
def files(tmp_path):
    root = tmp_path / "massive"
    prev = write_days(root, D0, {
        "RUN": (1.0, 1.1, 0.9, 1.0, 100_000), "QUIET": (10.0, 10.1, 9.9, 10.0, 50_000),
        "SPLT": (0.5, 0.52, 0.48, 0.5, 2_000_000), "SUSP": (0.5, 0.52, 0.48, 0.5, 3_000_000),
        "WARRW": (0.1, 0.1, 0.1, 0.1, 1000),
    })
    today = write_days(root, D1, {
        "RUN": (1.2, 3.5, 1.1, 3.0, 9_000_000), "QUIET": (10.0, 10.2, 9.9, 10.1, 60_000),
        "SPLT": (5.0, 6.0, 4.9, 5.8, 150_000), "SUSP": (5.0, 5.2, 4.9, 5.1, 100_000),
        "WARRW": (0.3, 0.5, 0.3, 0.45, 10_000), "IPO": (10.0, 14.0, 9.0, 13.0, 1_000_000),
    })
    minutes = write_minutes(root, D1, [
        ("RUN", 7, 0, 1.0, 1.15, 1.0, 1.1, 1000),      # premarket: +15% at 07:00
        ("RUN", 8, 30, 1.1, 1.25, 1.1, 1.2, 2000),     # +25%
        ("RUN", 9, 45, 1.3, 2.5, 1.3, 2.4, 50_000),    # +150%
        ("RUN", 10, 5, 2.4, 3.5, 2.3, 3.2, 90_000),    # the regular high, +250%
        ("RUN", 16, 30, 3.0, 4.2, 2.9, 4.0, 20_000),   # after hours: the day's high, +320%
        ("QUIET", 10, 0, 10.0, 10.2, 9.9, 10.1, 1000),
    ])
    return {"root": root, "prev": prev, "today": today, "minutes": minutes}


def build(files, splits=()):
    by_ticker = lb_io.splits_by_ticker(list(splits))
    types = {"RUN": "CS", "QUIET": "CS", "SPLT": "CS", "SUSP": "CS", "WARRW": "WARRANT"}
    return bm.build_session(bm.work_db(1), D1, prev_date=D0, day_file=files["today"], prev_file=files["prev"],
                            minute_file=files["minutes"], types=types, by_ticker=by_ticker)


def test_a_runner_carries_premarket_and_after_hours_and_its_marks(files):
    meta, rows = build(files)
    run = next(r for r in rows if r["symbol"] == "RUN")
    assert run["prev_close"] == pytest.approx(1.0)
    assert (run["open"], run["high"], run["close"]) == (1.2, 3.5, 3.0)          # the regular day bar
    assert run["pm_high"] == pytest.approx(1.25) and run["ah_high"] == pytest.approx(4.2)
    assert run["day_high"] == pytest.approx(4.2) and run["day_high_ts"] == ts(D1, 16, 30)
    assert run["high_pct"] == pytest.approx(3.2) and run["close_pct"] == pytest.approx(2.0)
    assert run["gap_pct"] == pytest.approx(0.2)
    assert run["up10_ts"] == ts(D1, 7, 0) and run["up20_ts"] == ts(D1, 8, 30)
    assert run["up100_ts"] == ts(D1, 9, 45) and run["up300_ts"] == ts(D1, 16, 30)
    assert run["kind"] == "CS" and run["split_suspect"] == 0
    assert meta["tickers"] == 6 and meta["minute_bars"] == 1 and meta["rows"] == len(rows)


def test_a_quiet_stock_is_counted_not_stored_and_a_new_listing_needs_a_range(files):
    _, rows = build(files)
    symbols = {r["symbol"] for r in rows}
    assert "QUIET" not in symbols
    ipo = next(r for r in rows if r["symbol"] == "IPO")      # no prior close; its high is 55% over its low
    assert ipo["prev_close"] is None and ipo["high_pct"] is None


def test_a_listed_split_puts_the_prior_close_on_todays_basis_and_an_unlisted_jump_is_a_suspect(files):
    split = lb_io.Split("SPLT", D1, 10.0, 1.0)                  # 1-for-10 reverse split executing today
    _, rows = build(files, [split])
    splt = next(r for r in rows if r["symbol"] == "SPLT")
    assert splt["prev_close"] == pytest.approx(5.0) and splt["split_listed"] == 1
    assert splt["prev_volume"] == pytest.approx(200_000) and splt["split_suspect"] == 0
    susp = next(r for r in rows if r["symbol"] == "SUSP")        # the same jump, no split listed: kept, flagged
    assert susp["split_suspect"] == 1 and susp["high_pct"] == pytest.approx(9.4)


def test_a_session_is_written_whole_and_the_builder_skips_it_after(files, tmp_path):
    meta, rows = build(files)
    target = tmp_path / "movers.sqlite3"
    with store.connect(target) as db:
        store.replace_session(db, meta, rows)
        store.replace_session(db, meta, rows)                    # idempotent: replaced, not doubled
        assert db.execute("SELECT count(*) FROM movers").fetchone()[0] == len(rows)
        done = bm.built(db)
    minute = {D1: files["minutes"]}
    assert bm.wanted([D1], done, minute, rebuild=False) == []
    assert bm.wanted([D1], done, minute, rebuild=True) == [D1]


def test_a_session_built_before_its_minute_file_arrived_is_built_again(files, tmp_path):
    meta, rows = bm.build_session(bm.work_db(1), D1, prev_date=D0, day_file=files["today"],
                                  prev_file=files["prev"], minute_file=None, types={}, by_ticker={})
    assert meta["minute_bars"] == 0 and "premarket" in meta["note"]
    run = next(r for r in rows if r["symbol"] == "RUN")
    assert run["day_high"] == 3.5 and run["day_high_ts"] is None and run["pm_high"] is None
    with store.connect(tmp_path / "m.sqlite3") as db:
        store.replace_session(db, meta, rows)
        done = bm.built(db)
    assert bm.wanted([D1], done, {D1: files["minutes"]}, rebuild=False) == [D1]
