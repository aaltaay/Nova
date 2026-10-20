"""Bars carry their gaps (``reads.bars``, #1086): a bar exists only for a bucket with a trade, so a halt is a hole in the
series. ``df.attrs['gaps']`` lists the runs of missing buckets, and ``fill_gaps`` adds a row for each with no price,
no volume and ``filled`` true -- a price is never carried forward or invented."""
from __future__ import annotations

import gzip
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from constants_sim import SIM_MASSIVE_MINUTES, SIM_MASSIVE_TRADES  # noqa: E402
from market_reads import read_cache, reads  # noqa: E402

DAY = "2026-09-03"
MINUTE_HEADER = "ticker,volume,open,close,high,low,window_start,transactions"
TRADE_HEADER = ("ticker,conditions,correction,exchange,id,participant_timestamp,price,sequence_number,sip_timestamp,"
                "size,tape,trf_id,trf_timestamp")


def _minute(symbol: str, at: str, price: float, volume: int = 1000) -> str:
    return f"{symbol},{volume},{price},{price + 0.01},{price + 0.02},{price - 0.01},{reads._ns(DAY, at)},{volume // 10}"


def _trade(symbol: str, at: str, seconds: int, price: float, correction: int = 0) -> str:
    sip = reads._ns(DAY, at) + seconds * 10**9
    return f"{symbol},,{correction},4,{sip % 997},{sip - 5},{price},{sip % 9973},{sip},100,3,0,0"


def _write(root: Path, dataset: str, header: str, lines: list[str]) -> None:
    path = root / dataset / DAY[:4] / DAY[5:7] / f"{DAY}.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write(header + "\n" + "\n".join(lines) + "\n")


