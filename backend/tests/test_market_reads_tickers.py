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
    {"ticker": "CDW", "cik": "0000000555", "name": "CDW Corp", "active": True, "type": "CS"},
    {"ticker": "CDw", "cik": "0000000444", "name": "Old Co Warrants", "active": False,
     "delisted_utc": "2019-01-02T05:00:00Z", "type": "WARRANT"},
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


def test_holder_runs_give_resolves_answer_for_every_day(listing):
    """The movers store's ``ticker_holders`` is written from these runs: a day in a run reads that run's company,
    a day resolve cannot settle is in none, and a ticker one company used has none at all."""
    runs = tickers.holder_runs("OVLP")

    def held(day):
        return [r["cik"] for r in runs if (r["held_from"] is None or r["held_from"] <= day)
                and (r["held_to"] is None or day <= r["held_to"])]
    for day in ("2014-01-01", "2015-06-01", "2016-03-01", "2016-06-01", "2016-06-02", "2026-09-02", "2030-01-01"):
        assert held(day) == ([c] if (c := tickers.resolve("OVLP", day)["cik"]) else []), day
    assert held("2016-03-01") == [] and held("2016-06-02") == ["222"]       # both filed that day: no holder
    assert tickers.holder_runs("AAP") == [{"cik": "4281", "held_from": None, "held_to": "2016-11-01"},
                                          {"cik": "1158449", "held_from": "2016-11-02", "held_to": None}]
    assert tickers.holder_runs("SOLO") == [] and tickers.holder_runs("NOPE") == []


def test_a_lowercase_letter_is_another_security_never_the_same_ticker(listing):
    """Massive writes a preferred or warrant with a lowercase letter (AAp, CDw). Folding case made 84 common stocks
    read another security's company on past days (CDW before 2019 read the warrants' issuer)."""
    for asked in ("CDW", "cdw", " CDW "):
        answer = tickers.resolve(asked, "2017-05-01")
        assert answer["cik"] == "555" and answer["ticker_reused"] is False and answer["symbol"] == "CDW", asked
    assert tickers.resolve("CDw", "2017-05-01")["cik"] == "444"
    assert tickers.holder_runs("CDW") == [] and tickers.key("cdw") == "CDW" and tickers.key("CDw") == "CDw"
