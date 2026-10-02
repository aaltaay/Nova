"""Dilution on file (ADR 036, the float group): SEC EDGAR's submissions file read into four kinds of
filing, worded as the read's row, and fetched in the background by a reader the stock read only asks."""
from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from constants_catalysts import CATALYST_FEED_SEC_TICKERS_URL, CATALYST_FEED_SEC_USER_AGENT_DEFAULT
from constants_stock_read import STOCK_READ_DILUTION_KEEP_PER_KIND, STOCK_READ_DILUTION_MAX_PAGES
from stock_read import dilution, dilution_reader, dilution_store, history, read, rows

ET = ZoneInfo("America/New_York")
TODAY = date(2026, 10, 1)
SUBMISSIONS = "https://data.sec.gov/submissions/CIK0001234567.json"
PAGE = "CIK0001234567-submissions-001.json"


def at(hh: int, mm: int, day: date = TODAY) -> float:
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=ET).timestamp()


def ago(days: int) -> str:
    return (TODAY - timedelta(days=days)).isoformat()


def block(filings) -> dict:
    """A columnar filings block as EDGAR writes it, newest first: ``(form, date[, items])`` rows."""
    listed = sorted(filings, key=lambda f: f[1], reverse=True)
    return {"accessionNumber": [f"0001234567-26-{i:06d}" for i in range(len(listed))],
            "form": [f[0] for f in listed], "filingDate": [f[1] for f in listed],
            "items": [f[2] if len(f) > 2 else "" for f in listed]}


def submissions(filings, files=(), name="Test Co") -> dict:
    return {"cik": "1234567", "name": name, "tickers": ["TEST"],
            "filings": {"recent": block(filings), "files": list(files)}}


def page(to: str, name: str = PAGE, frm: str = "2010-01-04") -> dict:
    return {"name": name, "filingCount": 2000, "filingFrom": frm, "filingTo": to}


ROUTINE = [("10-Q", "2026-08-14"), ("8-K", "2026-08-05", "2.02,9.01"), ("4", "2026-07-20"), ("10-K", "2026-03-30")]
ON_FILE = [("S-3", "2025-03-14"), ("424B5", "2026-08-11"), ("424B3", "2026-06-02"), ("S-1/A", "2026-07-02"),
           ("8-K", "2026-09-12", "1.01,3.02,9.01")]


def flags_of(filings, files=(), pages=None, today=TODAY) -> dict:
    found = dilution.digest(submissions(filings, files), pages or {}, today)
    return dilution.flags(found["filings"], found["unread_to"], today)


# -- the four kinds, from a submissions file ------------------------------------------------------
def test_a_submissions_file_reads_into_the_four_kinds():
    got = flags_of(ROUTINE + ON_FILE + [("8-K/A", "2026-09-20", "3.02"), ("S-8", "2026-09-01")])
    assert got["shelf"] == {"state": "on_file", "form": "S-3", "date": "2025-03-14", "count": 1}
    assert got["prospectus"] == {"state": "on_file", "form": "424B5", "date": "2026-08-11", "count": 2}
    assert got["s1"] == {"state": "on_file", "form": "S-1/A", "date": "2026-07-02", "count": 1}
    assert got["placement"] == {"state": "on_file", "form": "8-K", "date": "2026-09-12", "count": 1}


def test_routine_filings_are_none_on_file():
    assert flags_of(ROUTINE) == {kind: {"state": "none"} for kind in dilution.KINDS}
    assert flags_of([]) == {kind: {"state": "none"} for kind in dilution.KINDS}


