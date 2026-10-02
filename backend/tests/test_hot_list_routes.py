"""``/api/hot-list`` and the Who trades tie-in (ADR 043 decision 4).

The list's writes need the desk's API key; a star takes the list's default Buy / Sell where the venue
allows a Nova side; Buy to Nova stars an unlisted stock (a full list refuses first); a removal is You · You
on every venue and is refused while Nova has an open trade. The file, rollover and feed are
``test_hot_list.py``.
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
from stock_mode import store as stock_store
from tests.bot_helpers import headers, on_practice

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh():
    service.reset_for_tests()
    auto.reset_for_tests()
    stock_store.reset_for_tests()
    yield
    service.reset_for_tests()
    auto.reset_for_tests()
    stock_store.reset_for_tests()


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


def mode_of(sym: str, key: dict) -> dict:
    res = client.get(f"/api/stock-mode/{sym}", headers=key)
    assert res.status_code == 200
    return res.json()


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
    assert set(body["auto"]) == {"n", "start", "end", "rule", "error"} and body["auto"]["n"] == 5
    assert body["auto"]["start"] == "07:00" and body["auto"]["end"] == "16:00"
    assert body["default"] == {"buy": "you", "sell": "you"} and body["yesterday"] == [] and body["error"] is None
    [aisp] = body["entries"]
    assert aisp["symbol"] == "AISP" and aisp["how"] == "star" and aisp["followed"] is True
    assert aisp["board"] is None and aisp["rank"] is None and aisp["change_pct"] is None
    again = client.post("/api/hot-list/star", json={"symbol": "AISP"}, headers=key).json()
    assert [e["symbol"] for e in again["entries"]] == ["AISP"]                    # a second star is a no-op
    assert client.get("/api/hot-list").json()["entries"][0]["followed"] is False   # the scanner does not read it


def test_refusals_carry_their_reason(key):
    bad = client.post("/api/hot-list/star", json={"symbol": "not a ticker!"}, headers=key)
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == "HOT_LIST_INVALID"
    assert client.post("/api/hot-list/star", json={}, headers=key).json()["detail"]["field"] == "symbol"
    fill(HOT_LIST_CAP)
    full = client.post("/api/hot-list/star", json={"symbol": "ONEMORE"}, headers=key)
    assert full.status_code == 409 and full.json()["detail"]["reason"] == "HOT_LIST_FULL"
    for body in ({"auto_n": 4}, {"auto_n": "5"}, {"default_buy": "maybe"}):
        res = client.patch("/api/hot-list", json=body, headers=key)
        assert res.status_code == 400 and res.json()["detail"]["reason"] == "HOT_LIST_INVALID"
    store._path().write_text('{"schema_version": 7}', encoding="utf-8")
    locked = client.post("/api/hot-list/star", json={"symbol": "AISP"}, headers=key)
    assert locked.status_code == 409 and locked.json()["detail"]["reason"] == "HOT_LIST_UNREADABLE"
    assert "schema_version 7" in client.get("/api/hot-list").json()["error"]


def test_settings_change_the_feed_and_the_default(key):
    body = client.patch("/api/hot-list", json={"auto_n": 10, "default_buy": "nova"}, headers=key).json()
    assert body["auto"]["n"] == 10 and "top 10" in body["auto"]["rule"]
    assert body["default"] == {"buy": "nova", "sell": "you"}
    assert client.patch("/api/hot-list", json={"auto_n": 0}, headers=key).json()["auto"]["n"] == 0
    [line] = [r for r in list_entries(limit=20) if r["action"] == "hot_list"][:1]
    assert line["inputs"]["event"] == "settings"


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


# -- a new name's default --------------------------------------------------------------------------
def test_a_new_name_takes_the_default_where_the_venue_allows_nova(key):
    on_practice("paper")
    client.patch("/api/hot-list", json={"default_buy": "nova", "default_sell": "you"}, headers=key)
    client.post("/api/hot-list/star", json={"symbol": "XYZ"}, headers=key)
    assert mode_of("XYZ", key)["mode"] == "auto_entry"
    [applied] = [r["inputs"] for r in list_entries(limit=50) if r["inputs"].get("event") == "default"]
    assert applied["applied"] is True and applied["symbol"] == "XYZ"


def test_on_live_a_new_name_stays_you_you_and_its_view_says_so(key):
    client.patch("/api/hot-list", json={"default_buy": "nova"}, headers=key)        # the desk is on Live
    client.post("/api/hot-list/star", json={"symbol": "XYZ"}, headers=key)
    view = mode_of("XYZ", key)
    assert view["mode"] == "signal"
    [note] = [n for n in view["notes"] if n["id"] == "hot_list_default"]
    assert "today's hot list" in note["text"] and "You · You" in note["text"]
    [skipped] = [r["inputs"] for r in list_entries(limit=50) if r["inputs"].get("event") == "default"]
    assert skipped["applied"] is False and "Live" in skipped["why"]


def test_a_stock_with_its_own_switch_keeps_it(key):
    on_practice("paper")
    assert client.put("/api/stock-mode/XYZ", json={"buy": "you", "sell": "nova"}, headers=key).status_code == 200
    client.patch("/api/hot-list", json={"default_buy": "nova", "default_sell": "nova"}, headers=key)
    client.post("/api/hot-list/star", json={"symbol": "XYZ"}, headers=key)
    assert mode_of("XYZ", key)["mode"] == "approve"


# -- Buy to Nova stars the stock -------------------------------------------------------------------
def test_buy_to_nova_stars_an_unlisted_stock(key):
    on_practice("paper")
    res = client.put("/api/stock-mode/AISP", json={"buy": "nova", "sell": "nova"}, headers=key)
    assert res.status_code == 200 and res.json()["mode"] == "bot"
    assert hot_list.is_listed("AISP")
    [star] = [r["inputs"] for r in list_entries(limit=50) if r["inputs"].get("event") == "star"]
    assert star == {"event": "star", "symbol": "AISP", "by": "nova_buy"}
    assert client.put("/api/stock-mode/LGHL", json={"buy": "you", "sell": "nova"}, headers=key).status_code == 200
    assert not hot_list.is_listed("LGHL")                                          # Buy You stars nothing


def test_a_full_list_refuses_buy_to_nova_before_anything_changes(key):
    on_practice("paper")
    fill(HOT_LIST_CAP)
    res = client.put("/api/stock-mode/AISP", json={"buy": "nova", "sell": "you"}, headers=key)
    assert res.status_code == 409 and res.json()["detail"]["reason"] == "HOT_LIST_FULL"
    assert mode_of("AISP", key)["mode"] == "signal" and "AISP" not in load_session()["symbol_allowlist"]
    assert [r for r in list_entries(limit=20) if r["action"] == "stock_mode"] == []


def test_the_bot_list_route_stars_too(key):
    on_practice("paper")
    res = client.post("/api/bot/allowlist", json={"symbol": "abcd", "op": "add"}, headers=key)
    assert res.status_code == 200 and hot_list.is_listed("ABCD")


# -- removing a stock ------------------------------------------------------------------------------
def test_removing_a_stock_is_you_you_on_every_venue(key):
    on_practice("paper")
    assert client.put("/api/stock-mode/AISP", json={"buy": "nova", "sell": "nova"}, headers=key).status_code == 200
    row = load_session()
    row["venue_levels"] = {**(row.get("venue_levels") or {}), "sim": {"level": 0, "symbol_allowlist": ["AISP", "KEEP"]}}
    save_session(row)
    res = client.delete("/api/hot-list/aisp", headers=key)
    assert res.status_code == 200 and res.json()["entries"] == []
    row = load_session()
    assert "AISP" not in row["symbol_allowlist"] and row["venue_levels"]["sim"]["symbol_allowlist"] == ["KEEP"]
    assert mode_of("AISP", key)["mode"] == "signal" and not hot_list.is_listed("AISP")
    assert [r["inputs"]["event"] for r in list_entries(limit=50) if r["action"] == "hot_list"][-1] == "remove"


def test_removing_is_refused_while_nova_trades_the_stock(key):
    on_practice("paper")
    client.post("/api/hot-list/star", json={"symbol": "AISP"}, headers=key)
    trade = {"venue": "sim", "symbol": "AISP", "kind": "approve", "state": "holding", "exits": "nova",
             "sent_at": time.time()}
    stock_store.set_trade(trade)
    res = client.delete("/api/hot-list/AISP", headers=key)
    assert res.status_code == 409 and res.json()["detail"]["reason"] == "HOT_LIST_NOVA_TRADE"
    assert "sim" in res.json()["detail"]["error"] and hot_list.is_listed("AISP")
    stock_store.set_trade({**trade, "state": "closed", "closed_at": time.time()})
    row = load_session()
    row["trade"] = {"symbol": "AISP", "state": "open", "venue": "paper", "setup_id": "x"}
    save_session(row)
    bot = client.delete("/api/hot-list/AISP", headers=key)
    assert bot.status_code == 409 and "bot" in bot.json()["detail"]["error"]
    row["trade"] = {**row["trade"], "state": "closed"}
    save_session(row)
    assert client.delete("/api/hot-list/AISP", headers=key).status_code == 200
