"""Symbol search through the front door (``research/market_reads/symbols.py``): a ticker or name finds its listing
rows with the exact ticker first, a reused ticker says so, and one ticker's answer names every company that used it,
which held it on a day, and each company's other tickers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import symbols, tickers  # noqa: E402

ROWS = [
    {"ticker": "AAP", "cik": "0001158449", "name": "ADVANCE AUTO PARTS INC", "active": True, "type": "CS",
     "primary_exchange": "XNYS", "composite_figi": "BBG000F7RCJ1", "last_updated_utc": "2026-10-01T00:00:00Z"},
    {"ticker": "AAP", "cik": "0000004281", "name": "Alcoa Inc. $3.75 Preferred Stock", "active": False,
     "delisted_utc": "2016-11-01T04:00:00Z", "type": "PFD", "primary_exchange": "XASE",
     "last_updated_utc": "2016-11-01T00:00:00Z"},
    {"ticker": "AAPL", "cik": "0000320193", "name": "Apple Inc.", "active": True, "type": "CS",
     "primary_exchange": "XNAS", "last_updated_utc": "2026-10-02T00:00:00Z"},
    {"ticker": "AURA", "cik": "0000000111", "name": "Aurora Holdings", "active": True, "type": "CS",
     "primary_exchange": "XNAS"},
    {"ticker": "AURAW", "cik": "0000000111", "name": "Aurora Holdings Warrant", "active": True, "type": "WARRANT",
     "primary_exchange": "XNAS"},
    {"ticker": "OLDA", "cik": "0000000111", "name": "Old Aurora Name Inc", "active": False,
     "delisted_utc": "2020-03-02T05:00:00Z", "type": "CS", "primary_exchange": "XNAS"},
    {"ticker": "XAAP", "cik": "0000000999", "name": "Unrelated", "active": True, "type": "ETF",
     "primary_exchange": "ARCX"},
]


@pytest.fixture
def listing(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    ref = tmp_path / "store" / "reference"
    ref.mkdir(parents=True)
    (ref / "tickers.json").write_text(json.dumps(ROWS), encoding="utf-8")
    monkeypatch.setattr(tickers, "_list_date", lambda symbol, cik: None)
    monkeypatch.setattr(tickers, "_filing_span", lambda cik: None)
    tickers.clear()
    yield
    tickers.clear()


def test_the_exact_ticker_ranks_first_then_prefixes(listing):
    frame = symbols.search("aap")
    assert list(frame["ticker"]) == ["AAP", "AAP", "AAPL"]
    assert list(frame["active"])[:2] == [True, False]                      # today's holder before the former
    assert frame["ticker_reused"].tolist() == [True, True, False]
    assert frame.iloc[1]["delisted"] == "2016-11-01" and frame.attrs["as_of"] == "2026-10-02T00:00:00Z"


def test_a_name_matches_anywhere_in_any_case(listing):
    frame = symbols.search("aurora")
    assert set(frame["ticker"]) == {"AURA", "AURAW", "OLDA"}
    assert list(symbols.search("aurora", types=["CS"], active=True)["ticker"]) == ["AURA"]


def test_filters_narrow_by_ticker_exchange_and_cik(listing):
    assert list(symbols.search(ticker="aapl")["name"]) == ["Apple Inc."]
    assert set(symbols.search(cik="111")["ticker"]) == {"AURA", "AURAW", "OLDA"}
    assert list(symbols.search(exchange="arcx")["ticker"]) == ["XAAP"]
    assert len(symbols.search("a", limit=2)) == 2 and symbols.search("a", limit=2).attrs["matched"] > 2
    with pytest.raises(ValueError, match="needs a query"):
        symbols.search()


def test_one_ticker_names_every_company_and_who_held_it_on_a_day(listing):
    answer = symbols.symbol("aap", "2016-06-01")
    assert answer["ticker_reused"] is True and answer["listed"] is True
    assert {c["cik"]: (c["held_from"], c["held_to"]) for c in answer["companies"]} == {
        "4281": (None, "2016-11-01"), "1158449": ("2016-11-02", None)}
    assert answer["on_day"]["cik"] == "4281" and answer["on_day"]["rule"] == "held the ticker that day"
    today = symbols.symbol("AAP")
    assert today["on_day"]["cik"] == "1158449" and "Alcoa" in today["warning"]


def test_a_companys_other_tickers_are_its_cik_history(listing):
    answer = symbols.symbol("AURA")
    assert answer["ticker_reused"] is False and answer["warning"] is None
    assert [r["ticker"] for r in answer["cik_history"]["111"]] == ["AURA", "AURAW", "OLDA"]
    assert answer["cik_history"]["111"][-1]["delisted"] == "2020-03-02"


def test_an_unknown_ticker_says_it_is_not_listed(listing):
    answer = symbols.symbol("NOPE")
    assert answer["listed"] is False and answer["companies"] == [] and "not in Massive's" in answer["notes"][-1]
