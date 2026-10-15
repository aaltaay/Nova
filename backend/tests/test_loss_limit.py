"""The daily loss limit (ADR 056): what it counts, its setting, its 10-second wait, its trip and Auto sell."""
from __future__ import annotations

import asyncio
import json

import pytest

from loss_limit import gate, settings, state, watch
from loss_limit.count import Count, Fill, Held, count

NOW = 1_792_071_138.0          # 2026-10-15 09:32:18 ET


@pytest.fixture(autouse=True)
def _fresh():
    settings.reset_for_tests()
    state.reset_for_tests()
    watch.reset_for_tests()
    yield
    settings.reset_for_tests()
    state.reset_for_tests()
    watch.reset_for_tests()


# -- what it counts ---------------------------------------------------------------------------------
def test_weto_the_trade_opened_today_counts_cash_mark_and_commissions():
    fills = [Fill("WETO", 5000, 1.45, 25.015), Fill("WETO", 5000, 1.45, 25.015)]
    got = count(fills, {"WETO": Held(10_000, 1.4099)})
    assert got.pnl == pytest.approx(-451.03, abs=0.01)
    assert got.loss == pytest.approx(451.03, abs=0.01)
    assert got.opened_today() == [{"symbol": "WETO", "pnl": pytest.approx(-451.03, abs=0.01), "shares": 10_000}]


def test_a_stock_held_before_today_never_counts_even_when_traded_today():
    fills = [Fill("AAPL", 10, 150.0, 1.0)]                       # bought 10 more today
    got = count(fills, {"AAPL": Held(110, 100.0)})               # held 100 since long ago
    assert got.pnl == 0 and got.held_before == ["AAPL"] and got.stocks == []
    assert count([], {"AAPL": Held(100, 50.0)}).pnl == 0         # no trade today: nothing at all


def test_a_closed_round_trip_and_a_short():
    fills = [Fill("A", 100, 2.0, 1.0), Fill("A", -100, 1.5, 1.0),        # long, closed: -50 - 2
             Fill("B", -200, 5.0, 1.0)]                                    # short 200 at 5, now 5.10: -20 - 1
    got = count(fills, {"B": Held(-200, 5.10)})
    assert got.pnl == pytest.approx(-52.0 - 21.0)
    assert [s["symbol"] for s in got.opened_today()] == ["B"]


def test_an_open_position_without_a_mark_is_unknown_and_an_unknown_commission_still_counts():
    assert count([Fill("X", 10, 1.0, 0.1)], {"X": Held(10, None)}).pnl is None
    assert "X" in (count([Fill("X", 10, 1.0, 0.1)], {"X": Held(10, None)}).unknown or "")
    got = count([Fill("X", 10, 1.0, None), Fill("X", -10, 0.9, None)], {})
    assert got.pnl == pytest.approx(-1.0) and got.costs_unknown == 2


# -- the setting ----------------------------------------------------------------------------------------
def test_defaults_then_a_saved_change_and_the_rules():
    assert settings.current() == {"limit_usd": 2000, "warn": True, "no_new_buys": True, "auto_sell": False,
                                  "set_at": None, "source": "default", "error": None}
    before, after = settings.update({"limit_usd": 405, "auto_sell": True}, now=NOW)
    assert before["limit_usd"] == 2000 and after["limit_usd"] == 405 and after["auto_sell"] is True
    doc = json.loads(settings.path().read_text(encoding="utf-8"))
    assert doc == {"schema_version": 1, "limit_usd": 405, "warn": True, "no_new_buys": True, "auto_sell": True,
                   "set_at": NOW}
    for bad in ({"limit_usd": 9}, {"limit_usd": 10.5}, {"limit_usd": "x"}, {"limit_usd": 1_000_001},
                {"warn": "yes"}, {"breakers": 1}, {}):
        with pytest.raises(settings.Invalid):
            settings.update(bad)
    assert settings.current()["limit_usd"] == 405                  # a refusal changes nothing


def test_an_unknown_version_reads_the_defaults_and_says_so():
    settings.path().parent.mkdir(parents=True, exist_ok=True)
    settings.path().write_text(json.dumps({"schema_version": 9, "limit_usd": 5}), encoding="utf-8")
    current = settings.current()
    assert current["limit_usd"] == 2000 and current["source"] == "default" and "version 9" in current["error"]


