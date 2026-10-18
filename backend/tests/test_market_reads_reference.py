"""The front door's reference reads (``research/market_reads/reference.py``, ADR 059): Massive's statements as known
on a past day, the index rebuilt when the dump changes, and a float that never claims to be a past day's."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import reference  # noqa: E402


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def dump(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    ref = tmp_path / "store" / "reference"
    _write(ref / "balance_sheets" / "2024-02.jsonl", [
        {"tickers": ["ABC"], "cik": "0000000123", "period_end": "2023-12-31", "filing_date": "2024-02-20",
         "timeframe": "quarterly", "total_assets": 100.0},
        {"tickers": ["XYZ", "XYZW"], "cik": "0000000999", "period_end": "2023-12-31", "filing_date": "2024-02-21",
         "timeframe": "annual", "total_assets": 5.0},
    ])
    _write(ref / "balance_sheets" / "2024-05.jsonl", [
        {"tickers": ["ABC"], "cik": "0000000123", "period_end": "2024-03-31", "filing_date": "2024-05-10",
         "timeframe": "quarterly", "total_assets": 120.0},
    ])
    _write(ref / "float.jsonl", [{"ticker": "ABC", "free_float": 4_000_000, "effective_date": "2026-09-01",
                                  "free_float_percent": 40.0},
                                 {"free_float": 1, "effective_date": "2026-01-01"}])
    _write(ref / "ipos" / "2024-01.jsonl", [{"ticker": "NEWCO", "listing_date": "2024-01-15", "final_issue_price": 4}])
    return ref


def test_a_statement_counts_from_its_filing_date(dump):
    before = reference.financials("abc", as_of="2024-05-09")
    assert list(before["period_end"]) == ["2023-12-31"]          # Q1 was filed 2024-05-10: not known yet
    after = reference.financials("ABC", as_of="2024-05-10")
    assert list(after["total_assets"]) == [100.0, 120.0]
    assert after.attrs["rule"] == "a statement counts from its filing_date"


def test_every_ticker_a_statement_names_finds_it(dump):
    assert list(reference.financials("XYZW")["total_assets"]) == [5.0]


def test_a_changed_dump_rebuilds_the_index_and_an_unchanged_one_does_not(dump):
    assert reference.ensure("balance_sheets")["rebuilt"] is True
    assert reference.ensure("balance_sheets")["rebuilt"] is False
    _write(dump / "balance_sheets" / "2024-08.jsonl", [
        {"tickers": ["ABC"], "cik": "123", "period_end": "2024-06-30", "filing_date": "2024-08-09",
         "timeframe": "quarterly", "total_assets": 130.0}])
    assert reference.ensure("balance_sheets")["rebuilt"] is True
    assert list(reference.financials("ABC")["total_assets"]) == [100.0, 120.0, 130.0]


def test_the_float_is_latest_only_and_a_row_without_a_ticker_is_dropped(dump):
    frame = reference.float_latest()
    assert list(frame["ticker"]) == ["ABC"]
    assert frame.attrs["as_of"] == "latest_only"


def test_ipos_filter_by_listing_date(dump):
    assert list(reference.ipos(date_from="2024-01-01", date_to="2024-01-31")["ticker"]) == ["NEWCO"]
    assert reference.ipos(date_to="2023-12-31").empty


def test_an_index_of_another_version_refuses_loudly(dump):
    reference.ensure("balance_sheets")
    db = sqlite3.connect(reference.index_path())
    db.execute("PRAGMA user_version = 99")
    db.commit()
    db.close()
    with pytest.raises(reference.UnknownIndexVersion):
        reference.financials("ABC")


def test_a_reused_ticker_reads_the_statements_of_that_days_company(dump, monkeypatch):
    """ABC was CIK 777's ticker until 2019-12-31: a 2019 as-of reads 777's statements, today reads CIK 123's."""
    from market_reads import tickers
    (dump / "tickers.json").write_text(json.dumps([
        {"ticker": "ABC", "cik": "0000000123", "name": "ABC Now", "active": True},
        {"ticker": "ABC", "cik": "0000000777", "name": "ABC Then", "active": False,
         "delisted_utc": "2019-12-31T05:00:00Z"}]), encoding="utf-8")
    _write(dump / "balance_sheets" / "2019-03.jsonl", [
        {"tickers": ["ABC"], "cik": "0000000777", "period_end": "2018-12-31", "filing_date": "2019-03-01",
         "timeframe": "annual", "total_assets": 9.0}])
    monkeypatch.setattr(tickers, "_filing_span", lambda cik: None)
    tickers.clear()
    then = reference.financials("ABC", as_of="2019-06-01")
    assert list(then["total_assets"]) == [9.0] and then.attrs["ticker"]["cik"] == "777"
    now = reference.financials("ABC")
    assert list(now["total_assets"]) == [100.0, 120.0]
    assert "777" in now.attrs["ticker"]["warning"]
    tickers.clear()


def test_an_unknown_dataset_or_statement_is_refused(dump):
    with pytest.raises(ValueError):
        reference.ensure("nope")
    with pytest.raises(ValueError):
        reference.financials("ABC", statement="nope")
    assert os.environ["NOVA_MARKET_DATA_DIR"] in str(reference.index_path())
