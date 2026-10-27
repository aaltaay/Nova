"""Who filed a form, across companies (``research/market_reads/sec_scan.py``, ADR 059): a synthetic ``submissions.zip``
(temp files only -- never F:) read company by company -- forms matched exactly, the span bounded, older pages read
only when they overlap it, each acceptance time on its filer's own clock, and each row's ticker the one its company
held on the filing day."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import reference, sec, sec_scan, tickers  # noqa: E402

CLOCK = sec_scan._clock()


def _block(rows: list[tuple[str, str, str, str]]) -> dict:
    """A submissions column block from ``(accession, form, filing date, raw acceptance)`` rows."""
    return {"accessionNumber": [r[0] for r in rows], "form": [r[1] for r in rows], "filingDate": [r[2] for r in rows],
            "acceptanceDateTime": [r[3] for r in rows], "reportDate": [""] * len(rows),
            "items": ["2.02" if r[1] == "8-K" else "" for r in rows]}


def _doc(cik: str, name: str, sic: str, recent: list, files: list | None = None) -> dict:
    return {"cik": cik, "entityType": "operating", "sic": sic, "sicDescription": "x", "name": name,
            "filings": {"recent": _block(recent), "files": files or []}}


LISTING = [
    {"ticker": "ACME", "cik": "0000000111", "name": "Acme Corp", "active": True, "type": "CS"},
    {"ticker": "ACMEw", "cik": "0000000111", "name": "Acme Corp Warrants", "active": True, "type": "WARRANT"},
    {"ticker": "EAST", "cik": "0000000222", "name": "Eastern Clock Inc", "active": True, "type": "CS"},
    {"ticker": "OLD", "cik": "0000000333", "name": "Old Holder", "active": False, "type": "CS",
     "delisted_utc": "2019-12-31T05:00:00Z"},
    {"ticker": "OLD", "cik": "0000000444", "name": "New Holder", "active": True, "type": "CS"},
    {"ticker": "PAGE", "cik": "0000000555", "name": "Paged Bank", "active": True, "type": "CS"},
]


@pytest.fixture
def zip_on_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path / "massive"))
    monkeypatch.setenv("NOVA_CATALYST_DIR", str(tmp_path / "catalysts"))
    ref = tmp_path / "massive" / "store" / "reference"
    ref.mkdir(parents=True)
    (ref / "tickers.json").write_text(json.dumps(LISTING), encoding="utf-8")
    (ref / "ticker_details.jsonl").write_text("".join(json.dumps({"ticker": t, "cik": "0000000111",
                                                                  "list_date": "2021-03-01"}) + "\n"
                                                      for t in ("ACME", "ACMEw")), encoding="utf-8")
    docs = {
        # UTC filer: 15:05Z is 11:05 ET (no evidence of its own); its 23:10Z neighbour says the JSON is UTC.
        "111": _doc("0000000111", "ACME CORP", "2834", [
            ("a-3", "424B5", "2026-09-10", "2026-09-10T15:05:00.000Z"),
            ("a-2", "8-K", "2026-09-08", "2026-09-08T23:10:00.000Z"),
            ("a-1", "S-1/A", "2021-02-01", "2021-02-01T20:00:00.000Z"),
            ("a-0", "S-1", "2021-01-15", "2021-01-15T20:00:00.000Z")]),
        # Eastern filer: 16:05 behind the Z is 16:05 ET; its 07:30 neighbour (before 06:00 ET read as UTC) says so.
        "222": _doc("0000000222", "EASTERN CLOCK INC", "3674", [
            ("e-2", "424B5", "2026-09-09", "2026-09-09T16:05:00.000Z"),
            ("e-1", "8-K", "2026-09-10", "2026-09-10T07:30:00.000Z")]),
        "333": _doc("0000000333", "OLD HOLDER", "6022", [("o-1", "8-K", "2019-06-03", "2019-06-03T21:00:00.000Z")]),
        "444": _doc("0000000444", "NEW HOLDER", "6022", [("n-1", "8-K", "2019-06-04", "2019-06-04T21:00:00.000Z")]),
        "555": _doc("0000000555", "PAGED BANK", "6021", [("p-9", "424B2", "2026-09-10", "2026-09-10T21:00:00.000Z")],
                    files=[{"name": "CIK0000000555-submissions-001.json", "filingFrom": "2018-01-02",
                            "filingTo": "2019-12-30"},
                           {"name": "CIK0000000555-submissions-002.json", "filingFrom": "2010-01-04",
                            "filingTo": "2012-12-28"}]),
        "999": _doc("0000000999", "UNLISTED TRUST", "6189", [("u-1", "424B5", "2026-09-10", "2026-09-10T21:00:00Z")]),
    }
    folder = tmp_path / "catalysts" / "edgar"
    folder.mkdir(parents=True)
    with zipfile.ZipFile(folder / "submissions.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for cik, doc in docs.items():
            z.writestr(f"CIK{cik.zfill(10)}.json", json.dumps(doc))
        z.writestr("CIK0000000555-submissions-001.json", json.dumps(_block([
            ("p-2", "424B5", "2019-03-05", "2019-03-05T21:15:00.000Z"),
            ("p-1", "8-K", "2019-03-04", "2019-03-04T23:30:00.000Z")])))
        z.writestr("CIK0000000555-submissions-002.json", json.dumps(_block([
            ("p-0", "424B5", "2011-05-05", "2011-05-05T21:15:00.000Z")])))
    sec._zip.cache_clear()
    tickers.clear()
    reference._DETAILS = None
    monkeypatch.setattr(tickers, "_filing_span", lambda cik: None)
    yield
    sec._zip.cache_clear()
    tickers.clear()
    reference._DETAILS = None


def test_a_form_filed_in_the_span_by_a_listed_company_is_found_with_its_et_acceptance(zip_on_disk):
    frame = sec_scan.filings_scan(["424b5"], "2026-09-08", "2026-09-14")
    assert list(frame["accession"]) == ["e-2", "a-3"] and list(frame["cik"]) == ["222", "111"]
    accepted = {r.cik: r.accepted_et.strftime("%H:%M %z") for r in frame.itertuples()}
    assert accepted == {"222": "16:05 -0400", "111": "11:05 -0400"}     # each JSON read on its own clock
    assert set(frame["accepted_clock"]) == {"near_180d"}
    acme = frame[frame["cik"] == "111"].iloc[0]
    assert (acme["ticker"], acme["tickers"], acme["company"], acme["sic"]) == ("ACME", "ACME,ACMEw", "ACME CORP", "2834")
    assert "999" not in set(frame["cik"])                                # never held a ticker Massive lists
    assert frame.attrs["scanned"]["companies"] == 5 and frame.attrs["max_span_days"] == sec_scan.MAX_SPAN_DAYS


def test_forms_match_exactly_and_a_filing_before_the_listing_has_no_ticker(zip_on_disk):
    s1 = sec_scan.filings_scan(["S-1"], "2021-01-01", "2021-01-31")
    assert list(s1["accession"]) == ["a-0"]                               # S-1/A is another form
    assert pd.isna(s1.iloc[0]["ticker"]) and s1.iloc[0]["tickers"] == "ACME,ACMEw"   # listed 2021-03-01
    both = sec_scan.filings_scan(["S-1", "S-1/A"], "2021-01-10", "2021-02-09")
    assert list(both["form"]) == ["S-1", "S-1/A"]


def test_an_older_page_is_read_only_when_it_overlaps_the_span(zip_on_disk):
    frame = sec_scan.filings_scan(["424B5"], "2019-03-01", "2019-03-29")
    assert list(frame["accession"]) == ["p-2"] and frame.iloc[0]["ticker"] == "PAGE"
    assert frame.attrs["scanned"]["pages_read"] == 1                      # the 2010-2012 page is never opened
    assert frame.iloc[0]["accepted_et"].strftime("%Y-%m-%d %H:%M") == "2019-03-05 16:15"   # 21:15Z, EST


def test_a_reused_ticker_names_its_holder_on_the_filing_day_only(zip_on_disk):
    frame = sec_scan.filings_scan(["8-K"], "2019-06-01", "2019-06-30")
    by_cik = {r.cik: r.ticker for r in frame.itertuples()}
    assert by_cik["333"] == "OLD"                     # the former holder until 2019-12-31
    assert pd.isna(by_cik["444"])                     # today's holder did not hold OLD in 2019
    assert set(frame["tickers"]) == {"OLD"}           # each row is its own company, never merged


def test_tickers_ciks_and_sic_narrow_the_read(zip_on_disk):
    one = sec_scan.filings_scan(["424B5", "8-K"], "2026-09-01", "2026-09-30", ticker_list=["acme"])
    assert set(one["cik"]) == {"111"} and one.attrs["scanned"]["companies"] == 1
    trust = sec_scan.filings_scan(["424B5"], "2026-09-01", "2026-09-30", ciks=["0000000999"])
    assert list(trust["company"]) == ["UNLISTED TRUST"] and pd.isna(trust.iloc[0]["ticker"])
    pharma = sec_scan.filings_scan(["424B5"], "2026-09-01", "2026-09-30", sic=["283*"])
    assert set(pharma["cik"]) == {"111"} and pharma.attrs["scanned"]["other_sic"] == 4
    with pytest.raises(LookupError):
        sec_scan.filings_scan(["8-K"], "2026-09-01", "2026-09-30", ticker_list=["NOPE"])


def test_a_wide_or_empty_ask_is_refused(zip_on_disk):
    with pytest.raises(ValueError, match="at most 31 days"):
        sec_scan.filings_scan(["8-K"], "2026-08-01", "2026-09-01")
    with pytest.raises(ValueError):
        sec_scan.filings_scan(["8-K"], "2026-09-02", "2026-09-01")
    with pytest.raises(ValueError, match="forms is required"):
        sec_scan.filings_scan([], "2026-09-01", "2026-09-02")
    with pytest.raises(ValueError):
        sec_scan.sic_codes(["28345"])
    empty = sec_scan.filings_scan(["10-K"], "2026-09-01", "2026-09-30")
    assert empty.empty and list(empty.columns) == sec_scan.COLUMNS


def test_sic_codes_and_prefixes():
    assert sec_scan.sic_codes(["2834", 100, "283*"]) == ["2834", "0100", "283*"]
    assert sec_scan.sic_matches("100", ["0100"]) and sec_scan.sic_matches("2836", ["283*"])
    assert not sec_scan.sic_matches("2840", ["283*"]) and not sec_scan.sic_matches("", ["283*"])


def test_placing_some_rows_answers_what_placing_every_row_does():
    """``edgar_clock.placed`` builds only what a pick needs; its answer must equal ``clocks`` over the whole JSON --
    own times, neighbours, a part with no evidence falling to the filer's other parts, and no evidence anywhere."""
    eastern = [("8-K", "2026-09-10T07:30:00.000Z", "2026-09-10"), ("8-K", "2026-09-09T16:05:00.000Z", "2026-09-09")]
    silent = [("8-K", "2024-01-09T15:00:00.000Z", "2024-01-09"), ("8-K", "2023-05-09T14:00:00.000Z", "2023-05-09")]
    utc = [("8-K", "2026-09-08T23:10:00.000Z", "2026-09-08"), ("4", "2026-09-07T12:00:00.000Z", "2026-09-07"),
           ("8-K", "short", None)]
    for parts in ([eastern, silent], [utc, silent, eastern], [silent], [utc]):
        whole = CLOCK.clocks(parts)
        for k, rows in enumerate(parts):
            for i in range(len(rows)):
                rest = [p for j, p in enumerate(parts) if j != k]
                picked = CLOCK.placed([parts[k]], [(0, i)], lambda rest=rest: rest)
                assert picked == [whole[k][i]], (k, i)
    assert CLOCK.placed([silent], [(0, 0)], lambda: [eastern]) == [("et", "filer")]
    assert CLOCK.placed([silent], [(0, 0)]) == [("utc", "default")]