# -- the watcher -----------------------------------------------------------------------------------
def _closes(stocks, on_close, order_id: int = 7) -> list:
    """What a fake sale answers, told close by close as ``sell_opened_today`` does."""
    out = []
    for s in stocks:
        close = {"symbol": s["symbol"], "side": "SELL", "qty": s["shares"], "ok": True, "order_id": order_id,
                 "error": None}
        out.append(close)
        if on_close is not None:
            on_close(close)
    return out


def _run(account: str, pnl: float | None, at: float, stocks=None):
    got = Count(pnl=pnl, unknown=None if pnl is not None else "unknown", stocks=stocks or [])
    asyncio.run(watch.check(account, got, at))


def test_a_line_acts_only_after_ten_seconds_past_it_and_only_once():
    settings.update({"limit_usd": 1000})
    _run("paper", -1200, NOW)
    _run("paper", -1200, NOW + 9)
    assert not state.record("paper", NOW + 9).get("tripped_at")            # 9 s: nothing yet
    _run("paper", -1200, NOW + 10)
    row = state.record("paper", NOW + 10)
    assert row["tripped_at"] == NOW + 10 and row["tripped_loss"] == 1200 and row["limit_usd"] == 1000
    assert row["warned_at"] == NOW + 10                                     # 80% held as long
    _run("paper", -1500, NOW + 20)
    assert state.record("paper", NOW + 20)["tripped_loss"] == 1200          # once a day


def test_a_blip_or_an_unknown_starts_the_wait_again():
    settings.update({"limit_usd": 1000})
    _run("paper", -1200, NOW)
    _run("paper", -900, NOW + 5)                                            # back under: wait restarts
    _run("paper", -1200, NOW + 6)
    _run("paper", -1200, NOW + 15)
    assert not state.record("paper", NOW + 15).get("tripped_at")
    _run("paper", None, NOW + 16)                                           # unknown: restarts too
    _run("paper", -1200, NOW + 17)
    _run("paper", -1200, NOW + 26)
    assert not state.record("paper", NOW + 26).get("tripped_at")
    _run("paper", -1200, NOW + 27)
    assert state.record("paper", NOW + 27)["tripped_at"] == NOW + 27


def test_warn_me_off_writes_no_warning_but_the_trip_still_records():
    settings.update({"limit_usd": 1000, "warn": False})
    for t in (0, 10):
        _run("paper", -1100, NOW + t)
    row = state.record("paper", NOW + 10)
    assert "warned_at" not in row and row["tripped_at"] == NOW + 10


def test_auto_sell_off_sells_nothing_and_on_sells_only_todays(monkeypatch):
    sold: list = []

    async def fake_sell(account, stocks, on_close=None):
        sold.append((account, stocks))
        return _closes(stocks, on_close)

    monkeypatch.setattr("loss_limit.sell.sell_opened_today", fake_sell)
    stocks = [{"symbol": "WETO", "pnl": -451.03, "shares": 10_000.0}, {"symbol": "DONE", "pnl": -5.0, "shares": 0.0}]
    settings.update({"limit_usd": 405})
    for t in (0, 10):
        _run("paper", -451.03, NOW + t, stocks)
    assert sold == []                                                       # Auto sell is off by default
    settings.update({"auto_sell": True})
    state.clear()
    watch.reset_waits()
    for t in (20, 30):
        _run("paper", -451.03, NOW + t, stocks)
    assert sold == [("paper", [stocks[0]])]                                  # only what is still held
    assert state.record("paper", NOW + 30)["sold"][0]["symbol"] == "WETO"


