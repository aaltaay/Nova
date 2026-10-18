"""The 5-minute Bollinger signal tables have an in-repo builder (#1068).

`research/bb_mr/data_builder.py` only compacted `sig_5m_ext` / `sig_5m_rth` when they already
existed, so a fresh or `--rebuild` store had no producer for them and step 4 failed on the
missing tables. These pin the rebuilt producer's shape: 5-minute bars closing on the 5-minute
grid, a band warmup that crosses days, and only signalling symbol-days kept.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.bb_mr.signal_5m import ensure_sig_5m  # noqa: E402

SIG_COLUMNS = [
    "ticker", "d", "close_min", "bar_idx", "open", "high", "low", "close", "volume",
    "n20", "sma20", "std20", "n50", "sma50", "std50",
    "n100", "sma100", "std100", "n200", "sma200", "std200",
]
DAY1, DAY2, DAY3 = date(2025, 3, 3), date(2025, 3, 4), date(2025, 3, 5)


def _minute_rows(day: date, first_open: int, last_open: int, dip_at: int | None = None) -> list[tuple]:
    """One-minute bars whose closes alternate 10.0 / 10.2; ``dip_at`` wicks a bar down to 9.0."""
    rows = []
    for i, open_min in enumerate(range(first_open, last_open + 1)):
        close = 10.0 if i % 2 == 0 else 10.2
        low = 9.0 if open_min == dip_at else close - 0.01
        rows.append(("ABC", day, open_min, close, close + 0.01, low, close, 100.0))
    return rows


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("""CREATE TABLE src_1m (ticker VARCHAR, d DATE, open_min SMALLINT, open DOUBLE,
                 high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE)""")
    rows = (
        _minute_rows(DAY1, 200, 959, dip_at=601)        # warmup day with a rejection, but in no universe
        + _minute_rows(DAY2, 240, 959, dip_at=601)      # universe day with a lower-band rejection at 10:01
        + _minute_rows(DAY3, 240, 959)                  # universe day, no rejection
    )
    c.executemany("INSERT INTO src_1m VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    c.execute("CREATE TABLE meta_univ_a AS SELECT 'ABC' AS ticker, d FROM (VALUES (DATE '2025-03-04'), (DATE '2025-03-05')) t(d)")
    c.execute("CREATE TABLE ub_scanner_top20 (ticker VARCHAR, d DATE, close_min SMALLINT)")
    yield c
    c.close()


def test_builds_both_tables_when_missing(con):
    ensure_sig_5m(con, have=set())
    for table in ("sig_5m_ext", "sig_5m_rth"):
        assert [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()] == SIG_COLUMNS


def test_bars_close_on_the_five_minute_grid_inside_each_session(con):
    ensure_sig_5m(con, have=set())
    ext = con.execute("SELECT min(close_min), max(close_min), count(*) FROM sig_5m_ext WHERE d = ?", [DAY2]).fetchone()
    rth = con.execute("SELECT min(close_min), max(close_min), count(*) FROM sig_5m_rth WHERE d = ?", [DAY2]).fetchone()
    assert ext == (245, 960, 144)   # 04:00-16:00 ET
    assert rth == (575, 960, 78)    # 09:30-16:00 ET
    bar = con.execute("SELECT open, high, low, close, volume FROM sig_5m_ext WHERE d = ? AND close_min = 605",
                      [DAY2]).fetchone()
    assert bar == pytest.approx((10.0, 10.21, 9.0, 10.0, 500.0))  # minutes 600-604: first open, last close


def test_band_warmup_crosses_days_and_only_signal_days_are_kept(con):
    ensure_sig_5m(con, have=set())
    days = [r[0] for r in con.execute("SELECT DISTINCT d FROM sig_5m_ext ORDER BY d").fetchall()]
    assert days == [DAY2]  # day 1 rejects but is in no universe; day 3 is in one but never rejects
    first = con.execute("SELECT bar_idx, n20, n200 FROM sig_5m_ext WHERE d = ? ORDER BY close_min LIMIT 1",
                        [DAY2]).fetchone()
    assert first == (144, 20, 145)  # day 1 contributed 144 ext bars of warmup (04:00-16:00)


def test_existing_tables_are_compacted_not_rebuilt(con):
    ensure_sig_5m(con, have=set())
    con.execute("INSERT INTO sig_5m_rth SELECT * REPLACE (DATE '2025-03-05' AS d) FROM sig_5m_rth")
    ensure_sig_5m(con, have={"sig_5m_ext", "sig_5m_rth"})
    days = [r[0] for r in con.execute("SELECT DISTINCT d FROM sig_5m_rth ORDER BY d").fetchall()]
    assert days == [DAY2, DAY3]  # the copied rows still carry the rejection, so compaction keeps them
