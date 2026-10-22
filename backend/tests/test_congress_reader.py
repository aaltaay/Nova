"""ADR 066: the Congress reader end to end on a fake network, its store, the agreement, and the routes."""
import io
import sqlite3
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from congress import consent, house_pdf, refresh, roster
from congress.constants_congress import CONGRESS_ROSTER_BASE, CONGRESS_STORE_VERSION
from congress.routes import router
from congress.state import book, source
from congress.store import Store

SATURDAY = datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()
UUID_E = "0541be4f-4f96-4d84-8d6f-d349f218bb2a"
UUID_P = "1111be4f-4f96-4d84-8d6f-d349f218bb2a"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
HOUSE_TEXT = ("ID Owner Asset Transaction\nType\nDate Notification\nDate\nAmount Cap.\nGains >\n$200?\n"
              "SP Example Corp - Common Stock\n(EXC) [ST]\nP 09/18/202610/09/2026$1,001 - $15,000\nF S : New\n"
              "* For the complete list of asset type abbreviations\n")
SENATE_PAGE = ("<table><tbody><tr><td>1</td><td>09/04/2026</td><td>Spouse</td><td>EXA</td><td>Example Bank</td>"
               "<td>Stock</td><td>Purchase</td><td>$15,001 - $50,000</td><td>--</td></tr></tbody></table>")


def legislator(bio, first, last, kind, state, district=None, party="Democrat", end="2027-01-03"):
    term = {"type": kind, "state": state, "party": party, "start": "2025-01-03", "end": end}
    if district is not None:
        term["district"] = district
    return {"id": {"bioguide": bio}, "name": {"first": first, "last": last, "official_full": f"{first} {last}"},
            "terms": [term]}


def index_zip(year, rows):
    lines = ["Prefix\tLast\tFirst\tSuffix\tFilingType\tStateDst\tYear\tFilingDate\tDocID"]
    lines += [f"Hon.\t{last}\t{first}\t\tP\t{sd}\t{year}\t{filed}\t{doc}" for last, first, sd, filed, doc in rows]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{year}FD.txt", "\n".join(lines))
    return buf.getvalue()


class Resp:
    def __init__(self, status=200, content=b"", json_body=None, headers=None):
        self.status_code, self.content, self._json, self.headers = status, content, json_body, headers or {}
        self.text = content.decode("utf-8", "replace")

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeNet:
    def __init__(self):
        self.calls = []

    def get(self, url, **kw):
        return self._answer("GET", url, kw)

    def post(self, url, **kw):
        return self._answer("POST", url, kw)

    def _answer(self, method, url, kw):
        self.calls.append((method, url))
        if url == CONGRESS_ROSTER_BASE + "legislators-current.json":
            return Resp(json_body=[legislator("S000001", "Pat", "Example", "sen", "AA"),
                                   legislator("H000001", "Robin", "Sample", "rep", "BB", 7, "Republican")])
        if url == CONGRESS_ROSTER_BASE + "committees-current.json":
            return Resp(json_body=[{"thomas_id": "SSFI", "name": "Committee on Finance"}])
        if url == CONGRESS_ROSTER_BASE + "committee-membership-current.json":
            return Resp(json_body={"SSFI": [{"bioguide": "S000001"}], "SSFI13": [{"bioguide": "S000001"}]})
        if url.endswith("2026FD.zip"):
            if (kw.get("headers") or {}).get("If-Modified-Since"):
                return Resp(304)
            return Resp(content=index_zip(2026, [("Sample", "Robin", "BB07", "10/12/2026", "20012345"),
                                                 ("Sample", "Robin", "BB07", "10/02/2026", "8212345")]),
                        headers={"Last-Modified": "Wed, 14 Oct 2026 13:00:38 GMT"})
        if url.endswith("2025FD.zip"):
            return Resp(404)
        if url.endswith("/ptr-pdfs/2026/20012345.pdf"):
            return Resp(content=HOUSE_TEXT.encode())
        if url.endswith("/search/home/") and method == "GET":
            return Resp(content=b'<form><input name="csrfmiddlewaretoken" value="tok123"></form>')
        if url.endswith("/search/home/") and method == "POST":
            kw["session"].cookies.set("csrftoken", "tok456")
            return Resp()
        if url.endswith("/search/report/data/"):
            return Resp(json_body={"recordsTotal": 2, "data": [
                ["Pat", "Example", "Example, Pat (Senator)",
                 f'<a href="/search/view/ptr/{UUID_E}/">Periodic Transaction Report for 10/01/2026</a>', "10/01/2026"],
                ["Pat", "Example", "Example, Pat (Senator)",
                 f'<a href="/search/view/paper/{UUID_P}/">Periodic Transaction Report</a>', "09/02/2026"]]})
        if url.endswith(f"/search/view/ptr/{UUID_E}/"):
            return Resp(content=SENATE_PAGE.encode())
        if "S000001" in url:
            return Resp(content=JPEG)
        return Resp(404)