@pytest.mark.parametrize("form,items,kind", [
    ("S-3", "", "shelf"), ("S-3/A", "", "shelf"), ("S-3ASR", "", "shelf"),
    ("F-3", "", "shelf"), ("F-3/A", "", "shelf"), ("F-3ASR", "", "shelf"), ("s-3", "", "shelf"),
    ("424B1", "", "prospectus"), ("424B2", "", "prospectus"), ("424B5", "", "prospectus"), ("424B8", "", "prospectus"),
    ("S-1", "", "s1"), ("S-1/A", "", "s1"), ("F-1", "", "s1"), ("F-1/A", "", "s1"),
    ("8-K", "3.02", "placement"), ("8-K", "1.01,3.02,9.01", "placement"), ("8-K", "1.01, 3.02", "placement"),
    # not one of the four
    ("S-3MEF", "", None), ("S-3D", "", None), ("S-8", "", None), ("S-4", "", None), ("S-1MEF", "", None),
    ("F-10", "", None), ("S-11", "", None), ("424A", "", None), ("FWP", "", None), ("10-Q", "", None),
    ("8-K", "2.02,9.01", None), ("8-K", "", None), ("8-K", "3.01", None), ("8-K", "13.02", None),
    ("8-K/A", "3.02", None), ("6-K", "3.02", None),
])
def test_a_filing_is_one_of_the_four_kinds_by_its_form_and_items(form, items, kind):
    assert dilution.kind_of(form, items) == kind


@pytest.mark.parametrize("form,items,kind,days", [
    ("S-3", "", "shelf", 3 * 365), ("424B5", "", "prospectus", 180), ("F-1/A", "", "s1", 180),
    ("8-K", "3.02", "placement", 180),
])
def test_a_window_holds_its_last_day_and_not_the_one_before(form, items, kind, days):
    assert flags_of([(form, ago(days), items)])[kind]["state"] == "on_file"
    assert flags_of([(form, ago(days + 1), items)])[kind]["state"] == "none"
    assert flags_of([(form, TODAY.isoformat(), items)])[kind]["state"] == "on_file"


def test_the_newest_filing_of_a_kind_is_named_and_the_window_is_counted():
    got = flags_of([("S-3", "2024-02-01"), ("S-3/A", "2024-03-15"), ("S-3", ago(3 * 365 + 30))])
    assert got["shelf"] == {"state": "on_file", "form": "S-3/A", "date": "2024-03-15", "count": 2}


def test_a_kept_read_is_judged_again_as_its_filings_age_out():
    kept = dilution.digest(submissions([("424B5", ago(179))]), {}, TODAY)
    assert dilution.flags(kept["filings"], kept["unread_to"], TODAY)["prospectus"]["state"] == "on_file"
    assert dilution.flags(kept["filings"], kept["unread_to"], TODAY + timedelta(days=2))["prospectus"] == {"state": "none"}


def test_a_long_list_is_cut_per_kind_and_says_so():
    notes = [("424B2", ago(i % 170)) for i in range(STOCK_READ_DILUTION_KEEP_PER_KIND + 15)]
    kept = dilution.digest(submissions(notes + [("S-3ASR", "2024-11-08")]), {}, TODAY)
    assert kept["more"] == ["prospectus"] and kept["name"] == "Test Co"
    assert len([f for f in kept["filings"] if f["kind"] == "prospectus"]) == STOCK_READ_DILUTION_KEEP_PER_KIND
    assert [f for f in kept["filings"] if f["kind"] == "shelf"] == [{"kind": "shelf", "form": "S-3ASR", "date": "2024-11-08"}]


# -- a list EDGAR pages is never read as clean ------------------------------------------------------
def test_an_unread_page_inside_a_window_leaves_that_kind_unknown():
    files = [page("2025-09-20")]                                  # ``recent`` reaches back one year only
    got = flags_of(ROUTINE, files)
    assert got["shelf"] == {"state": "unknown", "unread_to": "2025-09-20"}
    assert got["prospectus"] == got["s1"] == got["placement"] == {"state": "none"}      # their 180 days were read
    assert flags_of(ROUTINE + [("S-3", "2026-01-09")], files)["shelf"]["state"] == "on_file"   # found: known


def test_the_page_that_reaches_into_the_window_is_wanted_and_answers():
    files = [page("2025-09-20"), page("2019-06-28", "CIK0001234567-submissions-002.json")]
    file = submissions(ROUTINE, files)
    assert dilution.pages_wanted(file, TODAY) == [PAGE]            # the 2019 page is older than every window
    older = block([("S-3", "2024-05-06"), ("424B5", "2024-05-20"), ("10-K", "2024-03-29")])
    found = dilution.digest(file, {PAGE: older}, TODAY)
    assert found["unread_to"] == "2019-06-28"
    got = dilution.flags(found["filings"], found["unread_to"], TODAY)
    assert got["shelf"] == {"state": "on_file", "form": "S-3", "date": "2024-05-06", "count": 1}
    assert got["prospectus"] == {"state": "none"}                  # the 2024 prospectus is outside 180 days
    clean = dilution.digest(file, {PAGE: block([("10-K", "2024-03-29")])}, TODAY)
    assert dilution.flags(clean["filings"], clean["unread_to"], TODAY)["shelf"] == {"state": "none"}