@pytest.fixture
def day(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(read_cache.SWITCH_ENV, "0")
    # DSS traded 09:30-09:32, then halted until 09:36 (3 minutes with no print), 09:36-09:37, 09:40 (2 more missing).
    _write(tmp_path, SIM_MASSIVE_MINUTES, MINUTE_HEADER,
           [_minute("DSS", at, 3.0 + n / 100) for n, at in enumerate(["09:30", "09:31", "09:32", "09:36", "09:37",
                                                                        "09:40"])] + [_minute("OTHER", "09:35", 1.0)])
    # Ten-second prints: 07:00:00, 07:00:10, then a pause to 07:00:40.
    _write(tmp_path, SIM_MASSIVE_TRADES, TRADE_HEADER,
           [_trade("DSS", "07:00", s, 3.0) for s in (0, 3, 10, 40)]
           + [_trade("VOID", "07:00", s, 2.0, correction=code) for s, code in ((0, 10), (20, 11))])
    return tmp_path


def test_minute_bars_say_where_the_holes_are_and_keep_their_rows(day):
    frame = reads.bars("DSS", DAY, "1m")
    assert len(frame) == 6
    assert frame.attrs["gaps"] == [{"first_et": "09:33", "last_et": "09:35", "buckets": 3},
                                   {"first_et": "09:38", "last_et": "09:39", "buckets": 2}]
    assert (frame.attrs["gap_runs"], frame.attrs["gap_buckets"], frame.attrs["gaps_truncated"]) == (2, 5, False)
    assert "no price is guessed" in frame.attrs["gap_rule"]
    assert "filled" not in frame.columns                         # rows are as they were without fill_gaps


def test_a_bucket_wide_enough_to_hold_the_halt_has_no_gap(day):
    frame = reads.bars("DSS", DAY, "5m")
    assert frame.attrs["gaps"] == [] and frame.attrs["gap_runs"] == 0 and frame.attrs["gap_buckets"] == 0


def test_the_window_asked_for_is_the_window_the_gaps_are_inside(day):
    frame = reads.bars("DSS", DAY, "1m", "09:28", "09:34")
    assert frame["time_et"].dt.strftime("%H:%M").tolist() == ["09:30", "09:31", "09:32"]
    assert frame.attrs["gaps"] == [{"first_et": "09:28", "last_et": "09:29", "buckets": 2},
                                   {"first_et": "09:33", "last_et": "09:33", "buckets": 1}]
    assert frame.attrs["gap_buckets"] == 3


def test_fill_gaps_adds_a_row_per_missing_bucket_with_no_price(day):
    plain = reads.bars("DSS", DAY, "1m")
    filled = reads.bars("DSS", DAY, "1m", fill_gaps=True)
    assert len(filled) == 11 and filled["filled"].sum() == 5
    assert filled["time_et"].dt.strftime("%H:%M").tolist() == [f"09:{m}" for m in range(30, 41)]
    rows = filled[filled["filled"]]
    assert rows[["open", "high", "low", "close"]].isna().all().all(), "a filled minute has no price"
    assert (rows["volume"] == 0).all() and (rows["transactions"] == 0).all()
    assert str(filled["time_et"].dt.tz) == "America/New_York"
    real = filled[~filled["filled"]].drop(columns="filled").reset_index(drop=True)
    pd.testing.assert_frame_equal(real, plain, check_exact=True)       # the real rows are untouched, dtypes included
    assert filled.attrs["gaps"] == plain.attrs["gaps"]


def test_a_tape_with_no_gap_fills_nothing(day):
    frame = reads.bars("DSS", DAY, "1m", "09:30", "09:33", fill_gaps=True)
    assert len(frame) == 3 and not frame["filled"].any() and frame.attrs["gap_runs"] == 0


def test_seconds_bars_name_gaps_to_the_second(day):
    frame = reads.bars("DSS", DAY, "10s")
    assert frame["time_et"].dt.strftime("%H:%M:%S").tolist() == ["07:00:00", "07:00:10", "07:00:40"]
    assert frame.attrs["gaps"] == [{"first_et": "07:00:20", "last_et": "07:00:30", "buckets": 2}]
    filled = reads.bars("DSS", DAY, "10s", fill_gaps=True)
    assert filled["filled"].tolist() == [False, False, True, True, False]
    assert filled["volume"].tolist() == [200, 100, 0, 0, 100] and filled["open"].isna().tolist() == \
        [False, False, True, True, False]


def test_a_long_list_of_gaps_keeps_the_longest_and_counts_them_all(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(read_cache.SWITCH_ENV, "0")

    def hhmm(minute_of_day: int) -> str:
        return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"

    # 60 bars two minutes apart from 04:00 (59 one-minute holes), then nothing until 09:00 (a 181-minute hole).
    bars = [hhmm(4 * 60 + n) for n in range(0, 120, 2)] + ["09:00", "09:01"]
    _write(tmp_path, SIM_MASSIVE_MINUTES, MINUTE_HEADER, [_minute("THIN", at, 2.0) for at in bars])
    meta = reads.bars("THIN", DAY, "1m").attrs
    assert (meta["gap_runs"], meta["gap_buckets"], meta["gaps_truncated"]) == (60, 59 + 181, True)
    assert len(meta["gaps"]) == reads.GAPS_LISTED
    assert {"first_et": "05:59", "last_et": "08:59", "buckets": 181} in meta["gaps"], "the long hole is kept"
    starts = [g["first_et"] for g in meta["gaps"]]
    assert starts == sorted(starts), "listed in time order"


@pytest.mark.parametrize("fill_gaps", [False, True])
def test_a_seconds_read_whose_every_print_is_a_cancel_or_error_is_an_empty_table_without_gap_meta(day, fill_gaps):
    frame = reads.bars("VOID", DAY, "10s", fill_gaps=fill_gaps)
    assert len(frame) == 0 and "gaps" not in frame.attrs and frame.attrs["tf"] == "10s"
    assert len(reads.bars("VOID", DAY, "10s", "07:00", "07:05", fill_gaps=fill_gaps)) == 0
