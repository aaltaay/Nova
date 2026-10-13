"""The tickers NA and NULL are tickers, not missing values, in the research reads of Massive files (2026-10-12).

pandas reads "NA", "NULL", "N/A" and the like as NaN by default. The leaderboard spot check dropped the real ticker
NA, so the correct 2026-07-15 rebuild failed it: "NA: stored but not on the independent board" and every later rank
off by one. The builder's DuckDB reads never had the problem; these tests hold the pandas readers to the same rule.
"""
from __future__ import annotations

import gzip
import sys
from pathlib import Path

from tests.test_leaderboard_reconstruct_helpers import build, session, ts, write_closes, write_minutes

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

import spot_check  # noqa: E402  (research/leaderboard on sys.path via the helpers)
from constants_sim import SIM_MASSIVE_TRADES  # noqa: E402
from market_reads import reads  # noqa: E402

TICKERS = {"AAA": "CS", "NA": "CS", "NULL": "CS"}


def _days(root: Path):
    prev, day = session(0), session(1)
    write_closes(root, prev, {"AAA": 1.0, "NA": 2.0, "NULL": 4.0})
    write_minutes(root, prev, [("AAA", 9, 30, 1.0, 100)])
    write_minutes(root, day, [("AAA", 9, 30, 1.1, 100), ("NA", 9, 30, 3.0, 500), ("NULL", 9, 31, 5.0, 400)])
    return prev, day


def test_the_spot_check_loaders_keep_the_tickers_na_and_null(tmp_path):
    prev, day = _days(tmp_path)
    minutes = spot_check.load_minutes(spot_check.day_file(tmp_path, "minute_aggs_v1", day), set(TICKERS))
    closes = spot_check.prior_closes(spot_check.day_file(tmp_path, "day_aggs_v1", prev), [], prev, day)

    assert sorted(minutes["ticker"]) == ["AAA", "NA", "NULL"]
    assert closes.to_dict() == {"AAA": 1.0, "NA": 2.0, "NULL": 4.0}


def test_a_rebuilt_board_holding_na_passes_the_spot_check(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    prev, day = _days(root)
    build(root, day, TICKERS, db=db)
    minutes = spot_check.load_minutes(spot_check.day_file(root, "minute_aggs_v1", day), set(TICKERS))
    closes = spot_check.prior_closes(spot_check.day_file(root, "day_aggs_v1", prev), [], prev, day)

    stored = spot_check.stored_rows(db, day, ts(day, 10, 0))
    board = spot_check.independent_board(minutes, closes, ts(day, 4, 0), ts(day, 10, 0))
    counts, problems = spot_check.compare(stored, board)

    assert [r["symbol"] for r in stored] == ["NA", "NULL", "AAA"]     # +50%, +25%, +10%
    assert problems == []
    assert counts["rank"] == counts["stored"] == 3


def test_a_market_read_of_the_ticker_na_keeps_its_ticker(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    path = tmp_path / SIM_MASSIVE_TRADES / "2026" / "06" / "2026-06-02.csv.gz"
    path.parent.mkdir(parents=True)
    sip = ts(session(1), 9, 30) * 1_000_000_000
    with gzip.open(path, "wt", newline="") as fh:
        fh.write("ticker,conditions,price,sip_timestamp,size\n")
        fh.write(f"AAA,,1.0,{sip},100\nNA,,3.0,{sip},200\nNA,\"12,37\",3.1,{sip + 1},50\nNULL,,5.0,{sip},10\n")

    frame = reads.read_file(SIM_MASSIVE_TRADES, "NA", "2026-06-02")

    assert list(frame["ticker"]) == ["NA", "NA"]
    assert list(frame["price"]) == [3.0, 3.1]
    assert frame["conditions"].isna().tolist() == [True, False]        # an empty field is still missing
