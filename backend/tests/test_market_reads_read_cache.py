"""The front door's read cache returns the frame the day file gives, and lets go of it when the file changes.

``research/market_reads/read_cache.py`` keeps one stock-day of a Massive dataset as an Arrow file so the second read
skips the unzip and the CSV parse. These tests read synthetic day files three ways -- cache off, cache filling, cache
hit -- and hold the three frames identical (columns, dtypes, values, missing fields, row order, ``attrs``).
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from constants_sim import SIM_MASSIVE_MINUTES, SIM_MASSIVE_QUOTES, SIM_MASSIVE_TRADES  # noqa: E402
from market_reads import read_cache, reads  # noqa: E402
from sim import massive_files  # noqa: E402

DAY, OTHER_DAY = "2026-06-02", "2026-06-03"
OPEN = reads._ns(DAY, "09:30")       # SIP nanoseconds; both days share the clock, a window reads DAY's
TRADES_HEADER = ("ticker,conditions,correction,exchange,id,participant_timestamp,price,sequence_number,"
                 "sip_timestamp,size,tape,trf_id,trf_timestamp")
QUOTES_HEADER = ("ticker,ask_exchange,ask_price,ask_size,bid_exchange,bid_price,bid_size,conditions,indicators,"
                 "participant_timestamp,sequence_number,sip_timestamp,tape,trf_timestamp")
MINUTES_HEADER = "ticker,volume,open,close,high,low,window_start,transactions"


def _trades(symbol: str, n: int, base: float, shift: int = 0) -> list[str]:
    conditions = ["", '"12,37"', "14", '"17,9,41"', "16", '"14,41"']
    out = []
    for i in range(n):
        ns = OPEN + (i - n // 3) * 7_000_000_000 + shift      # a third of the prints before 09:30
        correction = "" if i % 11 == 5 else ("1" if i % 13 == 7 else ("8" if i % 17 == 3 else "0"))
        trf = "" if i % 4 else "201"
        out.append(f"{symbol},{conditions[i % len(conditions)]},{correction},{4 + i % 3},{1000 + i},{ns - 900},"
                   f"{base + (i % 9) * 0.01:.4f},{5000 + i},{ns},{100 + i % 5 * 50},3,{trf},{ns - 400 if trf else 0}")
    return out


def _quotes(symbol: str, n: int, base: float) -> list[str]:
    out = []
    for i in range(n):
        ns = OPEN + (i - n // 2) * 3_000_000_000
        bid = "0" if i % 10 == 9 else f"{base + (i % 4) * 0.01:.4f}"           # Massive writes an empty side as 0
        indicators = "" if i % 3 else "604"
        out.append(f"{symbol},11,{base + 0.05:.4f},{200 + i},12,{bid},{100 + i},1,{indicators},{ns - 50},{900 + i},"
                   f"{ns},3,0")
    return out


def _minutes(symbol: str, n: int, base: float) -> list[str]:
    return [f"{symbol},{1000.5 + i},{base},{base + 0.02},{base + 0.03},{base - 0.01},{OPEN + (i - 5) * 60 * 10**9},"
            f"{10 + i}" for i in range(n)]


def _write(root: Path, dataset: str, day: str, header: str, rows: list[str]) -> Path:
    path = root / dataset / day[:4] / day[5:7] / f"{day}.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write(header + "\n" + "".join(row + "\n" for row in sorted(rows, key=lambda r: r.split(",")[0])))
    return path


@pytest.fixture
def market(tmp_path, monkeypatch):
    root = tmp_path / "massive"
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(root))
    monkeypatch.setenv(read_cache.DIR_ENV, str(tmp_path / "cache"))
    monkeypatch.setenv(read_cache.SWITCH_ENV, "1")
    monkeypatch.setattr(read_cache, "RESERVE_GB", 0.0)
    for day in (DAY, OTHER_DAY):
        _write(root, SIM_MASSIVE_TRADES, day, TRADES_HEADER,
               _trades("AAA", 120, 1.5) + _trades("NA", 40, 3.0) + _trades("CON", 25, 7.0) + _trades("ZZZ", 9, 9.0))
        _write(root, SIM_MASSIVE_QUOTES, day, QUOTES_HEADER, _quotes("AAA", 90, 1.5) + _quotes("NA", 30, 3.0))
        _write(root, SIM_MASSIVE_MINUTES, day, MINUTES_HEADER, _minutes("AAA", 30, 1.5) + _minutes("NA", 12, 3.0))
    return root, tmp_path / "cache"


def _read(kind: str, symbol: str, day: str, start=None, end=None) -> pd.DataFrame:
    if kind == "trades":
        return reads.trades(symbol, day, start, end)
    if kind == "quotes":
        return reads.quotes(symbol, day, start, end)
    return reads.read_file(SIM_MASSIVE_MINUTES, symbol, day, start, end)


def _same(a: pd.DataFrame, b: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert list(a.columns) == list(b.columns) and list(a.dtypes) == list(b.dtypes)
    assert type(a.index) is type(b.index) and a.index.equals(b.index)
    assert a.isna().equals(b.isna())
    for column in a.columns:                       # NaN stays NaN, never None
        assert [type(v) for v in a[column]] == [type(v) for v in b[column]], column
    assert {k: v for k, v in a.attrs.items() if k != "seconds"} == {k: v for k, v in b.attrs.items() if k != "seconds"}


def _three_ways(monkeypatch, *args) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    monkeypatch.setenv(read_cache.SWITCH_ENV, "0")
    cold = _read(*args)
    monkeypatch.setenv(read_cache.SWITCH_ENV, "1")
    return cold, _read(*args), _read(*args)


CASES = [(kind, symbol, day) for kind in ("trades", "quotes", "minutes") for symbol in ("AAA", "NA")
         for day in (DAY, OTHER_DAY)] + [("trades", "CON", DAY), ("trades", "ZZZ", OTHER_DAY)]


@pytest.mark.parametrize("kind,symbol,day", CASES)
def test_a_cached_read_is_the_frame_the_day_file_gives(market, monkeypatch, kind, symbol, day):
    cold, filled, hit = _three_ways(monkeypatch, kind, symbol, day)

    assert len(cold) > 0
    _same(cold, filled)
    _same(cold, hit)
    assert read_cache.entry(market[1], {"trades": SIM_MASSIVE_TRADES, "quotes": SIM_MASSIVE_QUOTES,
                                        "minutes": SIM_MASSIVE_MINUTES}[kind], symbol, day).is_file()


@pytest.mark.parametrize("kind", ["trades", "quotes", "minutes"])
def test_a_window_out_of_the_cache_is_the_window_out_of_the_file(market, monkeypatch, kind):
    _read(kind, "AAA", DAY)                                  # fills the whole day
    for start, end in (("09:30", "09:45"), (None, "09:30"), ("09:31", None)):
        cold, filled, hit = _three_ways(monkeypatch, kind, "AAA", DAY, start, end)
        _same(cold, hit)
        _same(cold, filled)


def test_an_empty_read_is_cached_and_stays_empty(market, monkeypatch):
    cold, filled, hit = _three_ways(monkeypatch, "quotes", "QQQQ", DAY)

    assert len(cold) == 0          # a file read without its index names no columns for a ticker it does not hold
    _same(cold, filled)
    _same(cold, hit)
    assert read_cache.entry(market[1], SIM_MASSIVE_QUOTES, "QQQQ", DAY).is_file()


def test_a_missing_day_is_still_a_lookup_error(market):
    with pytest.raises(LookupError):
        reads.trades("AAA", "2026-06-06")
    assert not (market[1] / SIM_MASSIVE_TRADES / "2026-06-06").exists()


def test_a_redownloaded_day_is_read_again(market, monkeypatch):
    root, _ = market
    first = reads.trades("AAA", DAY)
    path = _write(root, SIM_MASSIVE_TRADES, DAY, TRADES_HEADER, _trades("AAA", 60, 2.5, shift=1))
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 10**9))

    again = reads.trades("AAA", DAY)
    monkeypatch.setenv(read_cache.SWITCH_ENV, "0")
    _same(again, reads.trades("AAA", DAY))
    assert len(first) == 120 and len(again) == 60


def test_the_switch_turns_the_cache_off(market, monkeypatch):
    monkeypatch.setenv(read_cache.SWITCH_ENV, "off")
    reads.quotes("AAA", DAY)
    assert read_cache.root() is None
    assert not market[1].exists()


def test_with_no_folder_named_the_cache_is_off_off_windows(monkeypatch):
    monkeypatch.delenv(read_cache.DIR_ENV, raising=False)
    monkeypatch.delenv(read_cache.SWITCH_ENV, raising=False)
    monkeypatch.setattr(read_cache.os, "name", "posix")
    assert read_cache.root() is None


def _meta(path: Path) -> dict:
    with pa.OSFile(str(path), "rb") as handle:
        return json.loads(pa.ipc.open_file(handle).schema.metadata[read_cache.META_KEY])


def test_another_reader_or_schema_version_is_a_miss_that_is_written_again(market, monkeypatch):
    reads.trades("AAA", DAY)
    entry = read_cache.entry(market[1], SIM_MASSIVE_TRADES, "AAA", DAY)
    source = massive_files.day_file(SIM_MASSIVE_TRADES, DAY)

    assert read_cache.load(SIM_MASSIVE_TRADES, "AAA", DAY, source, "another reader") is None
    monkeypatch.setattr(read_cache, "SCHEMA_VERSION", read_cache.SCHEMA_VERSION + 1)
    assert read_cache.load(SIM_MASSIVE_TRADES, "AAA", DAY, source, reads._reader()) is None
    reads.trades("AAA", DAY)
    assert _meta(entry)["schema_version"] == read_cache.SCHEMA_VERSION


def test_a_damaged_entry_is_read_again_from_the_day_file(market, monkeypatch):
    reads.quotes("NA", DAY)
    entry = read_cache.entry(market[1], SIM_MASSIVE_QUOTES, "NA", DAY)
    entry.write_bytes(b"not an arrow file")

    cold, filled, hit = _three_ways(monkeypatch, "quotes", "NA", DAY)
    _same(cold, filled)
    _same(cold, hit)
    assert _meta(entry)["rows"] == 30


def test_entry_names_are_safe_for_any_ticker(tmp_path):
    assert read_cache.entry(tmp_path, "trades_v1", "con", DAY).name == "t_CON.arrow"
    assert read_cache.entry(tmp_path, "trades_v1", "BRK.A", DAY).name == "t_BRK.A.arrow"
    assert read_cache.entry(tmp_path, "trades_v1", "A/B:C", DAY).name == "t_A%2FB%3AC.arrow"


def test_the_prune_drops_the_oldest_used_entries_past_the_cap(market):
    for symbol, day in (("AAA", DAY), ("NA", DAY), ("AAA", OTHER_DAY), ("NA", OTHER_DAY)):
        reads.trades(symbol, day)
    found = sorted(read_cache.entries(market[1]))
    for n, (_, _, path) in enumerate(found):            # oldest first in the order they were written
        os.utime(path, ns=(10**18 + n * 10**9, 10**18 + n * 10**9))
    reads.trades(found[0][2].stem[2:], found[0][2].parent.name)     # a hit marks the oldest as used
    cap = sum(size for _, size, _ in found) - 1

    answer = read_cache.prune(market[1], cap)

    left = {path for _, _, path in read_cache.entries(market[1])}
    assert answer["removed"] >= 1 and answer["bytes"] <= cap * read_cache.PRUNE_TO
    assert found[0][2] in left
    assert found[1][2] not in left


def test_the_vectorized_sets_price_is_the_per_row_rule():
    conditions = pd.Series(["", "12,37", "14", "17,9,41", None, "16", "14,41", "37", "12", "x,15", "2,7"] * 7,
                           dtype="str")
    correction = pd.Series([0, 1, 8, None, 7, 10, 11, 12, 0, 2, 0] * 7, dtype="float64")
    per_row = [massive_files.sets_price(c if isinstance(c, str) else "", int(k))
               for c, k in zip(conditions, correction.fillna(0), strict=True)]

    answer = reads.sets_price(conditions, correction)

    assert answer.dtype == bool and answer.tolist() == per_row
    assert reads.sets_price(conditions, correction.fillna(0).astype(np.int64)).tolist() == per_row


def test_a_hit_does_not_open_the_day_file(market, monkeypatch):
    cold = reads.quotes("AAA", DAY)

    def no_parse(*_args):
        raise AssertionError("the day file was read again")

    monkeypatch.setattr(reads, "_parse_day", no_parse)
    _same(cold, reads.quotes("AAA", DAY))