def test_pages_are_not_read_when_too_many_are_needed_or_none_can_change_the_answer():
    many = [page(ago(400 + 30 * i), f"CIK0001234567-submissions-{i + 1:03d}.json")
            for i in range(STOCK_READ_DILUTION_MAX_PAGES + 1)]
    assert dilution.pages_wanted(submissions(ROUTINE, many), TODAY) == []
    assert flags_of(ROUTINE, many)["shelf"]["state"] == "unknown"                       # stated, never clean
    assert dilution.pages_wanted(submissions(ROUTINE, many[:1]), TODAY) == [many[0]["name"]]
    # A shelf already on file: the page is older than the 180 days the other kinds look back.
    assert dilution.pages_wanted(submissions(ROUTINE + [("S-3", "2026-01-09")], many[:1]), TODAY) == []
    assert dilution.pages_wanted(submissions(ON_FILE, many[:1]), TODAY) == []            # every kind already on file
    assert dilution.pages_wanted(submissions(ROUTINE, [page("2015-07-22")]), TODAY) == []  # older than every window
    assert dilution.pages_wanted(submissions(ROUTINE, [page("2025-09-20", "../evil.json")]), TODAY) == []
    undated = {"name": PAGE, "filingCount": 2000}
    assert dilution.pages_wanted(submissions(ROUTINE, [undated]), TODAY) == [PAGE]       # may reach into any window
    assert flags_of(ROUTINE, [undated])["prospectus"]["state"] == "unknown"


def test_a_file_that_is_not_a_submissions_file_is_refused():
    with pytest.raises(ValueError, match="no filings.recent"):
        dilution.digest({"error": "not found"}, {}, TODAY)
    with pytest.raises(ValueError, match="no form / filingDate"):
        dilution.digest({"filings": {"recent": {"form": ["S-3", "10-K"], "filingDate": ["2026-01-09"]}}}, {}, TODAY)
    with pytest.raises(ValueError, match="without a filing date"):
        dilution.digest(submissions([("S-3", "")]), {}, TODAY)
    assert flags_of([("10-K", "")])["shelf"] == {"state": "none"}   # a filing of no kind needs no date


# -- the row ----------------------------------------------------------------------------------------
NOW = at(9, 0)


def kept(filings, files=(), **over) -> dict:
    """The reader's answer for a symbol whose EDGAR read is kept."""
    return {"status": "read", "symbol": "TEST", "cik": 1234567, "fetched_at": at(7, 2), "stale": False,
            "error": None, "retry_at": None, **dilution.digest(submissions(filings, files), {}, TODAY), **over}


def test_filings_on_file_read_warn_with_their_forms_and_months():
    r = dilution.row(kept(ROUTINE + [("S-3", "2025-03-14"), ("424B5", "2026-08-11"), ("424B3", "2026-06-02")]), NOW)
    assert r == {
        "id": "dilution_on_file", "label": "Dilution on file", "value": "S-3 shelf 2025-03, 424B5 2026-08",
        "state": "warn", "source": "sec_edgar", "as_of": at(7, 2),
        "detail": "Shelf registration: S-3 filed 2025-03-14. Prospectus: 424B5 filed 2026-08-11 (2 in the last "
                  "180 days). EDGAR read Oct 1 07:02 ET for Test Co (CIK 1234567).",
    }
    every = dilution.row(kept(ON_FILE), NOW)
    assert every["value"] == "S-3 shelf 2025-03, 424B5 2026-08, S-1/A 2026-07, 8-K 3.02 2026-09"
    assert "Registration statement: S-1/A filed 2026-07-02." in every["detail"]
    assert "Unregistered sale of equity: 8-K Item 3.02 filed 2026-09-12." in every["detail"]


