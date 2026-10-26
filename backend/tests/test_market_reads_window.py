"""A windowed read parses only the window's lines and returns the frame a whole-day read gives for it (#1062).

A trade chart asks for seven minutes of a stock-day; parsing the whole block (354,206 rows for TIRX on 2023-05-02)
spent about 2 s of CSV work to keep 2,532 rows. The window is now picked from the raw lines first, and only those
lines reach the pandas parse, with each column given the dtype the whole-day parse would give it. No row order is
assumed. The read cache's own tests (test_market_reads_read_cache.py) hold the window to the cached day as well.
"""
from __future__ import annotations

import gzip
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from constants_sim import SIM_MASSIVE_TRADES  # noqa: E402
from market_reads import read_cache, reads  # noqa: E402

DAY = "2023-05-02"
HEADER = ("ticker,conditions,correction,exchange,id,participant_timestamp,price,sequence_number,sip_timestamp,size,"
          "tape,trf_id,trf_timestamp")


def _ns(hhmmss: str) -> int:
    hh, mm, ss = hhmmss.split(":")
    return reads._ns(DAY, f"{hh}:{mm}") + int(ss) * 10**9


def _line(symbol: str, at: str, price: str, *, conditions: str = "", correction: str = "0", size: int = 100,
          trf: str = "0") -> str:
    sip = _ns(at)
    return f"{symbol},{conditions},{correction},4,{sip % 997},{sip - 5},{price},{sip % 9973},{sip},{size},3,0,{trf}"


DEMO = [
    _line("DEMO", "06:59:58", "3.3"),
    _line("DEMO", "07:00:00", "3.31", conditions='"12,37"'),
    _line("DEMO", "07:00:09", "3.32"),
    _line("DEMO", "07:00:10", "3.4", conditions="14", size=300),
    _line("DEMO", "07:00:20", "3.38", correction="1"),             # printed, sets no price
    _line("DEMO", "07:01:30", "3.36", conditions='"14,41"'),
    _line("DEMO", "07:00:30", "3.34"),                             # out of time order: still read
    _line("DEMO", "07:02:00", "3.5"),                              # the window's end is exclusive
    _line("DEMO", "07:05:00", "3.6"),
    _line("DEMO", "09:30:00", "4", correction=""),                 # a gap: correction is float64 all day
]
# A line with no SIP time, and a column that is text on one line (a quoted comma after the time field): either way
# the window cannot be vouched for from its own lines, so the whole day is parsed.
HOLE = [_line("HOLE", "07:00:05", "2.1"), "HOLE,,0,4,1,,2.2,1,,10,3,0,0", _line("HOLE", "09:30:00", "2.3")]
ODD = [_line("ODD", "07:00:05", "5.1"), _line("ODD", "09:30:00", "5.2", trf='"7,8"')]


@pytest.fixture
def day(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(read_cache.SWITCH_ENV, "0")
    path = tmp_path / SIM_MASSIVE_TRADES / DAY[:4] / DAY[5:7] / f"{DAY}.csv.gz"
    path.parent.mkdir(parents=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write(HEADER + "\n" + "\n".join([_line("AAA", "07:00:05", "1"), *DEMO, *HOLE, *ODD,
                                            _line("ZZZ", "07:00:05", "9")]) + "\n")
    return path


@pytest.fixture
def parsed(monkeypatch):
    """How many rows each pandas parse was handed."""
    counts, real = [], reads.pd.read_csv

    def spy(source, *args, **kwargs):
        counts.append(source.getvalue().count(b"\n") - 1)
        return real(source, *args, **kwargs)
    monkeypatch.setattr(reads.pd, "read_csv", spy)
    return counts


def _window_of(whole: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    keep = pd.Series(True, index=whole.index)
    if start:
        keep &= whole["sip_timestamp"] >= _ns(start + ":00")
    if end:
        keep &= whole["sip_timestamp"] < _ns(end + ":00")
    return whole[keep].reset_index(drop=True)


@pytest.mark.parametrize("start,end", [("07:00", "07:02"), ("07:05", None), (None, "07:00"), ("07:00", "09:31")])
def test_a_window_is_the_whole_days_frame_cut_to_it(day, start, end):
    whole = reads.read_file(SIM_MASSIVE_TRADES, "DEMO", DAY)
    window = reads.read_file(SIM_MASSIVE_TRADES, "DEMO", DAY, start, end)
    pd.testing.assert_frame_equal(window, _window_of(whole, start, end), check_exact=True)
    assert {k: v for k, v in window.attrs.items() if k != "seconds"} == \
        {k: v for k, v in whole.attrs.items() if k != "seconds"}


def test_only_the_window_lines_reach_the_csv_parser(day, parsed):
    window = reads.read_file(SIM_MASSIVE_TRADES, "DEMO", DAY, "07:00", "07:02")
    assert parsed == [6] and len(window) == 6
    assert window["correction"].dtype == "float64", "the 09:30 gap makes the whole day's correction float64"
    reads.read_file(SIM_MASSIVE_TRADES, "DEMO", DAY)
    assert parsed == [6, len(DEMO)]


@pytest.mark.parametrize("symbol,lines", [("HOLE", HOLE), ("ODD", ODD)])
def test_a_line_the_probe_cannot_vouch_for_sends_the_read_the_whole_day_way(day, parsed, symbol, lines):
    whole = reads.read_file(SIM_MASSIVE_TRADES, symbol, DAY)
    window = reads.read_file(SIM_MASSIVE_TRADES, symbol, DAY, "07:00", "07:01")
    assert parsed == [len(lines), len(lines)], "the window is never parsed on its own"
    pd.testing.assert_frame_equal(window, _window_of(whole, "07:00", "07:01"), check_exact=True)


def test_an_empty_window_and_an_absent_symbol_match_the_whole_day_way(day):
    for symbol, start, end in (("DEMO", "12:00", "12:05"), ("NOPE", "07:00", "07:02")):
        whole = reads.read_file(SIM_MASSIVE_TRADES, symbol, DAY)
        window = reads.read_file(SIM_MASSIVE_TRADES, symbol, DAY, start, end)
        pd.testing.assert_frame_equal(window, _window_of(whole, start, end) if len(whole) else whole)


def test_windowed_ten_second_bars_equal_the_whole_days_bars_in_the_window(day):
    whole = reads.bars("DEMO", DAY, "10s")
    window = reads.bars("DEMO", DAY, "10s", "07:00", "07:02")
    inside = whole[(whole["time_et"] >= window["time_et"].min()) & (whole["time_et"] <= window["time_et"].max())]
    pd.testing.assert_frame_equal(window.reset_index(drop=True), inside.reset_index(drop=True), check_exact=True)
    # 07:00:20 holds only the original of a trade later corrected (correction 1): it printed, but the consolidated
    # tape counts no volume for it and it sets no price, so that bucket has no bar and is listed as a gap.
    assert window["open"].isna().tolist() == [False, False, False, False]
    assert "07:00:20" not in window["time_et"].dt.strftime("%H:%M:%S").tolist()
    assert any(run["first_et"] == "07:00:20" for run in window.attrs["gaps"])