@pytest.fixture
def net(monkeypatch):
    monkeypatch.setattr(house_pdf, "pdf_text", lambda data: data.decode())
    fake = FakeNet()
    refresh.reset_for_tests(fake)
    return fake


def run_all(limit=50):
    for _ in range(limit):
        if not refresh.run_once(SATURDAY):
            return
    raise AssertionError("the reader never ran out of work")


def test_nothing_is_fetched_before_the_agreement(net):
    assert refresh.run_once(SATURDAY) is False
    assert net.calls == [] and source("house").state == "needs_consent"


def test_the_reader_reads_both_chambers_after_the_agreement(net):
    consent.accept(SATURDAY)
    run_all()
    _, reports, trades = book().snapshot()
    assert set(reports) == {"H:2026:20012345", "H:2026:8212345", f"S:{UUID_E}", f"S:{UUID_P}"}
    assert reports["H:2026:8212345"]["kind"] == "paper" and reports["H:2026:8212345"]["read_at"] is None
    assert reports["H:2026:20012345"]["bioguide"] == "H000001" and reports[f"S:{UUID_E}"]["bioguide"] == "S000001"
    assert sorted((t.ticker, t.side, t.owner, t.chamber) for t in trades) == [
        ("EXA", "buy", "spouse", "senate"), ("EXC", "buy", "spouse", "house")]
    assert roster.by_bioguide()["S000001"]["committees"] == ["Committee on Finance"]
    assert source("house").state == "ok" and source("senate").state == "ok" and source("photos").state == "ok"
    urls = [u for _, u in net.calls]
    assert urls.index(CONGRESS_ROSTER_BASE + "legislators-current.json") < urls.index(next(u for u in urls if "FD.zip" in u))
    assert not any("8212345.pdf" in u for u in urls)                              # a scanned report is never downloaded
    assert any(u.endswith("/S000001.jpg") for u in urls)


def test_a_restart_reads_nothing_twice(net):
    consent.accept(SATURDAY)
    run_all()
    refresh.reset_for_tests(FakeNet())
    book().reset()
    again = refresh._ctx["net"]
    run_all()
    assert len(book().snapshot()[2]) == 2                                        # the kept store came back
    urls = [u for _, u in again.calls]
    assert not any(u.endswith(".pdf") for u in urls) and not any(f"/ptr/{UUID_E}" in u for u in urls)


def test_a_store_of_another_version_is_set_aside(tmp_path):
    path = tmp_path / "filings.sqlite3"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE reports (id TEXT)")
    db.execute("PRAGMA user_version = 99")
    db.commit()
    db.close()
    st = Store(path)
    assert st.reports() == {} and list(tmp_path.glob("filings.sqlite3.v99.*.bak"))
    st.close()
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == CONGRESS_STORE_VERSION


def test_the_agreement_must_be_to_todays_words():
    assert consent.wire()["state"] == "needed"
    consent.accept(1.0)
    assert consent.wire()["state"] == "given" and consent.wire()["accepted_at"] == 1.0
    consent.path().write_text('{"schema_version": 1, "accepted_at": 2.0, "text_sha256": "other words"}')
    assert consent.given() is False
    consent.accept(3.0)
    consent.withdraw()
    assert consent.given() is False


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(refresh, "start", lambda: None)
    monkeypatch.setattr(refresh, "wake", lambda: None)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_routes_ask_for_the_agreement_first(client):
    body = client.get("/api/congress/board").json()
    assert body["schema_version"] == 1 and body["consent"]["state"] == "needed"
    assert "commercial purpose" in body["consent"]["text"] and "13107" in body["consent"]["cite"]
    assert client.post("/api/congress/consent", json={"accept": "yes"}).status_code == 400
    assert client.post("/api/congress/consent", content=b"not json").status_code == 400
    assert client.post("/api/congress/consent", json={"accept": True}).json()["consent"]["state"] == "given"
    assert client.get("/api/congress/board").json()["consent"]["state"] == "given"
    assert client.post("/api/congress/consent", json={"accept": False}).json()["consent"]["state"] == "needed"


def test_routes_refuse_bad_parameters(client):
    bad = client.get("/api/congress/board?filter=everything")
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == "CONGRESS_BAD_PARAM"
    assert client.get("/api/congress/board?members=nope").status_code == 400
    assert client.get("/api/congress/board?members=S000001,H000001").status_code == 200
    assert client.get("/api/congress/trades?ticker=").status_code == 400
    assert client.get("/api/congress/trades?ticker=aapl").json()["ticker"] == "AAPL"
    unknown = client.get("/api/congress/member/Z999999")
    assert unknown.status_code == 404 and unknown.json()["detail"]["reason"] == "CONGRESS_UNKNOWN_MEMBER"
    assert client.get("/api/congress/photo/..%2Fsecrets").status_code == 404


def test_a_kept_photo_is_served(client):
    from congress import photos

    assert client.get("/api/congress/photo/S000001").status_code == 404
    photos.file("S000001").write_bytes(JPEG)
    got = client.get("/api/congress/photo/S000001")
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg" and got.content == JPEG
