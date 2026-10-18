"""Daily bars and the market's day from Massive's day files (``research/market_reads/daily.py``, 2026-10-18), on a
tiny fake Massive folder: raw rows, prev_close from before the range, split adjustment per day, no look-ahead."""
from __future__ import annotations

import contextlib
import gzip
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("pandas")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import daily, reads, slots  # noqa: E402

HEADER = "ticker,volume,open,close,high,low,window_start,transactions"
ETF_CLOSES = {"SPY": 98.8, "QQQ": 98.2, "IWM": 97.7}
# ABC: did not trade 09-02; 09-08 is after every day asked about and must never be read into one.
ABC = {"2026-08-31": (2000, 0.9, 1.0, 1.05, 0.85, 20), "2026-09-01": (2000, 1.1, 1.2, 1.3, 1.0, 20),
       "2026-09-03": (2000, 1.5, 2.0, 2.1, 1.4, 20), "2026-09-04": (20000, 2.5, 2.45, 3.0, 2.3, 200),
       "2026-09-08": (9, 99.0, 99.0, 99.0, 99.0, 1)}
SESSIONS = ("2026-08-26", "2026-08-27", "2026-08-28", "2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03",
            "2026-09-04", "2026-09-08")


def write_gz(root: Path, dataset: str, day: str, header: str, lines: list[str]) -> Path:
    path = root / dataset / day[:4] / day[5:7] / f"{day}.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write(header + "\n" + "\n".join(lines) + "\n")
    return path


def day_line(ticker: str, day: str, volume, o, c, h, low, tx) -> str:
    return f"{ticker},{volume},{o},{c},{h},{low},{reads._ns(day, '00:00')},{tx}"


def write_day_files(root: Path) -> None:
    for day in SESSIONS:
        rows = []
        if day in ABC:
            rows.append(day_line("ABC", day, *ABC[day]))
        rows.append(day_line("ABCD", day, 7, 50.0, 50.0, 50.0, 50.0, 1))     # a longer ticker never matches ABC
        for etf, last in sorted(ETF_CLOSES.items()):
            close = last if day == "2026-09-04" else 50.0 if day == "2026-09-08" else 100.0
            rows.append(day_line(etf, day, 1000, 99.0 if day == "2026-09-04" else 100.0, close, 100.5, 97.0, 10))
        write_gz(root, "day_aggs_v1", day, HEADER, sorted(rows))


@pytest.fixture
def massive(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(slots, "heavy", lambda what, wait=0: contextlib.nullcontext())
    write_day_files(tmp_path)
    daily.clear()
    yield tmp_path
    daily.clear()


def test_daily_bars_are_raw_rows_with_prev_close_from_before_the_range(massive):
    frame = daily.daily_bars("abc", "2026-09-01", "2026-09-04")
    assert list(frame["date"]) == ["2026-09-01", "2026-09-03", "2026-09-04"]       # 09-02 not traded: no row
    assert list(frame["prev_close"]) == pytest.approx([1.0, 1.2, 2.0])               # 08-31's close for the first
    assert list(frame["change_pct"]) == pytest.approx([20.0, 200 / 3, 22.5])
    assert list(frame["gap_pct"]) == pytest.approx([10.0, 25.0, 25.0])
    assert frame["range_pct"].iloc[0] == pytest.approx((1.3 - 1.0) / 1.1 * 100)
    assert frame["high_pct"].iloc[2] == pytest.approx(50.0)
    assert list(frame["transactions"]) == [20, 20, 200]
    assert frame.attrs["adjusted"] is False and "04:00-20:00" in frame.attrs["volume_note"]
    assert frame.attrs["prev_close_from"] == "2026-08-31"


def test_a_range_longer_than_the_cap_is_refused(massive):
    with pytest.raises(ValueError, match="longer than"):
        daily.daily_bars("ABC", "2016-01-04", "2026-01-04")
    with pytest.raises(ValueError, match="before"):
        daily.daily_bars("ABC", "2026-09-04", "2026-09-01")


def test_adjust_puts_each_day_in_one_days_terms(massive, monkeypatch):
    """A 1-for-10 reverse split on 09-03: days before it x10, volume / 10, and 09-03 is no fake +1567%."""
    pytest.importorskip("duckdb")
    from market_reads import splits
    calls = []

    def factor(symbol, day, as_of=None, cik=None):
        calls.append((symbol, day, as_of))
        return 10.0 if day < "2026-09-03" else 1.0

    monkeypatch.setattr(splits, "factor", factor)
    frame = daily.daily_bars("ABC", "2026-09-01", "2026-09-04", adjust=True, as_of="2026-09-05")
    assert list(frame["split_factor"]) == [10.0, 1.0, 1.0]
    assert list(frame["close"]) == pytest.approx([12.0, 2.0, 2.45])
    assert list(frame["volume"]) == pytest.approx([200.0, 2000.0, 20000.0])
    assert list(frame["prev_close"]) == pytest.approx([10.0, 12.0, 2.0])
    assert frame["change_pct"].iloc[1] == pytest.approx((2.0 / 12.0 - 1) * 100)
    assert ("ABC", "2026-08-31", "2026-09-05") in calls and frame.attrs["adjusted_to"] == "2026-09-05"
    assert "company that held the ticker" in frame.attrs["split_note"]


def test_a_rewritten_day_file_is_read_again(massive):
    assert daily.daily_bars("ABC", "2026-09-04", "2026-09-04")["close"].iloc[0] == 2.45
    path = write_gz(massive, "day_aggs_v1", "2026-09-04", HEADER, [day_line("ABC", "2026-09-04", 1, 3, 3.3, 3, 3, 1)])
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))
    assert daily.daily_bars("ABC", "2026-09-04", "2026-09-04")["close"].iloc[0] == 3.3


def test_market_context_reads_nothing_after_the_day(massive):
    answer = daily.market_context("2026-09-04", lookback=5)
    spy = answer["symbols"]["SPY"]
    assert spy["change_pct"] == pytest.approx(-1.2) and spy["gap_pct"] == pytest.approx(-1.0)
    assert spy["return_5_pct"] == pytest.approx(-1.2) and spy["return_lookback_pct"] == pytest.approx(-1.2)
    assert spy["avg_close_lookback"] == pytest.approx((4 * 100 + 98.8) / 5)
    assert spy["range_pct"] == pytest.approx(3.5 / 99 * 100)
    assert answer["summary"] == "SPY -1.2%, QQQ -1.8%, IWM -2.3%: a down day, small caps weakest"
    assert "only sessions on or before day" in answer["rules"]["as_of"]


def test_market_context_refuses_a_day_with_no_file(massive):
    with pytest.raises(LookupError, match="not a session"):
        daily.market_context("2026-09-05")
    with pytest.raises(ValueError, match="lookback"):
        daily.market_context("2026-09-04", lookback=1000)


def test_market_context_says_when_a_symbol_did_not_trade(massive):
    answer = daily.market_context("2026-09-02", symbols=("SPY", "ABC"), lookback=5)
    assert answer["symbols"]["ABC"] == {"traded": False} and answer["symbols"]["SPY"]["traded"] is True
