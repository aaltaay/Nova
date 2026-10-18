"""The front door's bulk movers scan (``research/market_reads/scan.py``, ADR 059): percents in points both ways (the
store keeps fractions: a 10 filter once matched only +1000% days), no row cap, only known filters and columns."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from day_movers import schema  # noqa: E402
from market_reads import roots, scan  # noqa: E402


@pytest.fixture
def movers(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    path = roots.movers_db()
    path.parent.mkdir(parents=True)
    db = sqlite3.connect(path)
    schema.initialize(db)
    rows = [("2025-01-02", "AAA", "CS", 3.0, 0.12), ("2025-01-02", "BBB", "CS", 25.0, 0.80),
            ("2025-01-03", "CCC", "ADRC", 4.0, 0.55), ("2025-01-03", "DDD", "CS", 5.0, 12.0)]
    db.executemany("INSERT INTO movers (session_date, symbol, kind, prev_close, high_pct) VALUES (?, ?, ?, ?, ?)", rows)
    db.commit()
    db.close()


def test_filters_and_answers_are_percent_points(movers):
    frame = scan.movers_scan(date_from="2025-01-01", price_min=2, price_max=20, high_min=10)
    assert list(frame["symbol"]) == ["AAA", "CCC", "DDD"]
    assert list(frame["high_pct"]) == pytest.approx([12.0, 55.0, 1200.0])
    assert list(scan.movers_scan(date_to="2025-12-31", high_min=1000)["symbol"]) == ["DDD"]


def test_kinds_dates_and_columns_narrow_the_scan(movers):
    frame = scan.movers_scan(kinds=["ADRC"], columns=["session_date", "symbol"], date_from="2025-01-03")
    assert frame.to_dict("records") == [{"session_date": "2025-01-03", "symbol": "CCC"}]


def test_an_unknown_filter_or_column_is_refused(movers):
    with pytest.raises(ValueError, match="unknown filter"):
        scan.movers_scan(float_max=10)
    with pytest.raises(ValueError, match="unknown column"):
        scan.movers_scan(date_from="2025-01-01", columns=["symbol; DROP TABLE movers"])


def test_a_missing_store_says_where_it_looked(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path / "none"))
    with pytest.raises(LookupError, match="no day movers index"):
        scan.movers_scan(date_from="2025-01-01")


@pytest.fixture
def split_days(tmp_path, monkeypatch):
    """Three +400% days: a likely reverse split (volume no bigger than the day before), a suspect that traded
    several times the prior volume (a real jump, #772) and an ordinary runner."""
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    path = roots.movers_db()
    path.parent.mkdir(parents=True)
    db = sqlite3.connect(path)
    schema.initialize(db)
    rows = [("2025-02-03", "SPLT", "CS", 4.0, 4.0, 1, 0, 1_000_000, 900_000),
            ("2025-02-03", "JUMP", "CS", 4.0, 4.0, 1, 0, 100_000, 5_000_000),
            ("2025-02-03", "RUNR", "CS", 4.0, 4.0, 0, 0, 100_000, 5_000_000),
            ("2025-02-04", "EDGE", "CS", 4.0, 1.2 - 1.0, 0, 0, 100_000, 1_000_000)]
    db.executemany("INSERT INTO movers (session_date, symbol, kind, prev_close, high_pct, split_suspect, split_listed,"
                   " prev_volume, volume) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    db.commit()
    db.close()


def test_likely_splits_are_left_out_by_default_like_the_capped_search(split_days):
    frame = scan.movers_scan(date_from="2025-02-03", high_min=300)
    assert list(frame["symbol"]) == ["JUMP", "RUNR"]
    assert frame.attrs["filters"]["splits"] == "exclude_likely"
    assert dict(zip(frame["symbol"], frame["split"], strict=True)) == {"JUMP": None, "RUNR": None}
    every = scan.movers_scan(date_from="2025-02-03", high_min=300, splits="include")
    assert dict(zip(every["symbol"], every["split"], strict=True)) == {"JUMP": None, "RUNR": None,
                                                                      "SPLT": "likely_split"}
    assert list(scan.movers_scan(date_from="2025-02-03", splits="only_suspects")["symbol"]) == ["JUMP", "SPLT"]
    with pytest.raises(ValueError, match="splits must be one of"):
        scan.movers_scan(date_from="2025-02-03", splits="none")


def test_a_stock_exactly_on_a_percent_line_is_on_it(split_days):
    # $1.20 over $1.00 is stored as 0.19999999999999996: the capped search counts it at high_min=20
    assert list(scan.movers_scan(date_from="2025-02-04", high_min=20)["symbol"]) == ["EDGE"]


def test_a_broad_scan_needs_a_symbol_a_date_range_or_a_limit(split_days):
    with pytest.raises(ValueError, match="date_from / date_to, a symbol or a limit"):
        scan.movers_scan(high_min=300)
    assert len(scan.movers_scan(high_min=300, limit=1)) == 1
    assert list(scan.movers_scan(symbol="RUNR")["symbol"]) == ["RUNR"]


def test_the_default_row_cap_says_so_and_a_limit_has_a_ceiling(split_days, monkeypatch):
    monkeypatch.setattr(scan, "ROW_CAP", 2)
    frame = scan.movers_scan(date_from="2025-02-03", splits="include")
    assert len(frame) == 2 and frame.attrs["capped"] is True and "limit=" in frame.attrs["note"]
    assert scan.movers_scan(date_from="2025-02-04").attrs["capped"] is False
    with pytest.raises(ValueError, match="limit must be 1-"):
        scan.movers_scan(date_from="2025-02-03", limit=scan.LIMIT_MAX + 1)
