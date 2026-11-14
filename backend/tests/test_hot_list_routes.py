"""``/api/hot-list``, and that the list never decides who trades a stock (ADR 044, amended 2026-10-06; ADR 072).

The list's writes need the desk's API key. A star is watching only: it never puts a stock on a bot list (there is
no default side any more, and the per-stock Buy / Sell switch retired with the bots, ADR 072), and taking a star
off leaves every venue's bot list as it was. The file, rollover and feed are ``test_hot_list.py``.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import hot_list
from bot.audit import list_entries
from bot.persist import load_session, save_session
from constants_hot_list import HOT_LIST_CAP
from hot_list import auto, service, store
from main import app
from tests.bot_helpers import headers, on_practice

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh():
    service.reset_for_tests()
    auto.reset_for_tests()
    yield
    service.reset_for_tests()
    auto.reset_for_tests()


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "hot-list-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return headers("hot-list-test-key")


def fill(n: int) -> None:
    doc = store.empty(store.trading_day())
    doc["entries"] = [{"symbol": f"F{i:02d}", "how": "star", "at": time.time(), "board": None, "rank": None,
                       "change_pct": None} for i in range(n)]
    store.save(doc)


# -- the routes ------------------------------------------------------------------------------------
def test_writes_need_the_api_key_and_the_view_does_not(monkeypatch):
    assert client.post("/api/hot-list/star", json={"symbol": "AISP"}).status_code == 503     # no key configured
    monkeypatch.setenv("NOVA_API_KEY", "hot-list-test-key")
    assert client.post("/api/hot-list/star", json={"symbol": "AISP"}).status_code == 401
    assert client.delete("/api/hot-list/AISP", headers=headers("wrong")).status_code == 401
    assert client.patch("/api/hot-list", json={"auto_n": 3}).status_code == 401
    assert client.post("/api/hot-list/bring-back").status_code == 401
    view = client.get("/api/hot-list")
    assert view.status_code == 200 and view.json()["entries"] == []


def test_the_view_answers_the_contract(key):
    from setup_scanner.engine import get_engine

    engine = get_engine()
    saved = engine.universe
    engine.universe = {"AISP"}
    try:
        body = client.post("/api/hot-list/star", json={"symbol": "aisp"}, headers=key).json()
    finally:
        engine.universe = saved
    assert body["schema_version"] == 1 and body["date"] == store.trading_day() and body["cap"] == HOT_LIST_CAP
    assert body["auto_cap"] == 20
    assert set(body["auto"]) == {"n", "start", "end", "rule", "error"} and body["auto"]["n"] == 5
    assert body["auto"]["start"] == "07:00" and body["auto"]["end"] == "16:00"
    assert "default" not in body and body["yesterday"] == [] and body["error"] is None
    [aisp] = body["entries"]
    assert aisp["symbol"] == "AISP" and aisp["how"] == "star" and aisp["followed"] is True
    assert aisp["why_not_followed"] is None
    assert aisp["board"] is None and aisp["rank"] is None and aisp["change_pct"] is None
    again = client.post("/api/hot-list/star", json={"symbol": "AISP"}, headers=key).json()
    assert [e["symbol"] for e in again["entries"]] == ["AISP"]                    # a second star is a no-op
    [unread] = client.get("/api/hot-list").json()["entries"]                    # the scanner does not read it
    assert unread["followed"] is False and unread["why_not_followed"]


def test_a_listed_name_past_the_reserved_slots_is_unfollowed_with_the_reason():
    import hod_momo_active as active
    import ibkr_bridge
    from setup_scanner.engine import get_engine
    from setup_scanner.symbol_view import not_followed_note

    active.clear_session_state()
    names = [f"S{i:02d}" for i in range(21)]                                  # a 21st, as a hand-edited file holds
    doc = store.empty(store.trading_day())
    doc["entries"] = [{"symbol": s, "how": "star", "at": time.time(), "board": None, "rank": None,
                       "change_pct": None} for s in names]
    store.save(doc)
    admitted = ibkr_bridge.refresh_hod_active_set()
    assert admitted[:20] == names[:20] and "S20" not in admitted
    engine = get_engine()
    saved = engine.universe
    engine.universe = set(admitted)
    try:
        entries = {e["symbol"]: e for e in client.get("/api/hot-list").json()["entries"]}
    finally:
        engine.universe = saved
    assert entries["S00"]["followed"] is True and entries["S00"]["why_not_followed"] is None
    assert entries["S20"]["followed"] is False
    assert entries["S20"]["why_not_followed"] == "HOD Momo's 20 reserved slots are full"
    assert not_followed_note("S20") == ("S20 is on today's hot list, but no lane reads it: HOD Momo's 20 "
                                        "reserved slots are full")


def test_refusals_carry_their_reason(key):
    bad = client.post("/api/hot-list/star", json={"symbol": "not a ticker!"}, headers=key)
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == "HOT_LIST_INVALID"
    assert client.post("/api/hot-list/star", json={}, headers=key).json()["detail"]["field"] == "symbol"
    fill(HOT_LIST_CAP)
    full = client.post("/api/hot-list/star", json={"symbol": "ONEMORE"}, headers=key)
    assert full.status_code == 409 and full.json()["detail"]["reason"] == "HOT_LIST_FULL"
    for body in ({"auto_n": 4}, {"auto_n": "5"}):
        res = client.patch("/api/hot-list", json=body, headers=key)
        assert res.status_code == 400 and res.json()["detail"]["reason"] == "HOT_LIST_INVALID"
    assert client.delete("/api/hot-list/!!", headers=key).json()["detail"]["reason"] == "HOT_LIST_INVALID"
    store._path().write_text('{"schema_version": 7}', encoding="utf-8")
    locked = client.post("/api/hot-list/star", json={"symbol": "AISP"}, headers=key)
    assert locked.status_code == 409 and locked.json()["detail"]["reason"] == "HOT_LIST_UNREADABLE"
    assert "schema_version 7" in client.get("/api/hot-list").json()["error"]


def test_settings_change_the_feed_and_ignore_a_retired_default_side(key):
    """``PATCH`` takes ``auto_n`` only. A desk still sending ``default_buy`` / ``default_sell`` is not refused:
    the fields are ignored, and nothing about a side is stored, served or audited."""
    res = client.patch("/api/hot-list", json={"auto_n": 10, "default_buy": "nova", "default_sell": "maybe"},
                       headers=key)
    assert res.status_code == 200
    body = res.json()
    assert body["auto"]["n"] == 10 and "top 10" in body["auto"]["rule"] and "default" not in body
    assert "default" not in store.read_raw()[0]
    assert client.patch("/api/hot-list", json={"auto_n": 0}, headers=key).json()["auto"]["n"] == 0
    only_side = client.patch("/api/hot-list", json={"default_buy": "nova"}, headers=key)
    assert only_side.status_code == 200 and only_side.json()["auto"]["n"] == 0      # nothing else changed
    lines = [r["inputs"] for r in list_entries(limit=20) if r["action"] == "hot_list"]
    assert [i["event"] for i in lines] == ["settings", "settings"]            # the side-only PATCH wrote nothing
    assert all(set(i) == {"event", "auto_n"} for i in lines)


def test_bring_back_stars_yesterdays_names_up_to_the_cap(key):
    earlier = store.trading_day(time.time() - 86_400)
    old = store.empty(earlier)
    old["entries"] = [{"symbol": s, "how": "auto", "at": 1.0, "board": "gainers", "rank": 1, "change_pct": 0.5}
                      for s in ("AAA", "BBB", "CCC")]
    store.save(old)
    assert client.get("/api/hot-list").json()["yesterday"] == ["AAA", "BBB", "CCC"]   # before the rollover ran
    body = client.post("/api/hot-list/bring-back", headers=key).json()
    assert [(e["symbol"], e["how"]) for e in body["entries"]] == [("AAA", "star"), ("BBB", "star"), ("CCC", "star")]
    fill(HOT_LIST_CAP)
    doc, _ = store.read_raw()
    doc["yesterday"] = ["AAA"]
    store.save(doc)
    full = client.post("/api/hot-list/bring-back", headers=key)
    assert full.status_code == 409 and full.json()["detail"]["reason"] == "HOT_LIST_FULL"


# -- a star never sets who trades the stock --------------------------------------------------------
def test_a_star_puts_a_name_on_no_bot_list(key):
    """No default side: starring a stock lists it and nothing else, on Paper as on Live."""
    on_practice("paper")
    assert client.post("/api/hot-list/star", json={"symbol": "XYZ"}, headers=key).status_code == 200
    assert hot_list.is_listed("XYZ") and "XYZ" not in (load_session().get("symbol_allowlist") or [])
    assert [r["inputs"]["event"] for r in list_entries(limit=50) if r["action"] == "hot_list"] == ["star"]


# -- taking a star off -------------------------------------------------------------------------------
def test_removing_the_star_leaves_every_venues_bot_list(key):
    on_practice("paper")
    client.post("/api/hot-list/star", json={"symbol": "AISP"}, headers=key)
    row = load_session()
    row["symbol_allowlist"] = ["AISP"]
    row["venue_levels"] = {**(row.get("venue_levels") or {}), "sim": {"level": 0, "symbol_allowlist": ["AISP", "KEEP"]}}
    save_session(row)
    res = client.delete("/api/hot-list/aisp", headers=key)
    assert res.status_code == 200 and res.json()["entries"] == []
    row = load_session()
    assert row["symbol_allowlist"] == ["AISP"] and row["venue_levels"]["sim"]["symbol_allowlist"] == ["AISP", "KEEP"]
    assert not hot_list.is_listed("AISP")
    assert [r["inputs"]["event"] for r in list_entries(limit=50) if r["action"] == "hot_list"][-1] == "remove"
    assert client.delete("/api/hot-list/AISP", headers=key).status_code == 200        # not listed: nothing to do
