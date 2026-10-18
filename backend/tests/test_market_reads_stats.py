"""One stock-day's numbers (``research/market_reads/stats.py``, 2026-10-18), on a tiny fake Massive folder: the
research/orb windows, the minute typical-price VWAP, relative volume by minute against prior sessions, and the
time-weighted NBBO spread that leaves crossed and one-sided quotes out."""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import pytest

pytest.importorskip("pandas")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from market_reads import daily, reads, slots, stats  # noqa: E402
from test_market_reads_daily import write_day_files, write_gz  # noqa: E402

DAY = "2026-09-04"
MINUTE_HEADER = "ticker,volume,open,close,high,low,window_start,transactions"
QUOTE_HEADER = "ticker,ask_price,ask_size,bid_price,bid_size,sip_timestamp"
# (time, open, high, low, close, volume, transactions); the day before closed at 2.00.
TODAY = [("08:00", 2.1, 2.3, 2.0, 2.2, 1000, 10), ("09:00", 2.2, 2.5, 2.2, 2.4, 2000, 20),
         ("09:30", 2.5, 2.8, 2.4, 2.7, 5000, 50), ("09:31", 2.7, 3.0, 2.6, 2.9, 4000, 40),
         ("09:40", 2.9, 2.95, 2.5, 2.6, 3000, 30), ("10:15", 2.6, 2.7, 2.3, 2.4, 2000, 20),
         ("15:59", 2.4, 2.5, 2.4, 2.45, 1000, 10), ("17:00", 2.45, 3.2, 2.45, 3.1, 500, 5)]
PRIOR = [("08:00", 1.0, 1.0, 1.0, 1.0, 500, 5), ("09:30", 1.0, 1.0, 1.0, 1.0, 1000, 10),
         ("12:00", 1.0, 1.0, 1.0, 1.0, 1000, 10)]
# (time, bid, ask): 2c in force at 09:30, then 10c, crossed, one-sided, 1c to the close.
QUOTES = [("09:00", 1.00, 1.02), ("09:40", 1.00, 1.10), ("09:45", 1.05, 1.00), ("09:50", 0.0, 1.01),
          ("09:55", 1.00, 1.01)]


def minute_lines(day: str, bars) -> list[str]:
    return [f"ABC,{v},{o},{c},{h},{low},{reads._ns(day, t)},{tx}" for t, o, h, low, c, v, tx in bars]


@pytest.fixture
def massive(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(slots, "heavy", lambda what, wait=0: contextlib.nullcontext())
    write_day_files(tmp_path)
    write_gz(tmp_path, "minute_aggs_v1", DAY, MINUTE_HEADER, minute_lines(DAY, TODAY))
    for day in ("2026-08-31", "2026-09-01", "2026-09-03"):           # ABC's prior sessions (no 09-02)
        write_gz(tmp_path, "minute_aggs_v1", day, MINUTE_HEADER, minute_lines(day, PRIOR))
    write_gz(tmp_path, "quotes_v1", DAY, QUOTE_HEADER,
             [f"ABC,{a},100,{b},100,{reads._ns(DAY, t)}" for t, b, a in QUOTES])
    daily.clear()
    yield tmp_path
    daily.clear()


def test_the_windows_are_research_orbs(massive):
    s = stats.stock_day_stats("abc", DAY, rvol_days=3)
    assert s["prev_close"] == 2.0 and s["prev_close_day"] == "2026-09-03"
    pm = s["premarket"]
    assert (pm["volume"], pm["high"], pm["high_time"], pm["close"], pm["low"]) == (3000, 2.5, "09:00", 2.4, 2.0)
    f5 = s["first_5min"]
    assert (f5["open"], f5["high"], f5["low"], f5["close"], f5["volume"]) == (2.5, 3.0, 2.4, 2.9, 9000)
    assert f5["change_pct"] == pytest.approx(45.0) and f5["range_pct"] == pytest.approx(24.0)
    f30 = s["first_30min"]
    assert (f30["close"], f30["volume"], f30["high_time"]) == (2.6, 12000, "09:31")
    rth = s["regular"]
    assert (rth["open"], rth["high"], rth["high_time"], rth["low"], rth["low_time"]) == (2.5, 3.0, "09:31", 2.3, "10:15")
    assert (rth["close"], rth["volume"]) == (2.45, 15000)
    whole = s["whole_day"]
    assert (whole["high"], whole["high_time"], whole["volume"]) == (3.2, "17:00", 18500)
    assert s["day_bar"]["close"] == 2.45 and s["day_bar"]["change_pct"] == pytest.approx(22.5)


def test_vwap_is_the_minute_typical_price_and_says_so(massive):
    s = stats.stock_day_stats("ABC", DAY, rvol_days=3)
    rth = [b for b in TODAY if "09:30" <= b[0] < "16:00"]
    want = sum((h + low + c) / 3 * v for _, _, h, low, c, v, _ in rth) / sum(b[5] for b in rth)
    assert s["vwap"]["regular"] == pytest.approx(want)
    assert s["vwap"]["method"] == "approximate, minute typical price"
    assert s["trades"]["regular"] == {"count": 150, "avg_size": 100.0}
    assert s["trades"]["whole_day"]["count"] == 185


def test_relative_volume_by_minute_against_prior_sessions(massive):
    s = stats.stock_day_stats("ABC", DAY, rvol_days=3)
    r = s["rvol"]
    assert r["basis_sessions"] == 3 and r["basis_days"] == ["2026-08-31", "2026-09-01", "2026-09-03"]
    assert r["by_minute"]["09:35"] == {"cum_volume": 12000.0, "avg_cum_volume": 1500.0, "rvol": 8.0}
    assert r["by_minute"]["16:00"]["rvol"] == pytest.approx(18000 / 2500)
    assert r["open5"]["rvol"] == pytest.approx(9.0)
    assert r["daily"] == {"volume": 20000.0, "avg_volume": 2000.0, "rvol": 10.0}


def test_a_shorter_history_says_how_many_sessions_it_used(massive):
    assert stats.stock_day_stats("ABC", DAY, rvol_days=20)["rvol"]["basis_sessions"] == 3


def test_spread_is_time_weighted_and_leaves_bad_quotes_out(massive):
    s = stats.stock_day_stats("ABC", DAY, rvol_days=1)
    first = s["spread"]["first_30min"]
    assert first["median_cents"] == pytest.approx(2.0) and first["quotes"] == 4
    assert first["valid_share"] == pytest.approx(20 / 30)
    regular = s["spread"]["regular"]
    assert regular["median_cents"] == pytest.approx(1.0)
    assert regular["median_bps"] == pytest.approx(0.01 / 1.005 * 1e4, abs=0.01)
    assert s["day_bar"]["transactions"] == 200
    assert stats.stock_day_stats("ABC", DAY, rvol_days=1, spread=False)["spread"] is None


def test_a_day_the_symbol_did_not_trade_is_refused(massive):
    with pytest.raises(LookupError, match="did not trade"):
        stats.stock_day_stats("ABC", "2026-09-02")
    with pytest.raises(ValueError, match="rvol_days"):
        stats.stock_day_stats("ABC", DAY, rvol_days=500)


def test_the_answer_explains_its_methods(massive):
    s = stats.stock_day_stats("ABC", DAY, rvol_days=1)
    for key in ("vwap", "spread", "rvol_by_minute", "raw", "windows"):
        assert key in s["rules"]
    assert set(s["seconds"]) >= {"day_files", "minutes", "prior_minutes", "quotes", "total"}
