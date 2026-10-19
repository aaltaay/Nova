"""A windowed read parses only the window's lines and returns exactly the rows a whole-block read would (#1062).

A trade chart asks for seven minutes of a stock-day; parsing the whole block (354,206 rows for TIRX on 2023-05-02)
spent about 2 s of CSV and print-rule work to keep 2,532 rows. The window is applied to the raw lines first, from
their own time field, so only the window's lines reach the CSV parser. No row order is assumed.
"""
from __future__ import annotations

import gzip
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from constants_sim import SIM_MASSIVE_TRADES  # noqa: E402
from market_reads import reads  # noqa: E402

DAY = "2023-05-02"
HEADER = ("ticker,conditions,correction,exchange,id,participant_timestamp,price,sequence_number,sip_timestamp,size,"
          "tape,trf_id,trf_timestamp")


def _ns(hhmmss: str) -> int:
    hh, mm, ss = hhmmss.split(":")
    return reads._ns(DAY, f"{hh}:{mm}") + int(ss) * 10**9


def _line(symbol: str, at: str, price: float, *, conditions: str = "", correction: int = 0, size: int = 100,
          trf: str = "") -> str:
    sip = _ns(at)
    return f"{symbol},{conditions},{correction},4,{sip % 997},{sip - 5},{price},{sip % 9973},{sip},{size},3,,{trf}"


def _write_day(root: Path) -> list[str]:
    demo = [
        _line("DEMO", "06:59:58", 3.30),
        _line("DEMO", "07:00:00", 3.31, conditions='"12,37"'),
        _line("DEMO", "07:00:09", 3.32),
        _line("DEMO", "07:00:10", 3.40, conditions="14", size=300),
        _line("DEMO", "07:00:20", 3.38, correction=1),             # a cancel: no trade
        _line("DEMO", "07:01:30", 3.36, conditions='"14,41"'),
        _line("DEMO", "07:00:30", 3.34),                           # out of time order: still read
        _line("DEMO", "07:02:00", 3.50),                           # the window's end is exclusive
        _line("DEMO", "07:05:00", 3.60, trf='"7,8"'),              # a quoted comma after the time field
        _line("DEMO", "09:30:00", 4.00),
    ] + ["DEMO,,0,4,1,,3.35,1,,10,3,,"]                            # no SIP time: never in a window
    path = root / SIM_MASSIVE_TRADES / DAY[:4] / DAY[5:7] / f"{DAY}.csv.gz"
    path.parent.mkdir(parents=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write(HEADER + "\n")
        fh.write(_line("AAA", "07:00:05", 1.0) + "\n")
        fh.write("\n".join(demo) + "\n")
        fh.write(_line("ZZZ", "07:00:05", 9.0) + "\n")
    return demo


@pytest.fixture
def day(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    return _write_day(tmp_path)


def _rows(frame) -> list[tuple]:
    return sorted(zip(frame["sip_timestamp"].astype("int64"), frame["price"], frame["conditions"].fillna(""),
                      strict=True))


def test_a_window_returns_the_rows_a_whole_read_filtered_to_it_returns(day):
    whole = reads.read_file(SIM_MASSIVE_TRADES, "DEMO", DAY)
    window = reads.read_file(SIM_MASSIVE_TRADES, "DEMO", DAY, "07:00", "07:02")
    expected = whole[(whole["sip_timestamp"] >= _ns("07:00:00")) & (whole["sip_timestamp"] < _ns("07:02:00"))]
    assert _rows(window) == _rows(expected)
    assert len(window) == 6 and list(window.columns) == list(whole.columns)


def test_only_the_window_lines_reach_the_csv_parser(day):
    window = reads.read_file(SIM_MASSIVE_TRADES, "DEMO", DAY, "07:00", "07:02")
    assert window.attrs["lines_read"] == len(day)
    # The six in the window, plus the line with no time to judge it by; the parsed frame drops that one, as it always
    # did. The quoted commas (in the conditions, and in a field after the time) never move the time column.
    assert window.attrs["lines_parsed"] == 7
    whole = reads.read_file(SIM_MASSIVE_TRADES, "DEMO", DAY)
    assert whole.attrs["lines_read"] == whole.attrs["lines_parsed"] == len(day)


def test_open_ended_windows(day):
    late = reads.read_file(SIM_MASSIVE_TRADES, "DEMO", DAY, "07:05")
    early = reads.read_file(SIM_MASSIVE_TRADES, "DEMO", DAY, None, "07:00")
    assert [round(p, 2) for p in late["price"]] == [3.60, 4.00]
    assert [round(p, 2) for p in early["price"]] == [3.30]


def test_windowed_ten_second_bars_equal_the_whole_days_bars_in_the_window(day):
    whole = reads.bars("DEMO", DAY, "10s")
    window = reads.bars("DEMO", DAY, "10s", "07:00", "07:02")
    inside = whole[(whole["time_et"] >= window["time_et"].min()) & (whole["time_et"] <= window["time_et"].max())]
    assert window.reset_index(drop=True).equals(inside.reset_index(drop=True))
    # 07:00:20 holds only a corrected print: volume, no price.
    assert window["open"].isna().tolist() == [False, False, True, False, False]
