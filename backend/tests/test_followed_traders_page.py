"""Followed traders, what the page needs beyond the day (operator ask 2026-10-13, the design canvas): the bar as the
feed last confirmed it, each trader's photo and live slot image, the read log behind a trade, and the toasts' read
without prices. Schema: architecture/schema/followed-traders.md.
"""
from __future__ import annotations

import copy
import json
import time
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from followed_traders import exits, feed, lines, reads, routes, view
from followed_traders.constants_followed import FOLLOWED_FEED_URL_ENV

BASE = "http://127.0.0.1:8787"
DATE = "2026-10-13"


def _ts(clock: str) -> str:
    return f"{DATE}T{clock}-04:00"


def _epoch(clock: str) -> float:
    return datetime.fromisoformat(_ts(clock)).timestamp()


def _trade(trader="ALPHA", symbol="ABCD", status="open", exit_clock=None):
    return {"trader": trader, "side": "long", "symbol": symbol, "entry_price": 2.0, "price": 2.0,
            "entry_ts": _ts("10:00:00"), "entry_since_ts": None, "entry_known": True, "adds": [],
            "exit_ts": _ts(exit_clock) if exit_clock else None, "exit_since_ts": None, "status": status,
            "entry_evidence": "frames/" + "a" * 32 + ".jpg", "exit_evidence": None}


def _raw_day(**status_extra):
    status = {"video": {"id": "x", "title": "Morning show"}, "live": True, "clock": "10:30:00",
              "updated_at": _ts("10:30:05"), "bar_visible": True, "traders": ["ALPHA", "BRAVO"]}
    status.update(status_extra)
    return {"date": DATE, "today": DATE, "dates": [DATE], "status": status, "trades": [_trade()]}


class _Resp:
    def __init__(self, status=200, chunks=(b"\xff\xd8jpeg",)):
        self.status_code = status
        self._chunks = list(chunks)

    def iter_content(self, _n):
        return iter(self._chunks)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    exits.reset_for_tests()
    lines.reset_for_tests()
    monkeypatch.delenv(FOLLOWED_FEED_URL_ENV, raising=False)
    monkeypatch.setattr(exits, "_path", lambda: tmp_path / "followed-exits.json")
    yield
    exits.reset_for_tests()
    lines.reset_for_tests()


# -- the optional pieces of the feed's day ----------------------------------------------------------------


def test_an_older_feed_without_the_new_pieces_reads_as_before():
    day = feed.parse_day(_raw_day())
    assert day["status"]["positions"] is None and day["status"]["slots"] == set() and day["faces"] == set()
    body = view.capture(day["status"], _epoch("10:30:06"))
    assert body["bar"] is None


def test_the_bar_as_last_confirmed_with_its_slot_images():
    raw = _raw_day(positions={"ALPHA": {"long:ABCD": 2.0, "short:WXYZ": 0.5512}, "BRAVO": {}},
                   slots={"ALPHA": "live/ALPHA.jpg", "BRAVO": "../etc/passwd"})
    status = feed.parse_day(raw)["status"]
    assert view.bar(status) == [
        {"trader": "ALPHA", "image": "/api/followed-traders/live/ALPHA.jpg", "face": None,
         "positions": [{"side": "long", "symbol": "ABCD", "price": 2.0},
                       {"side": "short", "symbol": "WXYZ", "price": 0.5512}]},
        # A path Nova may not ask for is no image, never a request.
        {"trader": "BRAVO", "image": None, "face": None, "positions": []},
    ]


@pytest.mark.parametrize("video, expected", [
    ({"id": "R5YIugCJar0", "title": "Morning show"}, "R5YIugCJar0"),
    ({"id": "x", "title": "Morning show"}, None),  # not a YouTube id: no player, no link, never a bad answer
    ({"id": "../../evil?x", "title": "Morning show"}, None),
    ({"id": 7, "title": "Morning show"}, None),
    ({"title": "Morning show"}, None),  # an older feed without the id
])
def test_the_stream_the_feed_reads_is_named_only_by_a_youtube_id(video, expected):
    status = feed.parse_day(_raw_day(video=video))["status"]
    assert status["video_id"] == expected
    assert view.capture(status, _epoch("10:30:06"))["video_id"] == expected