def test_a_known_registrant_with_none_on_file_reads_ok():
    r = dilution.row(kept(ROUTINE), NOW)
    assert (r["state"], r["value"], r["source"], r["as_of"]) == ("ok", "None on file", "sec_edgar", at(7, 2))
    assert r["detail"] == ("No S-3 / F-3 shelf in 3 years, no 424B prospectus in 180 days, no S-1 / F-1 in 180 days, "
                           "no 8-K Item 3.02 in 180 days. EDGAR read Oct 1 07:02 ET for Test Co (CIK 1234567).")


@pytest.mark.parametrize("view,value,said", [
    ({"status": "reading", "symbol": "TEST"}, "Not read yet", "Reading EDGAR…"),
    ({"status": "no_cik", "symbol": "ZZZZ", "fetched_at": at(8, 30), "listed_at": at(7, 2), "stale": False},
     "Not known", "SEC's ticker list has no registrant for ZZZZ (list read Oct 1 07:02 ET), so its filings cannot"),
    ({"status": "error", "symbol": "TEST", "error": "URLError: <urlopen error timed out>", "retry_at": at(9, 5)},
     "Not known", "EDGAR could not be read: URLError: <urlopen error timed out>. Nova asks again after Oct 1 09:05 ET."),
    ({"status": "off", "symbol": "TEST"}, "Not read", "The EDGAR reader is off (NOVA_DILUTION_READER=0)."),
    (None, "Not known", "The EDGAR reader could not be asked."),
    ({"status": "read", "symbol": "TEST"}, "Not known", "The EDGAR reader gave no answer."),
])
def test_what_is_not_known_says_why_and_is_never_clean(view, value, said):
    r = dilution.row(view, NOW)
    assert (r["state"], r["value"], r["source"], r["as_of"]) == ("unknown", value, "sec_edgar", None)
    assert said in r["detail"]


def test_a_list_not_read_back_far_enough_is_unknown_unless_something_is_on_file():
    files = [page("2025-09-20")]
    r = dilution.row(kept(ROUTINE, files), NOW)
    assert (r["state"], r["value"], r["as_of"]) == ("unknown", "Not known", at(7, 2))
    assert "Not known: S-3 / F-3 shelf -- EDGAR lists filings up to 2025-09-20 that Nova did not read." in r["detail"]
    found = dilution.row(kept(ROUTINE + [("424B2", "2026-09-29")], files), NOW)
    assert (found["state"], found["value"]) == ("warn", "424B2 2026-09")
    assert "Not known: S-3 / F-3 shelf" in found["detail"]


def test_a_read_past_its_day_keeps_what_is_on_file_and_drops_a_clean_answer():
    clean = dilution.row(kept(ROUTINE, stale=True), NOW)
    assert (clean["state"], clean["value"]) == ("unknown", "Not known")
    assert clean["detail"].startswith("The last read found none on file.")
    assert clean["detail"].endswith("A new read of EDGAR is under way.")
    held = dilution.row(kept(ON_FILE, stale=True, error="HTTPError: HTTP Error 503: Service Unavailable"), NOW)
    assert held["state"] == "warn" and held["value"].startswith("S-3 shelf 2025-03")
    assert held["detail"].endswith("EDGAR could not be read again: HTTPError: HTTP Error 503: Service Unavailable.")


def test_a_cut_count_says_so():
    notes = [("424B2", ago(i)) for i in range(STOCK_READ_DILUTION_KEEP_PER_KIND + 5)]
    assert f"({STOCK_READ_DILUTION_KEEP_PER_KIND}+ in the last 180 days)" in dilution.row(kept(notes), NOW)["detail"]


# -- the float group ----------------------------------------------------------------------------------
def test_the_float_group_carries_the_row_and_the_tile_stays_the_floats(monkeypatch):
    monkeypatch.setattr(history, "summary", lambda sym, now: None)
    facts = {"symbol": "TEST", "now": NOW, "errors": {}, "bars": [], "bars5": [], "dilution": kept(ON_FILE),
             "why": {"facts": {"symbol": "TEST", "float_shares": 4_200_000, "volume": 9_000_000}}}
    ids = [r["id"] for r in rows.float_rows(facts)]
    assert ids == ["float", "rotation", "split", "dilution", "dilution_on_file"]
    out = read.build(facts)
    group = next(g for g in out["groups"] if g["id"] == "float")
    assert group["rows"][-1]["state"] == "warn" and group["rows"][-1]["source"] == "sec_edgar"
    assert (group["verdict"], group["value"]) == ("ok", "4.2M")            # the tile is still the float's
    assert sum(out["counts"].values()) == sum(len(g["rows"]) for g in out["groups"])
    unasked = rows.float_rows({**facts, "dilution": None})[-1]
    assert unasked["state"] == "unknown" and unasked["detail"]