def test_an_auto_sell_a_restart_interrupted_resumes_once(monkeypatch):
    """PR #1003 review: the trip is saved as selling before any order goes out; the next pass finishes it."""
    sold: list = []

    async def fake_sell(account, stocks, on_close=None):
        sold.append([s["symbol"] for s in stocks])
        return _closes(stocks, on_close, 9)

    monkeypatch.setattr("loss_limit.sell.sell_opened_today", fake_sell)
    settings.update({"limit_usd": 405, "auto_sell": True})
    # What a restart mid-sale leaves: the trip, marked selling, and nothing sold.
    state.write("paper", {"tripped_at": NOW, "tripped_loss": 451.03, "limit_usd": 405, "sell": "pending"}, NOW)
    stocks = [{"symbol": "WETO", "pnl": -451.03, "shares": 10_000.0}]
    _run("paper", None, NOW + 1, stocks)                                     # an account it cannot count: waits
    assert sold == []
    _run("paper", -451.03, NOW + 2, stocks)
    assert sold == [["WETO"]]
    row = state.record("paper", NOW + 2)
    assert row["sell"] == "done" and row["sold"][0]["symbol"] == "WETO" and row["tripped_at"] == NOW
    _run("paper", -451.03, NOW + 3, stocks)
    assert sold == [["WETO"]]                                                # done: never sold twice


def test_a_close_sent_before_a_restart_stays_in_sold(monkeypatch):
    """PR #1004 review: each close is saved as it answers, so a restart after the first of two keeps it."""
    settings.update({"limit_usd": 405, "auto_sell": True})
    two = [{"symbol": "WETO", "pnl": -300.0, "shares": 10_000.0}, {"symbol": "AMC", "pnl": -151.0, "shares": 500.0}]

    async def dies_after_the_first(account, stocks, on_close=None):
        _closes(stocks[:1], on_close, 259)
        raise SystemExit("the process stopped")                     # a restart, mid-sale

    monkeypatch.setattr("loss_limit.sell.sell_opened_today", dies_after_the_first)
    with pytest.raises(SystemExit):
        for t in (0, 10):
            _run("paper", -451.0, NOW + t, two)
    row = state.record("paper", NOW + 10)
    assert row["sell"] == "pending" and [c["symbol"] for c in row["sold"]] == ["WETO"]
    watch.reset_for_tests()                                          # the new process
    resumed: list = []

    async def finishes(account, stocks, on_close=None):
        resumed.append([s["symbol"] for s in stocks])
        return _closes(stocks, on_close, 260)

    monkeypatch.setattr("loss_limit.sell.sell_opened_today", finishes)
    _run("paper", -451.0, NOW + 20, two[1:])                         # WETO is no longer held
    row = state.record("paper", NOW + 20)
    assert resumed == [["AMC"]] and row["sell"] == "done"
    assert [(c["symbol"], c["order_id"]) for c in row["sold"]] == [("WETO", 259), ("AMC", 260)]


def test_a_trip_with_auto_sell_is_saved_as_selling_before_any_order(monkeypatch):
    seen: list = []

    async def fake_sell(account, stocks, on_close=None):
        seen.append(state.record(account, NOW + 10).get("sell"))
        return []

    monkeypatch.setattr("loss_limit.sell.sell_opened_today", fake_sell)
    settings.update({"limit_usd": 405, "auto_sell": True})
    for t in (0, 10):
        _run("paper", -451.03, NOW + t, [{"symbol": "WETO", "pnl": -451.03, "shares": 10_000.0}])
    assert seen == ["pending"] and state.record("paper", NOW + 10)["sell"] == "done"


def test_a_setting_change_clears_todays_trip_so_buys_open_again():
    settings.update({"limit_usd": 405})
    for t in (0, 10):
        _run("paper", -451.03, NOW + t)
    assert gate.buys_stopped("paper", NOW + 10)
    assert not gate.buys_stopped("live", NOW + 10)                          # each account its own
    settings.update({"limit_usd": 1000})
    state.clear()
    assert not gate.buys_stopped("paper", NOW + 11)


def test_the_refusal_covers_opens_only():
    settings.update({"limit_usd": 405})
    state.write("paper", {"tripped_at": NOW, "tripped_loss": 451.03, "limit_usd": 405})
    assert gate.buy_refusal("BUY", "manual", "paper")["code"] == "LOSS_LIMIT_NO_NEW_BUYS"
    assert gate.buy_refusal("BUY", "bot", "paper") is not None
    assert gate.buy_refusal("SELL", "manual", "paper", short_entry=True) is not None
    assert gate.buy_refusal("SELL", "manual", "paper") is None              # selling what is held
    assert gate.buy_refusal("BUY", "manual", "paper", covers=True) is None  # covering a short
    assert gate.buy_refusal("BUY", "flatten", "paper") is None              # protective
    assert gate.buy_refusal("BUY", "manual", "live") is None


