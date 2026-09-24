"""Filing an issue from the desk: the scrubber, the dump, the written title, the routes.

The repository is public, so most of this file checks what must never leave the PC.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from issue_report import compose, drafts, gh_filer
from issue_report import context as issue_context
from issue_report.dump import parse_log, render_dump
from issue_report.scrub import Scrubber
from main import app

KEY = "k" * 16
NOW = 1790262318.0  # 2026-09-24 11:05:18 ET


def scrubber() -> Scrubber:
    return Scrubber(secrets=["sekret-value-123456", "U7654321"],
                    roots=[(r"C:\Users\alice\github\Nova", "<repo>"), (r"F:\Nova", "<data>"), (r"C:\Users\alice", "<home>")],
                    user="alice", host="DESKTOP-ABC123")


# --- scrubber -----------------------------------------------------------------------------------

@pytest.mark.parametrize("raw, gone, kept", [
    ("token=sekret-value-123456&x=1", "sekret-value-123456", "token=[redacted]"),
    ("login ghp_abcdefghijklmnopqrstuvwxyz123456 ok", "ghp_", "[redacted]"),
    ("account U1234567 and DU7654321", "1234567", "account <account> and <account>"),
    ("NetLiquidation=25,123.45 BuyingPower: 100000", "25,123", "NetLiquidation=<amount>"),
    ("realized_pnl -312.50 today", "312.50", "realized_pnl <amount>"),
    ("lost $1,200 on it", "1,200", "$<amount>"),
    (r"store C:\Users\alice\github\Nova\backend\.cache\l2.db", "alice", r"<repo>\backend\.cache\l2.db"),
    (r"store F:\Nova\leaderboard\x.sqlite3", "F:\\", r"<data>\leaderboard\x.sqlite3"),
    (r"file at D:\Private\taxes.xlsx", "Private", "file at <path>"),
    ("file:///C:/Users/alice/AppData/Local/nova/app.asar/index.js:12", "alice", "<home>"),
    ("user alice on DESKTOP-ABC123", "DESKTOP-ABC123", "user <user> on <host>"),
    ("mail me at a.b@example.com", "example.com", "<email>"),
    ("peer 192.168.1.20 and 127.0.0.1", "192.168", "peer <ip> and 127.0.0.1"),
])
def test_scrubber_removes_what_identifies_the_pc_or_the_money(raw, gone, kept):
    out = scrubber().text(raw)
    assert gone not in out
    assert kept in out


def test_scrubber_keeps_the_debugging_facts():
    s = scrubber()
    line = "fill BUY 100 GCTK @ $4.13 on port 4001; aaltaay/Nova #612; Python 3.13.14"
    assert s.text(line) == line
    assert s.count == 0


def test_scrubber_drops_path_and_key_fields_from_evidence():
    s = scrubber()
    out = s.value({"store": r"F:\Nova\x.db", "path": r"C:\Users\alice\.env", "keys": ["APCA_API_KEY_ID"],
                   "nested": {"repo_root": "C:\\", "port": 4001}, "display": {"label": "DELL U2720Q", "index": 1}})
    assert out == {"store": r"<data>\x.db", "nested": {"port": 4001}, "display": {"index": 1}}


# Every mix of a known, missing or too-short name: each known name gets its own label. The patterns and
# their labels are zipped strictly, so the two lists drifting apart raises here instead of skipping a name.
@pytest.mark.parametrize("user, host, raw, want", [
    ("alice", "DESKTOP-ABC123", "alice on DESKTOP-ABC123", "<user> on <host>"),
    (None, "DESKTOP-ABC123", "alice on DESKTOP-ABC123", "alice on <host>"),
    ("", "DESKTOP-ABC123", "alice on DESKTOP-ABC123", "alice on <host>"),
    ("al", "DESKTOP-ABC123", "al on DESKTOP-ABC123", "al on <host>"),
    ("alice", None, "alice on DESKTOP-ABC123", "<user> on DESKTOP-ABC123"),
    ("alice", "PC", "alice on PC", "<user> on PC"),
    (None, None, "alice on DESKTOP-ABC123", "alice on DESKTOP-ABC123"),
])
def test_scrubber_gives_each_known_name_its_own_label(user, host, raw, want):
    assert Scrubber(user=user, host=host).text(raw) == want


# --- the engine log and the dump ---------------------------------------------------------------

LOG = """2026-09-24 10:34:11,001 INFO ibkr.ticks subscribed GCTK
2026-09-24 10:34:11,002 WARNING ibkr.session_errors connectivity lost (Error 1100)
2026-09-24 10:35:11,002 WARNING ibkr.session_errors connectivity lost (Error 1100)
2026-09-24 10:36:00,100 ERROR asyncio Exception in callback _loop_writing()
Traceback (most recent call last):
  File "x.py", line 1, in <module>
