"""The ORB harness reads 2026 Massive aggregates, whose volumes are fractional (#1219).

A ``'volume': 'BIGINT'`` read_csv column refused "1234.5" and stopped the build on every 2026 day.
"""
from __future__ import annotations

import gzip
import sys
from pathlib import Path

import duckdb

ORB = Path(__file__).resolve().parents[2] / "research" / "orb"
if str(ORB) not in sys.path:
    sys.path.insert(0, str(ORB))

import build_daily  # noqa: E402
import common  # noqa: E402

HEADER = "ticker,volume,open,close,high,low,window_start,transactions\n"
# 2026-10-01 10:00 ET
ROW = "AAPL,191744.629933,330.39,329.83,330.555,329.81,1759327200000000000,4874\n"


def _csv(tmp_path: Path) -> str:
    path = tmp_path / "2026-10-01.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(HEADER + ROW)
    return path.as_posix()


def test_the_minute_read_keeps_a_fractional_volume(tmp_path):
    rows = duckdb.connect().execute(common.MINUTE_SOURCE_SQL, [_csv(tmp_path)]).fetchall()
    assert rows[0][0] == "AAPL" and rows[0][5] == 191744.629933


def test_the_daily_table_takes_a_fractional_day_volume_as_whole_shares(tmp_path):
    con = duckdb.connect()
    con.execute(build_daily.SCHEMA)
    con.execute(build_daily.DAY_SQL, ["2026-10-01", _csv(tmp_path)])
    assert con.execute("SELECT volume FROM daily").fetchone()[0] == 191745     # rounded, not truncated