def test_the_state_file_is_today_only(monkeypatch):
    state.write("paper", {"tripped_at": NOW, "tripped_loss": 1.0, "limit_usd": 10}, NOW)
    state.reset_for_tests()                                                 # a restart reads the file again
    assert state.record("paper", NOW + 60)["tripped_at"] == NOW
    assert state.record("paper", NOW + 86_400) == {}                        # tomorrow: nothing


def test_auto_sell_cancels_then_closes_on_its_own_account(monkeypatch):
    from loss_limit import sell

    sent: list = []

    class Receipt:
        ok, order_id, error, reason_code = True, 259, None, None

    async def fake_execute(cmd, wait_ack=False):
        sent.append(cmd)
        return Receipt()

    monkeypatch.setattr("execution.service.execute", fake_execute)
    monkeypatch.setattr(sell, "_working", lambda account, symbols: [{"symbol": "WETO", "order_id": 40}])
    monkeypatch.setattr("sim.mode.venue", lambda: "sim")              # the desk shows another account
    out = asyncio.run(sell.sell_opened_today("paper", [{"symbol": "WETO", "pnl": -451.0, "shares": 10_000.0}]))
    cancel, close = sent
    assert (cancel.operation, cancel.source, cancel.order_id, cancel.target_venue, cancel.origin) == (
        "cancel", "cancel_working", 40, "paper", "loss_limit")
    assert (close.operation, close.source, close.side, close.qty, close.order_type) == (
        "place", "flatten", "SELL", 10_000.0, "MKT")
    assert (close.target_venue, close.origin, close.intent) == ("paper", "loss_limit", None)
    assert out == [{"symbol": "WETO", "side": "SELL", "qty": 10_000.0, "ok": True, "order_id": 259, "error": None}]
    sent.clear()
    monkeypatch.setattr("sim.mode.venue", lambda: "paper")            # the desk shows it: the door checks it
    asyncio.run(sell.sell_opened_today("paper", [{"symbol": "B", "pnl": -5.0, "shares": -100.0}]))
    assert sent[-1].side == "BUY" and sent[-1].intent == "flatten"


def test_the_venue_door_lets_auto_sell_name_its_account_and_live_only_as_a_flatten(monkeypatch):
    from execution import venue_door
    from execution.models import ExecutionCommand

    def close(target, intent):
        return ExecutionCommand(operation="place", idempotency_key="k", source="flatten", symbol="A", side="SELL",
                                qty=1, order_type="MKT", target_venue=target, origin="loss_limit", intent=intent)

    assert venue_door.target_refusal(close("paper", None)) is None
    monkeypatch.setattr(venue_door, "ibkr_connected", lambda: True)
    monkeypatch.setattr(venue_door, "live_session_refusal", lambda: None)
    assert venue_door.target_refusal(close("live", "flatten")) is None
    assert "intent flatten" in venue_door.target_refusal(close("live", None))
    buy = ExecutionCommand(operation="place", idempotency_key="k", source="manual", symbol="A", side="BUY", qty=1,
                           order_type="MKT", target_venue="paper", origin="loss_limit")
    assert venue_door.target_refusal(buy) is not None                  # only closes may name an account


# -- the wire --------------------------------------------------------------------------------------
@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from loss_limit.routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_and_put(client):
    got = client.get("/api/loss-limit").json()
    assert got["settings"]["limit_usd"] == 2000 and set(got["accounts"]) == {"live", "paper", "sim"}
    bad = client.put("/api/loss-limit", json={"limit_usd": 5})
    assert bad.status_code == 400 and "between $10" in bad.json()["detail"]
    state.write("paper", {"tripped_at": NOW, "tripped_loss": 451.03, "limit_usd": 405})
    ok = client.put("/api/loss-limit", json={"limit_usd": 3000, "auto_sell": True}).json()
    assert ok["settings"]["limit_usd"] == 3000 and ok["settings"]["auto_sell"] is True
    assert ok["accounts"]["paper"]["tripped_at"] is None                    # the change cleared today's trip