# -- the reader ---------------------------------------------------------------------------------------
class Edgar:
    """SEC as the reader sees it: answers by URL, records every request, fails where told to."""

    def __init__(self):
        self.calls: list[str] = []
        self.agents: list[str] = []
        self.tickers = {"0": {"cik_str": 1234567, "ticker": "TEST", "title": "Test Co"},
                        "1": {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"}}
        self.answers: dict[str, object] = {SUBMISSIONS: submissions(ROUTINE + ON_FILE)}
        self.gate: threading.Event | None = None

    def __call__(self, url: str, headers: dict) -> bytes:
        self.calls.append(url)
        self.agents.append(headers.get("User-Agent", ""))
        if self.gate is not None:
            assert self.gate.wait(5)
        answer = self.tickers if url == CATALYST_FEED_SEC_TICKERS_URL else self.answers.get(url)
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return json.dumps(answer).encode()


class Desk:
    """A reader on a fake clock, with SEC stubbed and no real sleeping."""

    def __init__(self, tmp_path, now=NOW):
        self.now, self.mono, self.slept = now, 100.0, []
        self.edgar = Edgar()
        self.db_path = tmp_path / "dilution.sqlite3"
        self.reader = self.open()

    def open(self) -> dilution_reader.DilutionReader:
        return dilution_reader.DilutionReader(fetch=self.edgar, clock=lambda: self.now, sleep=self.slept.append,
                                              monotonic=lambda: self.mono, db=dilution_store.connect(self.db_path))

    def ask(self, symbol="TEST") -> dict:
        return self.reader.view(symbol, self.now)

    def settle(self) -> None:
        worker = self.reader._worker
        if worker is not None:
            worker.join(5)
        assert not self.reader._pending and self.reader._worker is None


@pytest.fixture()
def desk(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_DILUTION_READER", "1")
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    d = Desk(tmp_path)
    yield d
    d.settle()
    d.reader.close()


def test_the_first_ask_answers_at_once_and_the_read_lands_in_the_background(desk):
    desk.edgar.gate = threading.Event()                       # SEC has not answered yet
    first = desk.ask()
    assert first == {"status": "reading", "symbol": "TEST"}
    assert dilution.row(first, desk.now)["detail"].startswith("Reading EDGAR…")
    desk.edgar.gate.set()
    desk.settle()
    got = desk.ask()
    assert got["status"] == "read" and got["cik"] == 1234567 and got["name"] == "Test Co" and got["stale"] is False
    assert got["fetched_at"] == desk.now
    assert dilution.row(got, desk.now)["value"] == "S-3 shelf 2025-03, 424B5 2026-08, S-1/A 2026-07, 8-K 3.02 2026-09"
    assert desk.edgar.calls == [CATALYST_FEED_SEC_TICKERS_URL, SUBMISSIONS]


def test_a_read_serves_the_day_and_is_made_again_at_the_next_session(desk):
    desk.ask()
    desk.settle()
    desk.now = at(19, 30)
    assert desk.ask()["stale"] is False
    desk.now = at(3, 59, TODAY + timedelta(days=1))           # the same session day until 04:00 ET
    assert desk.ask()["stale"] is False
    desk.settle()
    assert len(desk.edgar.calls) == 2
    desk.now = at(4, 0, TODAY + timedelta(days=1))
    desk.edgar.answers[SUBMISSIONS] = submissions(ROUTINE)
    old = desk.ask()                                          # the kept read, marked, while the new one is made
    assert old["stale"] is True and old["fetched_at"] == NOW
    desk.settle()
    new = desk.ask()
    assert new["stale"] is False and new["fetched_at"] == desk.now and new["filings"] == []
    assert desk.edgar.calls[2:] == [CATALYST_FEED_SEC_TICKERS_URL, SUBMISSIONS]


def test_a_read_is_never_fresh_past_its_ttl_or_across_four_am():
    assert dilution_reader.session_start(at(3, 59)) == at(4, 0, TODAY - timedelta(days=1))
    assert dilution_reader.session_start(at(4, 0)) == at(4, 0)
    assert dilution_reader.fresh(at(4, 0), at(23, 0)) and not dilution_reader.fresh(at(3, 59), at(4, 0))
    assert not dilution_reader.fresh(at(5, 0), at(5, 30), ttl=1800.0)


def test_a_failed_read_says_why_and_waits_before_it_is_tried_again(desk):
    desk.edgar.answers[SUBMISSIONS] = urllib.error.URLError("timed out")
    desk.ask()
    desk.settle()
    failed = desk.ask()
    assert failed == {"status": "error", "symbol": "TEST", "error": "URLError: <urlopen error timed out>",
                      "retry_at": NOW + 30}
    assert dilution.row(failed, desk.now)["state"] == "unknown"
    desk.now = NOW + 29
    desk.ask()
    desk.settle()
    assert len(desk.edgar.calls) == 2                         # nothing asked inside the wait
    desk.now = NOW + 30
    assert desk.ask()["status"] == "reading"
    desk.settle()
    assert desk.ask()["retry_at"] == NOW + 30 + 120           # the second wait is longer
    desk.edgar.answers[SUBMISSIONS] = submissions(ROUTINE)
    desk.now = NOW + 30 + 120
    desk.ask()
    desk.settle()
    assert (desk.ask()["status"], desk.ask()["error"]) == ("read", None)


def test_a_symbol_sec_does_not_list_has_no_registrant(desk):
    desk.ask("ZZZZ")
    desk.settle()
    got = desk.ask("ZZZZ")
    assert got["status"] == "no_cik" and got["stale"] is False
    r = dilution.row(got, desk.now)
    assert r["state"] == "unknown" and "no registrant for ZZZZ (list read Oct 1 09:00 ET)" in r["detail"]
    desk.settle()
    assert desk.edgar.calls == [CATALYST_FEED_SEC_TICKERS_URL]            # looked up, and kept for the day


def test_a_share_class_is_looked_up_as_sec_writes_it(desk):
    desk.edgar.answers["https://data.sec.gov/submissions/CIK0001067983.json"] = submissions(ROUTINE, name="BERKSHIRE")
    for symbol in ("BRK/B", "BRK B", "brk.b"):
        desk.ask(symbol)
        desk.settle()
        assert desk.ask(symbol)["cik"] == 1067983
    assert dilution_reader.ticker_key("BRK/B") == "BRK-B"


def test_no_ticker_list_fails_every_ask_with_one_request(desk):
    desk.edgar.tickers = urllib.error.HTTPError(CATALYST_FEED_SEC_TICKERS_URL, 403, "Forbidden", None, None)
    desk.ask("TEST")
    desk.ask("ZZZZ")
    desk.settle()
    assert desk.edgar.calls == [CATALYST_FEED_SEC_TICKERS_URL]            # the second symbol did not ask again
    for symbol in ("TEST", "ZZZZ"):
        assert desk.ask(symbol)["error"] == "SEC's ticker list could not be read (HTTPError: HTTP Error 403: Forbidden)"


def test_a_ticker_list_that_cannot_be_read_again_still_serves(desk):
    desk.ask()
    desk.settle()
    desk.now = at(7, 0, TODAY + timedelta(days=1))
    desk.edgar.tickers = urllib.error.URLError("reset")
    desk.ask()
    desk.settle()
    assert desk.ask()["status"] == "read" and desk.ask()["stale"] is False
    assert desk.edgar.calls[2:] == [CATALYST_FEED_SEC_TICKERS_URL, SUBMISSIONS]


def test_an_older_page_is_read_when_it_can_answer(desk):
    desk.edgar.answers[SUBMISSIONS] = submissions(ROUTINE, [page("2025-09-20")])
    desk.edgar.answers[f"https://data.sec.gov/submissions/{PAGE}"] = block([("F-3", "2024-05-06")])
    desk.ask()
    desk.settle()
    got = desk.ask()
    assert got["unread_to"] is None and got["filings"] == [{"kind": "shelf", "form": "F-3", "date": "2024-05-06"}]
    assert desk.edgar.calls[-1].endswith(PAGE)


def test_requests_are_paced_and_carry_the_desks_sec_user_agent(desk, monkeypatch):
    desk.ask()
    desk.settle()
    assert desk.slept == [1.0]                                 # the second request waited out the gap
    assert set(desk.edgar.agents) == {CATALYST_FEED_SEC_USER_AGENT_DEFAULT}
    monkeypatch.setenv("SEC_USER_AGENT", "NovaDesk ops@example.com")
    desk.mono += 5.0
    desk.ask("ZZZZ")
    desk.settle()
    desk.now = at(4, 0, TODAY + timedelta(days=1))
    desk.ask()
    desk.settle()
    assert desk.edgar.agents[-1] == "NovaDesk ops@example.com"


def test_a_kept_read_survives_a_restart_without_asking_sec(desk):
    desk.ask()
    desk.settle()
    desk.reader.close()
    desk.reader = desk.open()                                  # a new process on the same cache
    got = desk.ask()
    desk.settle()
    assert got["status"] == "read" and got["stale"] is False and got["fetched_at"] == NOW
    assert len(desk.edgar.calls) == 2
    stored = sqlite3.connect(desk.db_path)
    assert stored.execute("PRAGMA user_version").fetchone()[0] == 1
    assert [r[0] for r in stored.execute("SELECT symbol FROM reads")] == ["TEST"]
    stored.close()


def test_a_kept_row_that_is_not_a_read_is_left_out_and_read_again(tmp_path):
    db = dilution_store.connect(tmp_path / "dilution.sqlite3")
    good = {"status": "read", "cik": 1234567, "name": "Test Co", "more": [], "unread_to": None, "fetched_at": NOW,
            "filings": [{"kind": "shelf", "form": "S-3", "date": "2025-03-14"}]}
    dilution_store.put(db, "GOOD", good)
    with db:
        db.executemany("INSERT INTO reads (symbol, fetched_at, body) VALUES (?, ?, ?)", [
            ("TORN", NOW, '{"status": "read", "filings": [{"kind": "shelf"'),
            ("ODD", NOW, json.dumps({"status": "read", "filings": [{"kind": "shelf", "date": "2025-03-14"}]})),
            ("ELSE", NOW, json.dumps({"status": "pending", "filings": []})),
            ("LIST", NOW, json.dumps([1, 2, 3])),
        ])
    assert dilution_store.load(db) == {"GOOD": good}
    dilution_store.prune(db, NOW + 1)
    assert dilution_store.load(db) == {}
    db.close()


def test_a_store_of_another_version_is_refused_and_the_reader_answers_from_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_DILUTION_READER", "1")
    target = dilution_store.path()
    target.parent.mkdir(parents=True, exist_ok=True)
    other = sqlite3.connect(target)
    other.execute("PRAGMA user_version = 99")
    other.close()
    with pytest.raises(RuntimeError, match="schema version 99"):
        dilution_store.connect()
    edgar = Edgar()
    reader = dilution_reader.DilutionReader(fetch=edgar, clock=lambda: NOW, sleep=lambda s: None)
    reader.read("TEST")
    assert reader.view("TEST", NOW)["status"] == "read" and "schema version 99" in reader.store_error
    reader.close()


def test_the_reader_switched_off_asks_nothing(desk, monkeypatch):
    monkeypatch.setenv("NOVA_DILUTION_READER", "0")
    assert desk.ask() == {"status": "off", "symbol": "TEST"}
    assert desk.reader._worker is None and desk.edgar.calls == []
    assert dilution.row(desk.ask(), desk.now)["state"] == "unknown"


def test_the_suite_keeps_the_desks_own_reader_off():
    # conftest pins NOVA_DILUTION_READER=0: a read a test asks for must never reach SEC.
    assert dilution_reader.view("test", NOW) == {"status": "off", "symbol": "TEST"}
    assert dilution_reader.get_reader()._worker is None and dilution_reader.get_reader()._db is None
    dilution_reader.reset_for_tests()


def test_gather_asks_the_reader_and_never_waits(monkeypatch):
    from stock_read import gather

    seen = []
    monkeypatch.setattr(dilution_reader, "view", lambda sym, now: seen.append((sym, now)) or {"status": "reading", "symbol": sym})
    assert gather._dilution("TEST", NOW) == {"status": "reading", "symbol": "TEST"} and seen == [("TEST", NOW)]