def test_the_bar_carries_each_traders_photo_on_the_feeds_today_only():
    raw = _raw_day(positions={"ALPHA": {"long:ABCD": 2.0}, "BRAVO": {}})
    raw["faces"] = {"BRAVO": "faces/BRAVO.jpg"}  # on the bar with no trade that day: the page still shows them
    day = feed.parse_day(raw)
    body = view.compose(day, now=_epoch("10:31:00"), prices={"state": "not_asked", "why": "x"},
                        now_for=lambda t: {}, exit_for=lambda t: {})
    assert [(s["trader"], s["face"]) for s in body["capture"]["bar"]] == [
        ("ALPHA", None), ("BRAVO", f"/api/followed-traders/faces/{DATE}/BRAVO.jpg")]
    day["today"] = "2026-10-14"  # a past day asked: its photos never stand in for the bar now
    body = view.compose(day, now=_epoch("10:31:00"), prices={"state": "past_day", "why": "x"},
                        now_for=lambda t: {}, exit_for=lambda t: {})
    assert [s["face"] for s in body["capture"]["bar"]] == [None, None]


@pytest.mark.parametrize("positions, field", [
    ({"ALPHA": {"sideways:ABCD": 2.0}}, "status.positions.ALPHA"),
    ({"ALPHA": {"long:ABCD": "2.0"}}, "status.positions.ALPHA.long:ABCD"),
    ({"ALPHA": [1]}, "status.positions.ALPHA"),
])
def test_a_bar_nova_cannot_read_is_a_bad_answer(positions, field):
    with pytest.raises(feed.FeedError) as err:
        feed.parse_day(_raw_day(positions=positions))
    assert err.value.state == "bad_answer" and field in err.value.message


def test_faces_on_the_day_become_this_apis_paths():
    raw = _raw_day()
    raw["faces"] = {"ALPHA": "faces/ALPHA.jpg", "BRAVO": "faces/CHARLIE.jpg"}
    day = feed.parse_day(raw)
    assert day["faces"] == {"ALPHA"}
    body = view.compose(day, now=_epoch("10:31:00"), prices={"state": "past_day", "why": "x"},
                        now_for=lambda t: {}, exit_for=lambda t: {})
    assert body["traders"][0]["face"] == f"/api/followed-traders/faces/{DATE}/ALPHA.jpg"


# -- the read log -------------------------------------------------------------------------------------


def _log_line(clock, **traders):
    return json.dumps({"clock": clock, "traders": {
        name: {"positions": pos, "unparsed": []} for name, pos in traders.items()}})


LOG = "\n".join([
    _log_line("10:00:00", ALPHA={"long:JYD": 1.35}, BRAVO={}),
    _log_line("10:00:10", ALPHA={"long:JYD": 1.35, "long:JBDI": 8.42}, BRAVO={}),
    _log_line("10:00:30", ALPHA={"long:JYD": 1.35, "long:JBD": 18.42}, BRAVO={}),  # a one-frame misread
    _log_line("10:00:32", ALPHA={"long:JYD": 1.35, "long:JBDI": 8.42}, BRAVO={}),
    _log_line("10:00:40", ALPHA={"long:JYD": 1.35, "long:JBDI": 8.42}, BRAVO={"long:NVDL": 35.41}),  # BRAVO only
    _log_line("10:01:00", TALPHA={"long:JYD": 1.35}),  # the name tag misread
    _log_line("10:01:02", ALPHA={"long:JYD": 1.35}),
    _log_line("10:05:00", ALPHA={}),
])


def test_parse_reads_and_name_a_bad_line():
    log = feed.parse_reads(LOG)
    assert log[1]["traders"]["ALPHA"]["positions"][1] == {"side": "long", "symbol": "JBDI", "price": 8.42}
    with pytest.raises(feed.FeedError, match="reads.jsonl line 2"):
        feed.parse_reads(_log_line("10:00:00") + "\n{not json")
    with pytest.raises(feed.FeedError, match="not HH:MM:SS"):
        feed.parse_reads(json.dumps({"clock": "10:00", "traders": {}}))
    # A frame the feed could not read at all has no clock: skipped, never a bad answer (the feed's log, 2026-10-13).
    assert feed.parse_reads(json.dumps({"clock": None, "traders": {}})) == []


def test_trader_reads_fold_and_window():
    log = feed.parse_reads(LOG)
    got = reads.trader_reads(log, date=DATE, trader="ALPHA", from_ts=_epoch("10:00:10"),
                             to_ts=_epoch("10:01:02"), max_reads=100)
    summary = [(datetime.fromtimestamp(r["ts"], reads.ET).strftime("%H:%M:%S"), r["seen"],
                [p["symbol"] for p in r["positions"]]) for r in got["reads"]]
    assert summary == [
        ("10:00:10", True, ["JYD", "JBDI"]),
        ("10:00:30", True, ["JYD", "JBD"]),
        ("10:00:32", True, ["JYD", "JBDI"]),  # 10:00:40 changed BRAVO only: folded in
        ("10:01:00", False, []),
        ("10:01:02", True, ["JYD"]),
    ]
    assert got["reads"][0]["until_ts"] == _epoch("10:00:30") and got["reads"][-1]["until_ts"] == _epoch("10:05:00")
    assert got["truncated"] is False


