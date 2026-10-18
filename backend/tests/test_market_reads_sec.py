"""The front door's SEC reads (``research/market_reads/sec.py``, ADR 059): share counts and filings as filed by a past
day, the cover page before the balance sheet, a split putting an old count on the day's basis."""
from __future__ import annotations

import json
import sys
import types
import zipfile
from datetime import date
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

import market_reads  # noqa: E402
from market_reads import sec, tickers  # noqa: E402

CIK = "885462"


def _fact(end, filed, val, form="10-Q"):
    return {"end": end, "filed": filed, "val": val, "form": form}


@pytest.fixture
def edgar(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path / "massive"))
    monkeypatch.setenv("NOVA_CATALYST_DIR", str(tmp_path / "catalysts"))
    ref = tmp_path / "massive" / "store" / "reference"
    ref.mkdir(parents=True)
    (ref / "tickers.json").write_text(json.dumps([{"ticker": "GURE", "cik": f"000{CIK}"}]), encoding="utf-8")
    folder = tmp_path / "catalysts" / "edgar"
    folder.mkdir(parents=True)
    facts = {"entityName": "GULF RESOURCES", "facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            _fact("2025-05-10", "2025-05-12", 1_000_000), _fact("2025-08-10", "2025-08-14", 1_100_000)]}},
            "EntityPublicFloat": {"units": {"USD": [_fact("2024-06-30", "2025-04-11", 8_000_000, "10-K")]}}},
        "us-gaap": {"CommonStockSharesIssued": {"units": {"shares": [_fact("2025-06-30", "2025-08-14", 1_200_000)]}},
                    "TreasuryStockCommonShares": {"units": {"shares": [_fact("2025-06-30", "2025-08-14", 28_583)]}}}}}
    subs = {"name": "GULF RESOURCES", "filings": {"recent": {
        "form": ["10-K", "4", "SC 13D", "10-Q"], "filingDate": ["2025-04-11", "2025-06-01", "2025-07-01", "2025-08-14"],
        "reportDate": ["2024-12-31", "", "", "2025-06-30"], "accessionNumber": ["a1", "a2", "a3", "a4"],
        "items": ["", "", "", ""]}, "files": [{"name": f"CIK{CIK.zfill(10)}-submissions-001.json"}]}}
    older = {"form": ["20-F"], "filingDate": ["2010-03-01"], "reportDate": [""], "accessionNumber": ["a0"],
             "items": [""]}
    with zipfile.ZipFile(folder / "companyfacts.zip", "w") as z:
        z.writestr(f"CIK{CIK.zfill(10)}.json", json.dumps(facts))
    with zipfile.ZipFile(folder / "submissions.zip", "w") as z:
        z.writestr(f"CIK{CIK.zfill(10)}.json", json.dumps(subs))
        z.writestr(f"CIK{CIK.zfill(10)}-submissions-001.json", json.dumps(older))
    sec._zip.cache_clear()
    tickers.clear()
    monkeypatch.setattr(sec, "_share_factor", lambda symbol, after, through, cik=None: 1.0)
    yield
    sec._zip.cache_clear()
    tickers.clear()


def test_a_count_filed_after_the_day_is_not_known_yet(edgar):
    known = sec.shares_as_of("gure", "2025-08-13")
    assert known["outstanding"]["value"] == 1_000_000            # the 1.1M count was filed 2025-08-14
    assert known["outstanding"]["filed"] == "2025-05-12"
    assert known["issued"] is None and known["treasury"] is None
    later = sec.shares_as_of("GURE", "2025-09-01")
    assert later["outstanding"]["value"] == 1_100_000
    assert later["issued"]["value"] - later["treasury"]["value"] == 1_171_417
    assert later["public_float_usd"]["value"] == 8_000_000


def test_max_age_drops_a_stale_outstanding_count(edgar):
    assert sec.shares_as_of("GURE", "2026-03-01", max_age_days=120)["outstanding"] is None


def test_filings_filter_by_form_and_date_and_read_the_older_file(edgar):
    assert list(sec.filings("GURE", as_of="2025-07-01", forms=["4", "sc 13d"])["form"]) == ["4", "SC 13D"]
    assert list(sec.filings("GURE")["form"])[0] == "20-F"


def test_the_newest_annual_report_names_the_filer(edgar):
    assert sec.filer_kind("GURE", "2011-01-01") == "foreign"
    assert sec.filer_kind("GURE", "2025-05-01") == "domestic"
    assert sec.filer_kind("NOPE", "2025-05-01") == "unknown"


def test_a_symbol_without_a_cik_says_so(edgar):
    with pytest.raises(LookupError, match="no SEC CIK"):
        sec.facts("NOPE")


def test_a_reused_ticker_reads_the_company_that_held_it_that_day(edgar, tmp_path):
    """GURE's ticker was another company's (CIK 42) until 2020: a 2019 day reads CIK 42, never today's GURE."""
    ref = tmp_path / "massive" / "store" / "reference"
    (ref / "tickers.json").write_text(json.dumps([
        {"ticker": "GURE", "cik": f"000{CIK}", "name": "GULF RESOURCES", "active": True},
        {"ticker": "GURE", "cik": "0000000042", "name": "Old Gure Co", "active": False,
         "delisted_utc": "2020-01-10T05:00:00Z"}]), encoding="utf-8")
    tickers.clear()
    assert sec.cik_for("GURE", "2019-05-01") == "42"
    with pytest.raises(LookupError, match="CIK 42 has no submissions"):
        sec.filings("GURE", as_of="2019-05-01")           # never falls back to today's company
    today = sec.shares_as_of("GURE", "2025-09-01")
    assert today["cik"] == CIK and today["ticker"]["ticker_reused"] is True
    assert {c["cik"] for c in today["ticker"]["candidates"]} == {CIK, "42"}
    assert sec.filings("GURE", as_of="2019-05-01", cik=CIK).attrs["cik"] == CIK   # an asked CIK wins


def test_a_reverse_split_puts_an_old_count_on_the_days_basis(monkeypatch):
    rows = pd.DataFrame({"execution_date": [date(2025, 7, 1)], "price_factor": [10.0]})   # 1-for-10
    monkeypatch.setattr(market_reads, "splits", types.SimpleNamespace(table=lambda symbol, day=None, cik=None: rows), raising=False)
    monkeypatch.setitem(sys.modules, "market_reads.splits", market_reads.splits)
    assert sec._share_factor("GURE", "2025-05-10", "2025-08-01") == pytest.approx(0.1)
    assert sec._share_factor("GURE", "2025-07-02", "2025-08-01") == 1.0
