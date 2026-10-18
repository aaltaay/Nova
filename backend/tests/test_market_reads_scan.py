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
    frame = scan.movers_scan(price_min=2, price_max=20, high_min=10)
    assert list(frame["symbol"]) == ["AAA", "CCC", "DDD"]
    assert list(frame["high_pct"]) == pytest.approx([12.0, 55.0, 1200.0])
    assert list(scan.movers_scan(high_min=1000)["symbol"]) == ["DDD"]


def test_kinds_dates_and_columns_narrow_the_scan(movers):
    frame = scan.movers_scan(kinds=["ADRC"], columns=["session_date", "symbol"], date_from="2025-01-03")
    assert frame.to_dict("records") == [{"session_date": "2025-01-03", "symbol": "CCC"}]


def test_an_unknown_filter_or_column_is_refused(movers):
    with pytest.raises(ValueError, match="unknown filter"):
        scan.movers_scan(float_max=10)
    with pytest.raises(ValueError, match="unknown column"):
        scan.movers_scan(columns=["symbol; DROP TABLE movers"])


def test_a_missing_store_says_where_it_looked(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path / "none"))
    with pytest.raises(LookupError, match="no day movers index"):
        scan.movers_scan()