def test_trader_reads_start_with_the_read_in_force_and_cap():
    log = feed.parse_reads(LOG)
    got = reads.trader_reads(log, date=DATE, trader="ALPHA", from_ts=_epoch("10:00:05"),
                             to_ts=_epoch("10:00:05"), max_reads=100)
    assert [r["ts"] for r in got["reads"]] == [_epoch("10:00:00")]
    capped = reads.trader_reads(log, date=DATE, trader="ALPHA", from_ts=0, to_ts=_epoch("23:00:00"), max_reads=2)
    assert len(capped["reads"]) == 2 and capped["truncated"] is True


# -- the routes ---------------------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(FOLLOWED_FEED_URL_ENV, BASE)
    monkeypatch.setattr(routes, "_ibkr_ready", lambda: True)
    monkeypatch.setattr(routes, "_replay_desk", lambda: False)
    monkeypatch.setattr(lines, "_spawn_ib", lambda name, factory: None)
    monkeypatch.setattr(exits, "_spawn_ib", lambda name, factory: None)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_route_day_without_quotes_opens_no_line(client, monkeypatch):
    raw = _raw_day()
    today = routes.desk_day(time.time())[0]
    raw.update(date=today, today=today, dates=[today])
    monkeypatch.setattr(feed, "fetch_day", lambda base, date: feed.parse_day(copy.deepcopy(raw)))
    wanted = []
    monkeypatch.setattr(lines, "want", lambda syms, now: wanted.append(syms))
    body = client.get("/api/followed-traders/day?quotes=0").json()
    assert body["prices"] == {"state": "not_asked", "why": "asked without prices"}
    assert body["traders"][0]["open"][0]["now"]["state"] == "off" and wanted == []


def test_route_images_pass_through_and_say_missing(client, monkeypatch):
    asked = []

    def get(_pool, url, **_kw):
        asked.append(url)
        return _Resp(status=404) if "BRAVO" in url else _Resp()

    monkeypatch.setattr(feed.http_pool, "get", get)
    live = client.get("/api/followed-traders/live/ALPHA.jpg")
    assert live.status_code == 200 and live.content == b"\xff\xd8jpeg"
    assert live.headers["cache-control"] == "no-store" and live.headers["content-type"] == "image/jpeg"
    face = client.get(f"/api/followed-traders/faces/{DATE}/ALPHA.jpg")
    assert face.status_code == 200 and "max-age" in face.headers["cache-control"]
    assert client.get("/api/followed-traders/live/BRAVO.jpg").status_code == 404
    # Names and dates Nova may not ask for never reach the feed.
    assert client.get("/api/followed-traders/live/alpha.jpg").status_code == 404
    assert client.get("/api/followed-traders/faces/latest/ALPHA.jpg").status_code == 404
    assert asked == [f"{BASE}/files/live/ALPHA.jpg", f"{BASE}/files/{DATE}/faces/ALPHA.jpg",
                     f"{BASE}/files/live/BRAVO.jpg"]

    monkeypatch.setattr(feed.http_pool, "get", lambda *_a, **_k: _Resp(status=500))
    down = client.get("/api/followed-traders/live/ALPHA.jpg")
    assert down.status_code == 502 and down.json()["detail"]["reason"] == "FOLLOWED_FEED_UNREACHABLE"


def test_route_reads(client, monkeypatch):
    monkeypatch.setattr(feed.http_pool, "get", lambda *_a, **_k: _Resp(chunks=[LOG.encode()]))
    q = f"date={DATE}&trader=ALPHA&from_ts={_epoch('10:00:10')}&to_ts={_epoch('10:00:31')}"
    body = client.get(f"/api/followed-traders/reads?{q}").json()
    assert body["feed"]["state"] == "ok" and body["available"] is True and body["trader"] == "ALPHA"
    assert [r["positions"][-1]["symbol"] for r in body["reads"]] == ["JBDI", "JBD"]

    monkeypatch.setattr(feed.http_pool, "get", lambda *_a, **_k: _Resp(status=404))
    missing = client.get(f"/api/followed-traders/reads?{q}").json()
    assert missing["available"] is False and "no read log" in missing["why"] and missing["reads"] == []

    bad = client.get("/api/followed-traders/reads?date=yesterday&trader=ALPHA&from_ts=1&to_ts=2")
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == "FOLLOWED_BAD_DATE"
    backwards = client.get(f"/api/followed-traders/reads?date={DATE}&trader=ALPHA&from_ts=5&to_ts=2")
    assert backwards.status_code == 400 and backwards.json()["detail"]["reason"] == "FOLLOWED_BAD_READS"
