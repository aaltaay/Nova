"""Cross-stock scans of Massive's reference dump (``research/market_reads/reference_scans.py``, ADR 059): every stock's
FINRA short interest at ONE settlement -- named, or the newest published by a day under the per-stock read's publish
lag -- and every listed company by SIC code or description, the dump's latest. Temp files only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import reference, reference_scans, tickers  # noqa: E402


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _si(day: str, ticker: str, shares: int, dtc: float) -> dict:
    return {"settlement_date": day, "ticker": ticker, "short_interest": shares, "avg_daily_volume": 1000,
            "days_to_cover": dtc}


@pytest.fixture
def dump(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    ref = tmp_path / "store" / "reference"
    ref.mkdir(parents=True)
    (ref / "tickers.json").write_text(json.dumps([
        {"ticker": "BIGS", "cik": "0000000001", "name": "Big Short Co", "active": True, "type": "CS"},
        {"ticker": "TINY", "cik": "0000000002", "name": "Tiny Co", "active": True, "type": "CS"},
        {"ticker": "ETFX", "name": "An ETF Massive lists without a CIK", "active": True, "type": "ETF"},
        {"ticker": "ABRpD", "cik": "0000000003", "name": "Arbor Preferred D", "active": True, "type": "PFD"},
        {"ticker": "REUS", "cik": "0000000004", "name": "Reus Old", "active": False, "type": "CS",
         "delisted_utc": "2026-09-10T04:00:00Z"},
        {"ticker": "REUS", "cik": "0000000005", "name": "Reus New", "active": True, "type": "CS"},
    ]), encoding="utf-8")
    _write(ref / "short_interest" / "2026-08.jsonl", [
        _si("2026-08-14", "BIGS", 9_000_000, 4.0), _si("2026-08-31", "BIGS", 9_500_000, 4.2),
        _si("2026-08-31", "REUS", 2_000_000, 6.0)])
    _write(ref / "short_interest" / "2026-09.jsonl", [
        _si("2026-09-15", "BIGS", 10_000_000, 3.0), _si("2026-09-15", "TINY", 50_000, 12.0),
        _si("2026-09-15", "ETFX", 7_000_000, 1.0), _si("2026-09-15", "ABRpD", 80_000, 999.99),
        _si("2026-09-15", "OTCQF", 6_000_000, 999.99), _si("2026-09-15", "REUS", 3_000_000, 8.0),
        _si("2026-09-30", "BIGS", 12_000_000, 5.0)])
    _write(ref / "ticker_details.jsonl", [
        {"ticker": "PHRM", "name": "Pharma Inc", "cik": "0000000010", "sic_code": "2834",
         "sic_description": "PHARMACEUTICAL PREPARATIONS", "primary_exchange": "XNAS", "type": "CS", "active": True,
         "list_date": "2020-01-02"},
        {"ticker": "PHRMw", "name": "Pharma Inc Warrant", "cik": "0000000010", "sic_code": "2834",
         "sic_description": "PHARMACEUTICAL PREPARATIONS", "primary_exchange": "XNAS", "type": "WARRANT",
         "active": True},
        {"ticker": "BIOL", "name": "Biologics Corp", "cik": "0000000011", "sic_code": "2836",
         "sic_description": "BIOLOGICAL PRODUCTS, (NO DIAGNOSTIC SUBSTANCES)", "primary_exchange": "XNYS",
         "type": "CS", "active": True, "list_date": "2015-05-05"},
        {"ticker": "CHIP", "name": "Chip Co", "cik": "0000000012", "sic_code": "3674",
         "sic_description": "SEMICONDUCTORS & RELATED DEVICES", "primary_exchange": "XNAS", "type": "CS",
         "active": True},
        {"ticker": "GONE", "_missing": True},
    ])
    tickers.clear()
    reference._DETAILS = None
    monkeypatch.setattr(tickers, "_filing_span", lambda cik: None)
    yield ref
    tickers.clear()
    reference._DETAILS = None


def test_one_named_settlement_with_a_floor_common_stock_by_default(dump):
    frame = reference_scans.short_interest_scan(settlement="2026-09-15", min_shares=1_000_000)
    assert list(frame["ticker"]) == ["BIGS", "REUS"]                 # largest first; ETF and OTC name left out
    assert set(frame["settlement_date"]) == {"2026-09-15"} and set(frame["counts_from"]) == {"2026-09-25"}
    assert frame.attrs["left_out"] == {"other_kind": 1, "unknown_kind": 1}
    every = reference_scans.short_interest_scan(settlement="2026-09-15", kinds=["all"], sort="ticker")
    assert list(every["ticker"]) == ["ABRpD", "BIGS", "ETFX", "OTCQF", "REUS", "TINY"]   # as FINRA writes them
    kinds = dict(zip(every["ticker"], every["type"], strict=True))
    assert kinds["ETFX"] == "ETF" and kinds["ABRpD"] == "PFD" and pd.isna(kinds["OTCQF"])
    assert every.set_index("ticker").loc["OTCQF", "ticker_warning"] == "not in the ticker list"


def test_days_to_cover_floor_and_sort(dump):
    frame = reference_scans.short_interest_scan(settlement="2026-09-15", min_days_to_cover=5, sort="days_to_cover")
    assert list(frame["ticker"]) == ["TINY", "REUS"]


def test_by_day_reads_the_newest_settlement_published_then_and_names_the_pending_one(dump):
    frame = reference_scans.short_interest_scan(day="2026-10-02", at="09:30")
    assert frame.attrs["settlement_date"] == "2026-09-15"           # Sep 30 counts only from Oct 12
    assert frame.attrs["picked"]["pending"] == {"settlement_date": "2026-09-30", "counts_from": "2026-10-12"}
    earlier = reference_scans.short_interest_scan(day="2026-09-20")
    assert earlier.attrs["settlement_date"] == "2026-08-31"          # Sep 15 counts only from Sep 25
    assert list(earlier["short_interest"]) == [9_500_000, 2_000_000]


def test_a_reused_ticker_names_its_holder_on_the_settlement_day(dump):
    august = reference_scans.short_interest_scan(settlement="2026-08-31").set_index("ticker")
    september = reference_scans.short_interest_scan(settlement="2026-09-15").set_index("ticker")
    assert (august.loc["REUS", "cik"], august.loc["REUS", "company"]) == ("4", "Reus Old")
    assert (september.loc["REUS", "cik"], september.loc["REUS", "company"]) == ("5", "Reus New")
    assert "also used by" not in str(september.loc["BIGS", "ticker_warning"])


def test_a_settlement_not_on_file_or_a_double_ask_is_refused(dump):
    with pytest.raises(LookupError, match="2026-09-15"):
        reference_scans.short_interest_scan(settlement="2026-09-14")
    with pytest.raises(ValueError):
        reference_scans.short_interest_scan()
    with pytest.raises(ValueError):
        reference_scans.short_interest_scan(settlement="2026-09-15", day="2026-10-02")
    with pytest.raises(ValueError):
        reference_scans.short_interest_scan(settlement="2026-09-15", sort="float")
    with pytest.raises(ValueError):
        reference_scans.kinds_set(["all", "CS"])


def test_sectors_by_code_prefix_and_words_are_the_dumps_latest(dump):
    assert list(reference_scans.sector_scan(sic=["2834"])["ticker"]) == ["PHRM"]          # common stock by default
    assert list(reference_scans.sector_scan(sic=["2834"], kinds=["all"])["ticker"]) == ["PHRM", "PHRMw"]
    drugs = reference_scans.sector_scan(sic="283*")
    assert list(drugs["ticker"]) == ["PHRM", "BIOL"] and list(drugs["sic"]) == ["2834", "2836"]
    assert list(reference_scans.sector_scan(sic_words=["pharmaceutical"])["ticker"]) == ["PHRM"]
    either = reference_scans.sector_scan(sic=["3674"], sic_words=["biolog"])
    assert list(either["ticker"]) == ["BIOL", "CHIP"]                 # codes OR words
    row = reference_scans.sector_scan(sic=["283*"], exchange=["xnas"]).iloc[0]
    assert (row["ticker"], row["cik"], row["list_date"], row["exchange"]) == ("PHRM", "10", "2020-01-02", "XNAS")
    assert reference_scans.sector_scan(sic=["283*"], active=False).empty
    frame = reference_scans.sector_scan(sic=["2834"])
    assert frame.attrs["as_of"] == "latest_only" and "not as of a past day" in frame.attrs["note"]
    with pytest.raises(ValueError):
        reference_scans.sector_scan()
