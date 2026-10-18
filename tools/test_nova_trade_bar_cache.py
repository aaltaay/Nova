"""The trade-chart bar cache: hits only on an unchanged day file and reader; generated bars, no Massive files."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nova_trade_bar_cache as cache  # noqa: E402
import nova_trade_charts as trades  # noqa: E402

DAY = "2023-05-02"
NAN = float("nan")


def frame(rows):
    times = pd.to_datetime([f"{DAY} {t}" for t, *_ in rows]).tz_localize("America/New_York")
    return pd.DataFrame({"time_et": times, "open": [r[1] for r in rows], "high": [r[2] for r in rows],
                         "low": [r[3] for r in rows], "close": [r[4] for r in rows], "volume": [r[5] for r in rows],
                         "transactions": [1] * len(rows)})


DAY_FRAME = frame([("07:00:00", 3.3, 3.4, 3.3, 3.35, 100), ("07:00:10", NAN, NAN, NAN, NAN, 40),
                   ("07:05:20", 3.35, 3.4, 3.35, 3.39, 900), ("07:10:20", 3.9, 4.1, 3.9, 4.1, 500)])


def day_file(tmp_path: Path) -> Path:
    path = tmp_path / "massive" / "trades_v1" / DAY[:4] / DAY[5:7] / f"{DAY}.csv.gz"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fixture")
    return path


def counting_read(calls: list):
    def read():
        calls.append(1)
        return DAY_FRAME
    return read


def test_a_second_read_of_the_stock_day_is_a_hit_with_the_same_rows(tmp_path):
    source, calls = day_file(tmp_path), []
    first, state = cache.day_rows(tmp_path / "cache", source, "DEMO", DAY, 10, counting_read(calls))
    assert state == "miss" and len(calls) == 1
    second, state = cache.day_rows(tmp_path / "cache", source, "DEMO", DAY, 10, counting_read(calls))
    assert state == "hit" and len(calls) == 1 and second == first
    assert first[1] == [25210, None, None, None, None, 40.0], "a volume-only bucket keeps no prices"


def test_a_changed_day_file_reader_or_schema_is_a_miss(tmp_path, monkeypatch):
    source, calls, root = day_file(tmp_path), [], tmp_path / "cache"
    cache.day_rows(root, source, "DEMO", DAY, 10, counting_read(calls))
    info = source.stat()
    os.utime(source, ns=(info.st_atime_ns, info.st_mtime_ns + 10**9))
    assert cache.day_rows(root, source, "DEMO", DAY, 10, counting_read(calls))[1] == "miss"
    monkeypatch.setattr(cache, "reader_sha256", lambda repo=cache.REPO: "another reader")
    assert cache.day_rows(root, source, "DEMO", DAY, 10, counting_read(calls))[1] == "miss"
    entry = root / DAY / "DEMO_10s.json"
    stored = json.loads(entry.read_text(encoding="utf-8"))
    entry.write_text(json.dumps(dict(stored, schema_version=99)), encoding="utf-8")
    assert cache.day_rows(root, source, "DEMO", DAY, 10, counting_read(calls))[1] == "miss"
    assert cache.day_rows(root, source, "DEMO", DAY, 5, counting_read(calls))[1] == "miss", "another bar size"
    assert len(calls) == 5


def test_a_day_file_that_changes_during_the_read_is_not_cached(tmp_path):
    source, root = day_file(tmp_path), tmp_path / "cache"

    def read_while_the_file_grows():
        source.write_bytes(b"fixture and more")
        return DAY_FRAME

    assert cache.day_rows(root, source, "DEMO", DAY, 10, read_while_the_file_grows)[1] == "miss"
    assert not (root / DAY / "DEMO_10s.json").exists()


def test_the_trade_bundle_reads_the_front_door_once_then_hits(tmp_path, monkeypatch):
    source = day_file(tmp_path)
    massive = source.parents[3]
    calls = []

    def front_door(root):
        def bars(symbol, day, tf, start=None, end=None):
            calls.append((symbol, day, tf, start, end))
            return DAY_FRAME
        return bars

    monkeypatch.setattr(trades, "_front_door_read", front_door)
    trade = {"symbol": "DEMO", "date": DAY, "entry_time": "07:05:22", "entry_price": 3.39,
             "exit_time": "07:10:20", "exit_price": 4.10}
    first = trades.resolve_trade_bundle([trade], tmp_path / "one", massive, cache_root=tmp_path / "cache")
    second = trades.resolve_trade_bundle([dict(trade, exit_price=4.0)], tmp_path / "two", massive,
                                         cache_root=tmp_path / "cache")
    assert calls == [("DEMO", DAY, "10s", None, None)], "the whole session once; the second chart reads nothing"
    assert [s["cache"] for s in (first["sources"][0], second["sources"][0])] == ["miss", "hit"]
    bars = [json.loads((tmp_path / name / "bars" / "01.json").read_text(encoding="utf-8"))["bars"]
            for name in ("one", "two")]
    assert bars[0] == bars[1] and [b["s"] for b in bars[0]] == [25520, 25820], "the window opens at 07:00:20"
    assert first["sources"][0]["volume_only_buckets_left_as_gaps"] == 0
