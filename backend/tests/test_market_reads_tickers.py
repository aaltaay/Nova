"""Which company held a ticker on a day (``research/market_reads/tickers.py``): 84 tickers in Massive's list belong to
more than one company (AAP was Alcoa's preferred until 2016-11-01 and is Advance Auto Parts now). A past day reads the
company that held it then, a tie is broken by whose SEC filings span the day, and a read that still cannot tell
refuses with the candidates -- never today's company silently."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import tickers  # noqa: E402

ROWS = [
    {"ticker": "AAP", "cik": "0001158449", "name": "ADVANCE AUTO PARTS INC", "active": True, "type": "CS",
     "primary_exchange": "XNYS"},
    {"ticker": "AAP", "cik": "0000004281", "name": "Alcoa Inc. $3.75 Preferred Stock", "active": False,
     "delisted_utc": "2016-11-01T04:00:00Z", "type": "PFD", "primary_exchange": "XASE"},
    {"ticker": "SOLO", "cik": "0000000111", "name": "Solo Corp", "active": True, "type": "CS"},
    {"ticker": "OVLP", "cik": "0000000222", "name": "New Owner Inc", "active": True, "type": "CS"},
    {"ticker": "OVLP", "cik": "0000000333", "name": "Old Owner Inc", "active": False,
     "delisted_utc": "2016-06-01T04:00:00Z", "type": "CS"},
]


@pytest.fixture
def listing(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    ref = tmp_path / "store" / "reference"
    ref.mkdir(parents=True)
    (ref / "tickers.json").write_text(json.dumps(ROWS), encoding="utf-8")
    dates = {"222": "2015-01-01"}                       # New Owner listed before Old Owner left: the data overlaps
    monkeypatch.setattr(tickers, "_list_date", lambda symbol, cik: dates.get(cik))
    spans = {"222": ("2014-06-01", "2026-09-01"), "333": ("2001-01-01", "2016-05-20"),
             "1158449": ("2001-01-01", "2026-09-01"), "4281": ("1994-01-01", "2016-10-01")}
    monkeypatch.setattr(tickers, "_filing_span", lambda cik: spans.get(cik))
    tickers.clear()
    yield spans
    tickers.clear()


def test_a_past_day_reads_the_company_that_held_the_ticker_then(listing):
    old = tickers.resolve("aap", "2016-06-01")
    assert old["cik"] == "4281" and old["ticker_reused"] is True and "Alcoa" in old["name"]
    assert {c["cik"] for c in old["candidates"]} == {"4281", "1158449"}
    assert tickers.resolve("AAP", "2020-01-02")["cik"] == "1158449"


def test_without_a_day_it_is_todays_company_and_says_the_ticker_was_reused(listing):
    today = tickers.resolve("AAP")
    assert today["cik"] == "1158449" and today["rule"] == "today's holder"
    assert "4281" in today["warning"] and "Alcoa" in today["warning"]


def test_a_ticker_with_one_company_has_no_warning(listing):
    solo = tickers.resolve("SOLO", "2019-03-04")
    assert solo["cik"] == "111" and solo["ticker_reused"] is False and solo["warning"] is None


def test_overlapping_listings_are_settled_by_whose_filings_span_the_day(listing):
    assert tickers.resolve("OVLP", "2016-03-01")["cik"] is None           # both filed through that day
    listing["222"] = ("2016-04-01", "2026-09-01")                          # New Owner filed nothing yet
    tickers.clear()
    picked = tickers.resolve("OVLP", "2016-03-01")
    assert picked["cik"] == "333" and picked["rule"] == "SEC filings span the day"


def test_overlapping_listings_both_filing_read_the_only_common_stock_and_warn(listing, monkeypatch):
    """Massive lists Advance Auto from 2001 and Alcoa's preferred until 2016-11-01; both filed with SEC then."""
    monkeypatch.setattr(tickers, "_list_date", lambda symbol, cik: "2001-11-29" if cik == "1158449" else None)
    tickers.clear()
    answer = tickers.resolve("AAP", "2016-06-01")
    assert answer["cik"] == "1158449" and answer["rule"] == "the only common stock of overlapping listings"
    assert "4281" in answer["warning"] and "pass cik=" in answer["warning"]
    assert tickers.resolve("AAP", "2016-06-01", cik="4281")["cik"] == "4281"


def test_an_ambiguous_day_refuses_with_the_candidates(listing):
    answer = tickers.resolve("OVLP", "2016-03-01")
    assert answer["cik"] is None and "222" in answer["warning"] and "333" in answer["warning"]
    with pytest.raises(LookupError, match="pass cik="):
        tickers.require("OVLP", "2016-03-01")


def test_an_asked_cik_wins_and_an_unknown_ticker_has_none(listing):
    assert tickers.resolve("OVLP", "2016-03-01", cik="0000000222")["cik"] == "222"
    assert tickers.resolve("NOPE", "2020-01-02")["cik"] is None
    with pytest.raises(LookupError, match="no SEC CIK"):
        tickers.require("NOPE")


def test_the_window_each_company_held_the_ticker(listing):
    held = {c["cik"]: (c["held_from"], c["held_to"]) for c in tickers.resolve("AAP")["candidates"]}
    assert held == {"4281": (None, "2016-11-01"), "1158449": ("2016-11-02", None)}