AssertionError: boom
2026-09-24 10:37:00,000 WARNING nova.client_errors client_error source=boundary msg=Cannot read x url=http://localhost:5173/ ua=Mozilla stack=at f component=
2026-09-24 10:38:00,000 WARNING catalysts.feed poll failed for C:\\Users\\alice\\x token=sekret-value-123456
"""


def test_parse_log_folds_repeats_keeps_the_exception_and_splits_desk_errors():
    records, clients = parse_log(LOG)
    assert [(r.logger, r.count) for r in records] == [
        ("ibkr.session_errors", 2), ("asyncio", 1), ("catalysts.feed", 1)]
    assert records[1].tail == "AssertionError: boom"
    assert len(clients) == 1 and clients[0].source == "boundary" and clients[0].message == "Cannot read x"


def diag_payload():
    return {
        "groups": [{"id": "process", "title": "Process"}, {"id": "gateway", "title": "Gateway"}],
        "rows": [
            {"group": "process", "state": "ok", "title": "Repo root", "detail": r"C:\Users\alice\github\Nova",
             "cause": "", "evidence": {"repo_root": r"C:\Users\alice\github\Nova", "pid": 1}},
            {"group": "gateway", "state": "fail", "title": "Gateway API port", "detail": "live port 4001 refused",
             "cause": "IB Gateway is not running", "evidence": {"live_port": 4001, "account_id": "U7654321"}},
            {"group": "gateway", "state": "warn", "title": "Last IB error", "detail": "Error 101", "cause": "x",
             "evidence": {}},
        ],
    }


def make_dump(**over):
    records, clients = parse_log(LOG)
    args = dict(diag=diag_payload(), diag_error=None, records=records, log_error=None, client_errors=clients,
                windows=[{"window_id": "main", "role": "main", "page": "trader", "symbol": "GCTK", "focused": True}],
                context_lines=["Nova v991 (dc0e346a)", "Venue: Paper"], now=NOW, scrubber=scrubber())
    args.update(over)
    return render_dump(**args)


def test_dump_is_readable_and_carries_nothing_private():
    dump = make_dump()
    assert dump.file_name == "nova-dump-2026-09-24-1105.txt"
    assert dump.summary["fail"] == 1 and dump.summary["warn"] == 1 and dump.summary["rows"] == 3
    text = dump.text
    for needle in ("alice", "U7654321", "sekret-value-123456", "C:\\Users"):
        assert needle not in text
    assert "[FAIL] Gateway API port: live port 4001 refused" in text
    assert '"live_port": 4001' in text           # evidence kept outside the private groups
    assert '"pid": 1' not in text                 # process evidence left out
    assert "x2" in text and "AssertionError: boom" in text
    assert "- main (main): page trader, symbol GCTK, in front" in text


def test_dump_says_when_a_source_could_not_be_read():
    dump = make_dump(diag=None, diag_error="TimeoutError: probe", records=[], log_error="OSError: gone",
                     windows=[], windows_error="RuntimeError: lock")
    assert "(the focus sensor could not be read: RuntimeError: lock)" in dump.text
    assert "(the checklist could not be read: TimeoutError: probe)" in dump.text
    assert "(unreadable: OSError: gone)" in dump.text


# --- the written title and description -----------------------------------------------------------

CTX = {"nova": "v991", "commit": "dc0e346a", "venue": "paper", "page": "trader", "symbol": "gctk"}


def test_an_empty_bug_is_titled_and_described_from_the_dump():
    issue = compose.compose_issue(kind="bug", title="", details="  ", context=CTX, filed_at=NOW, scrubber=scrubber(),
                                  dump=make_dump(), dump_link=compose.DumpLink("d.txt", "https://gist.github.com/aaltaay/abc", None, True))
    assert issue.title == "Desk report: Gateway API port — live port 4001 refused (Trader · GCTK, 11:05 ET)"
    assert issue.auto_title and issue.auto_description
    assert issue.labels == ["bug"]
    assert "_No description was written; Nova summarized the dump._" in issue.body
    assert "- `FAIL` Gateway API port: live port 4001 refused" in issue.body
    assert "**Latest engine errors**\n- 10:36:00 asyncio:" in issue.body
    assert "- Diagnostics dump: [d.txt](https://gist.github.com/aaltaay/abc)" in issue.body
    assert "- Page: Trader · GCTK" in issue.body
    assert '"auto_title":true' in issue.body


def test_typed_words_are_kept_scrubbed_and_the_title_comes_from_the_first_line():
    issue = compose.compose_issue(kind="bug", title="", details="Chart froze on C:\\Users\\alice\\x\nsecond line",
                                  context=None, filed_at=NOW, scrubber=scrubber(), dump=make_dump())
    assert issue.title == "Chart froze on <home>\\x"
    assert not issue.auto_description and issue.removed >= 1
    assert "alice" not in issue.body


def test_a_feature_needs_words_and_an_empty_report_needs_the_dump():
    with pytest.raises(compose.IssueError) as err:
        compose.compose_issue(kind="feature", title="", details="", context=CTX, filed_at=NOW, scrubber=scrubber(),
                              dump=make_dump())
    assert err.value.field == "title"
    with pytest.raises(compose.IssueError):
        compose.compose_issue(kind="bug", title="", details="", context=CTX, filed_at=NOW, scrubber=scrubber())
    feature = compose.compose_issue(kind="feature", title="Hot key to flatten all", details="", context=None,
                                    filed_at=NOW, scrubber=scrubber())
    assert feature.labels == ["enhancement"] and feature.title == "Hot key to flatten all"


def test_a_failed_upload_is_stated_in_the_issue():
    issue = compose.compose_issue(kind="bug", title="x", details="", context=None, filed_at=NOW, scrubber=scrubber(),
                                  dump=make_dump(), dump_link=compose.DumpLink("d.txt", None, "gist refused", True))
    assert "- Diagnostics dump: not uploaded (gist refused); saved on the desk as `d.txt`" in issue.body


def test_context_keeps_checked_fields_only():
    ctx = compose.clean_context({"nova": "v991; rm -rf", "venue": "moon", "page": "trader", "symbol": "gctk",
                                 "tab": "gainers"})
    assert ctx == {"nova": None, "commit": None, "ui": None, "venue": None, "page": "trader", "tab": None,
                   "symbol": "GCTK"}


def test_the_fallback_link_never_cuts_the_hidden_record_in_half():
    issue = compose.compose_issue(kind="bug", title="t", details="x" * 7000, context=None, filed_at=NOW,
                                  scrubber=scrubber())
    url = compose.new_issue_url(issue)
    assert url.startswith("https://github.com/aaltaay/Nova/issues/new?title=t&body=")
    assert "nova-desk-issue" not in url and "cut%20to%20fit" in url


# --- routes ------------------------------------------------------------------------------------

@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("NOVA_API_KEY", KEY)
    drafts.reset_for_tests()
    gh_filer.reset_for_tests()
    monkeypatch.setattr(drafts, "_checklist", lambda ui: (diag_payload(), None))
    monkeypatch.setattr(drafts, "_log", lambda: (LOG, None))
    monkeypatch.setattr(drafts, "_windows", lambda: ([], None))
    monkeypatch.setattr(drafts, "save_copy", lambda dump: True)
    monkeypatch.setattr(issue_context, "scrubber", scrubber)
    monkeypatch.setattr(gh_filer, "status", lambda **kw: {"direct": True, "via": "gh", "account": "aaltaay",
                                                          "reason": None})
    calls: dict[str, list] = {"gist": [], "issue": []}

    def gist(name, text, desc):
        calls["gist"].append((name, text))
        return "https://gist.github.com/aaltaay/abc123"

    def issue(title, body, labels):
        calls["issue"].append((title, body, labels))
        return {"number": 612, "url": "https://github.com/aaltaay/Nova/issues/612"}

    monkeypatch.setattr(gh_filer, "create_gist", gist)
    monkeypatch.setattr(gh_filer, "file_issue", issue)
    yield TestClient(app), calls
    drafts.reset_for_tests()


def post(client, **form):
    body = {"schema_version": 1, "kind": "bug", "title": "", "details": "", "context": CTX, "attach_dump": True}
    body.update(form)
    return client.post("/api/issues", json=body, headers={"X-Nova-Api-Key": KEY})


def test_draft_then_one_click_file(api):
    client, calls = api
    draft = client.get("/api/issues/draft").json()
    assert draft["filer"]["account"] == "aaltaay" and draft["public"] is True
    assert draft["dump"]["summary"]["fail"] == 1 and draft["auto_title"].startswith("Desk report: Gateway API port")
    preview = client.get(f"/api/issues/draft/{draft['draft_id']}/dump")
    assert preview.status_code == 200 and "Nova desk dump" in preview.text and "alice" not in preview.text
    res = post(client, draft_id=draft["draft_id"])
    assert res.status_code == 201, res.text
    out = res.json()
    assert out["number"] == 612 and out["auto_title"] and out["dump"]["url"].endswith("abc123")
    assert calls["gist"][0][1] == preview.text   # what was previewed is what was uploaded
    assert "https://gist.github.com/aaltaay/abc123" in calls["issue"][0][1]


def test_a_failed_gist_still_files_the_issue(api, monkeypatch):
    client, calls = api

    def refuse(*a):
        raise gh_filer.FilerError("ISSUE_FILE_FAILED", "GitHub refused the dump: HTTP 422")

    monkeypatch.setattr(gh_filer, "create_gist", refuse)
    draft = client.get("/api/issues/draft").json()
    out = post(client, draft_id=draft["draft_id"]).json()
    assert out["dump"] == {"file_name": draft["dump"]["file_name"], "url": None,
                           "error": "GitHub refused the dump: HTTP 422", "saved": True}
    assert "not uploaded (GitHub refused the dump: HTTP 422)" in calls["issue"][0][1]


def test_no_signed_in_cli_answers_the_prefilled_link(api, monkeypatch):
    client, _ = api

    def refuse(*a):
        raise gh_filer.FilerError("ISSUE_FILER_UNAVAILABLE", "the GitHub CLI (gh) is not installed on this PC")

    monkeypatch.setattr(gh_filer, "file_issue", refuse)
    res = post(client, attach_dump=False, title="Chart froze")
    assert res.status_code == 503
    detail = res.json()["detail"]
    assert detail["reason"] == "ISSUE_FILER_UNAVAILABLE"
    assert detail["new_issue_url"].startswith("https://github.com/aaltaay/Nova/issues/new?title=Chart%20froze")


def test_refusals_happen_before_anything_is_uploaded(api):
    client, calls = api
    draft = client.get("/api/issues/draft").json()
    res = post(client, kind="feature", draft_id=draft["draft_id"])
    assert res.status_code == 400 and res.json()["detail"]["field"] == "title"
    expired = post(client, draft_id="nope")
    assert expired.status_code == 409 and expired.json()["detail"]["reason"] == "ISSUE_DRAFT_EXPIRED"
    assert calls == {"gist": [], "issue": []}


def test_filing_needs_the_desk_key_even_on_loopback(api, monkeypatch):
    client, calls = api
    assert client.post("/api/issues", json={"schema_version": 1}).status_code == 401
    monkeypatch.delenv("NOVA_API_KEY")
    res = client.post("/api/issues", json={"schema_version": 1})
    assert res.status_code == 503 and "file an issue" in res.json()["detail"]
    assert calls["issue"] == []


def test_drafts_expire(monkeypatch):
    drafts.reset_for_tests()
    monkeypatch.setattr(drafts, "_checklist", lambda ui: (None, "off"))
    monkeypatch.setattr(drafts, "_log", lambda: ("", None))
    monkeypatch.setattr(drafts, "_windows", lambda: ([], None))
    monkeypatch.setattr(issue_context, "scrubber", scrubber)
    draft = drafts.build(now=time.time())
    assert drafts.get(draft.id) is draft
    assert drafts.get(draft.id, now=draft.created + 10_000) is None
