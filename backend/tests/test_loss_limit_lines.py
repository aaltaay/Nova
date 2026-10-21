"""The daily loss limit's three lines (ADR 061): the split count, each line's trip, and the migration."""
from __future__ import annotations

import asyncio
import json

import pytest

from loss_limit import gate, settings, state, watch
from loss_limit.accounts import by_of
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


def _by(got: Count, symbol: str, side: str) -> dict:
    return next(s for s in got.stocks if s["symbol"] == symbol)["by"][side]


# -- whose fill: the order's own stamps ------------------------------------------------------------
def test_whose_order_reads_the_rows_own_source_bot_id_and_origin():
    assert by_of({"order_source": "manual"}) == "you"
    assert by_of({"order_source": "manual", "order_origin": "approve"}) == "you"       # you approved it
    assert by_of({"order_source": "manual", "order_origin": "nova_exit"}) == "you"     # your shares' exit
    assert by_of({"order_source": "bot", "order_origin": "auto_entry"}) == "bots"
    assert by_of({"order_source": "manual", "bot_id": "fp-1"}) == "bots"               # the bot audit's rule
    assert by_of({"order_source": "flatten", "order_origin": "live_trader"}) == "bots"  # a bot's own close
    assert by_of({"order_source": "flatten", "order_origin": "bot"}) == "bots"
    assert by_of({"order_source": "flatten", "order_origin": "ticket_flatten"}) == "you"
    assert by_of({"order_source": "flatten", "order_origin": "loss_limit_bots"}) == "bots"
    assert by_of({"order_source": "flatten", "order_origin": "loss_limit_you"}) == "you"
    for nova in ("loss_limit", "day_cover", "margin_call", None):
        assert by_of({"order_source": "flatten", "order_origin": nova}) is None
    assert by_of({"order_source": "kill", "order_origin": "emergency_kill"}) is None


# -- the split count --------------------------------------------------------------------------------
def test_each_side_counts_its_own_stocks_and_the_two_add_up_to_the_account():
    fills = [Fill("A", 100, 10.0, 1.0, "you", 1), Fill("A", -100, 9.0, 1.0, "you", 2),     # yours: -100 - 2
             Fill("B", 200, 5.0, 1.0, "bots", 3)]                                         # the bots': open
    got = count(fills, {"B": Held(200, 4.5)})                                             # -100 - 1
    assert got.pnl_of("you") == -102.0 and got.pnl_of("bots") == -101.0
    assert got.pnl == -203.0 == got.pnl_of("you") + got.pnl_of("bots")
    assert got.loss_of("bots") == 101.0 and got.loss_of("account") == 203.0
    assert got.opened_today("bots") == [{"symbol": "B", "pnl": -101.0, "shares": 200.0}]
    assert got.opened_today("you") == []


def test_a_bots_close_takes_the_bots_shares_first_when_you_hold_the_same_stock():
    fills = [Fill("X", 100, 2.0, 0.0, "bots", 1), Fill("X", 200, 2.1, 0.0, "you", 2),
             Fill("X", -100, 2.5, 0.0, "bots", 3)]                                        # the bot's stop / target
    got = count(fills, {"X": Held(200, 2.0)})
    assert _by(got, "X", "bots") == {"pnl": 50.0, "shares": 0.0}                          # +0.50 on 100
    assert _by(got, "X", "you") == {"pnl": -20.0, "shares": 200.0}                        # 200 at 2.10, now 2.00
    assert got.opened_today("you") == [{"symbol": "X", "pnl": -20.0, "shares": 200.0}]
    assert got.opened_today("bots") == []


def test_whoever_opened_it_owns_the_trade_you_closing_the_bots_shares_counts_on_the_bots():
    fills = [Fill("Y", 300, 4.0, 1.5, "bots", 1),
             Fill("Y", -300, 3.0, 1.5, "you", 2)]       # you sold the bot's shares by hand: you held none
    got = count(fills, {})
    assert got.pnl_of("bots") == -303.0 and got.pnl_of("you") == 0.0                      # the close's cost too


def test_novas_own_close_takes_from_each_side_in_proportion():
    fills = [Fill("Z", 100, 1.0, 0.0, "you", 1), Fill("Z", 300, 1.0, 0.0, "bots", 2),
             Fill("Z", -200, 0.5, 4.0, None, 3)]                                          # KILL, half of it
    got = count(fills, {"Z": Held(200, 0.5)})
    assert _by(got, "Z", "you")["shares"] == 50.0 and _by(got, "Z", "bots")["shares"] == 150.0
    assert got.pnl_of("you") == -51.0 and got.pnl_of("bots") == -153.0                    # each 1/4, 3/4 of $4
    assert got.pnl == got.pnl_of("you") + got.pnl_of("bots")


def test_a_side_lines_auto_sell_gives_the_sold_shares_back_to_its_side():
    fills = [Fill("W", 100, 3.0, 0.0, "you", 1), Fill("W", 100, 3.0, 0.0, "bots", 2),
             Fill("W", -100, 2.0, 0.0, "bots", 3)]      # the Bots line's Auto sell (origin loss_limit_bots)
    got = count(fills, {"W": Held(100, 2.0)})
    assert _by(got, "W", "bots") == {"pnl": -100.0, "shares": 0.0}
    assert _by(got, "W", "you") == {"pnl": -100.0, "shares": 100.0}


def test_shorts_split_the_same_way_and_held_before_still_never_counts():
    fills = [Fill("S", -100, 5.0, 0.0, "bots", 1), Fill("S", 100, 5.2, 0.0, None, 2),    # the day cover
             Fill("OLD", 10, 1.0, 0.0, "bots", 3)]
    got = count(fills, {"OLD": Held(110, 1.0)})
    assert got.pnl_of("bots") == -20.0 and got.pnl_of("you") == 0.0 and got.held_before == ["OLD"]


def test_an_unknown_mark_makes_every_line_unknown():
    got = count([Fill("Q", 10, 1.0, 0.0, "bots", 1)], {"Q": Held(10, None)})
    assert got.pnl_of("bots") is None and got.loss_of("you") is None and got.loss is None


def test_the_sides_add_up_to_the_account_to_the_cent():
    """PR #1130 review: rounding each figure alone gave You -0.01 + Bots -0.01 beside an Account -0.03."""
    fills = [Fill("C", 1, 1.0, 0.0149, "you", 1), Fill("C", 1, 1.0, 0.0149, "bots", 2),
             Fill("D", 100, 1.0001, 0.005, "you", 3), Fill("D", 200, 1.0003, 0.005, "bots", 4),
             Fill("D", -300, 0.99995, 0.01, None, 5)]
    got = count(fills, {"C": Held(2, 1.0)})
    assert _by(got, "C", "you")["pnl"] == -0.01 and _by(got, "C", "bots")["pnl"] == -0.02    # C is -0.03
    assert round(got.pnl_of("you") + got.pnl_of("bots"), 2) == got.pnl
    for stock in got.stocks:
        assert round(stock["by"]["you"]["pnl"] + stock["by"]["bots"]["pnl"], 2) == stock["pnl"]


# -- each line's trip ---------------------------------------------------------------------------------
def _run(account: str, at: float, *, you: float, bots: float, stocks=None):
    got = Count(pnl=round(you + bots, 2), stocks=stocks or [], sides={"you": you, "bots": bots})
    asyncio.run(watch.check(account, got, at))


def _held(at: float) -> tuple[bool, bool]:
    return gate.buys_stopped("paper", at, actor="you"), gate.buys_stopped("paper", at, actor="bots")


def test_the_bots_line_stops_only_the_bots_and_the_account_line_stays_quiet():
    settings.update({"limit_usd": 2000, "you_usd": 300, "bots_usd": 500})
    for t in (0, 10):
        _run("paper", NOW + t, you=-50.0, bots=-510.0)          # a bot's normal losing day
    assert state.record("paper", NOW + 10, line="bots")["tripped_at"] == NOW + 10
    assert state.record("paper", NOW + 10, line="bots")["limit_usd"] == 500
    assert not state.record("paper", NOW + 10).get("tripped_at")               # the account is $560 down
    assert _held(NOW + 10) == (False, True)                                     # you still buy
    stop = gate.stopped("paper", NOW + 10, actor="bots")
    assert stop["line"] == "bots" and "The bots' daily loss limit reached on Paper" in stop["text"]
    assert "$510" in stop["text"] and "$500" in stop["text"] and "your own buys still work" in stop["text"]


def test_your_line_stops_only_you_and_its_warning_comes_first():
    settings.update({"you_usd": 300})
    for t in (0, 10):
        _run("paper", NOW + t, you=-250.0, bots=0.0)
    you = state.record("paper", NOW + 10, line="you")
    assert you["warned_at"] == NOW + 10 and you["warned_loss"] == 250.0 and not you.get("tripped_at")
    for t in (20, 30):
        _run("paper", NOW + t, you=-310.0, bots=+900.0)         # the bots' gain never hides your loss
    assert state.record("paper", NOW + 30, line="you")["tripped_at"] == NOW + 30
    assert _held(NOW + 30) == (True, False)
    text = gate.stopped("paper", NOW + 30, actor="you")["text"]
    assert text.startswith("Your trades' daily loss limit reached on Paper") and "the bots still trade" in text


def test_the_door_reads_the_side_from_the_orders_own_source():
    """The door asks with no clock: today's record, written now."""
    settings.update({"you_usd": 300, "bots_usd": 500})
    state.write("paper", {"tripped_at": NOW, "tripped_loss": 510.0, "limit_usd": 500}, line="bots")
    assert gate.buy_refusal("BUY", "bot", "paper")["code"] == "LOSS_LIMIT_NO_NEW_BUYS"
    assert gate.buy_refusal("SELL", "bot", "paper", short_entry=True) is not None   # a bot's new short
    assert gate.buy_refusal("BUY", "manual", "paper") is None                       # you still buy
    assert gate.buy_refusal("SELL", "bot", "paper") is None                         # a bot's own exit
    assert gate.buy_refusal("BUY", "bot", "paper", covers=True) is None             # a bot's cover
    state.clear()
    state.write("paper", {"tripped_at": NOW, "tripped_loss": 310.0, "limit_usd": 300}, line="you")
    assert gate.buy_refusal("BUY", "manual", "paper") is not None
    assert gate.buy_refusal("BUY", "bot", "paper") is None                          # the bots still trade


def test_the_account_line_still_stops_everyone():
    settings.update({"limit_usd": 500, "you_usd": 400, "bots_usd": 400})
    for t in (0, 10):
        _run("paper", NOW + t, you=-260.0, bots=-260.0)         # neither side at its own line
    assert _held(NOW + 10) == (True, True)
    assert gate.stopped("paper", NOW + 10, actor="bots")["line"] == "account"


def test_a_line_that_is_off_never_acts():
    settings.update({"limit_usd": 5000})
    for t in (0, 10):
        _run("paper", NOW + t, you=-4000.0, bots=-900.0)
    _day, records, _err = state.records(NOW + 10)
    assert set(records.get("paper", {})) == {"account"}                          # only the 80% warning
    assert _held(NOW + 10) == (False, False)


def test_the_bots_lines_auto_sell_sells_only_the_bots_shares(monkeypatch):
    sold: list = []

    async def fake_sell(account, stocks, on_close=None, *, line="account"):
        sold.append((account, line, stocks))
        return []

    monkeypatch.setattr("loss_limit.sell.sell_opened_today", fake_sell)
    settings.update({"bots_usd": 500, "auto_sell": True})
    stocks = [{"symbol": "X", "pnl": -560.0, "shares": 300.0,
               "by": {"you": {"pnl": -40.0, "shares": 200.0}, "bots": {"pnl": -520.0, "shares": 100.0}}}]
    for t in (0, 10):
        _run("paper", NOW + t, you=-40.0, bots=-520.0, stocks=stocks)
    assert sold == [("paper", "bots", [{"symbol": "X", "pnl": -520.0, "shares": 100.0}])]
    assert state.record("paper", NOW + 10, line="bots")["sell"] == "done"


def test_two_lines_tripping_in_one_pass_sell_one_at_a_time_from_a_fresh_count(monkeypatch):
    sold: list = []

    async def fake_sell(account, stocks, on_close=None, *, line="account"):
        sold.append((line, [s["shares"] for s in stocks]))
        return []

    monkeypatch.setattr("loss_limit.sell.sell_opened_today", fake_sell)
    settings.update({"limit_usd": 500, "bots_usd": 400, "auto_sell": True})
    stocks = [{"symbol": "X", "pnl": -600.0, "shares": 300.0,
               "by": {"you": {"pnl": -150.0, "shares": 200.0}, "bots": {"pnl": -450.0, "shares": 100.0}}}]
    for t in (0, 10):
        _run("paper", NOW + t, you=-150.0, bots=-450.0, stocks=stocks)
    assert sold == [("account", [300.0])]                                       # the Account line sold first
    assert state.record("paper", NOW + 10, line="bots")["sell"] == "pending"
    _run("paper", NOW + 11, you=-150.0, bots=-450.0)                            # next pass: nothing left
    assert sold[-1] == ("bots", []) and state.record("paper", NOW + 11, line="bots")["sell"] == "done"


# -- the setting and the record: the migration ------------------------------------------------------
def test_a_version_1_setting_reads_as_the_account_line_unchanged():
    settings.path().parent.mkdir(parents=True, exist_ok=True)
    settings.path().write_text(json.dumps({"schema_version": 1, "limit_usd": 405, "warn": False,
                                           "no_new_buys": True, "auto_sell": True, "set_at": NOW}),
                               encoding="utf-8")
    assert settings.current() == {"limit_usd": 405, "you_usd": None, "bots_usd": None, "warn": False,
                                  "no_new_buys": True, "auto_sell": True, "set_at": NOW, "source": "operator",
                                  "error": None}
    settings.update({"bots_usd": 300}, now=NOW + 1)                             # the next save writes version 2
    doc = json.loads(settings.path().read_text(encoding="utf-8"))
    assert doc["schema_version"] == 2 and doc["limit_usd"] == 405 and doc["bots_usd"] == 300
    assert doc["you_usd"] is None and doc["warn"] is False and doc["auto_sell"] is True


def test_a_version_1_record_keeps_todays_trip_on_the_account_line():
    state.path().parent.mkdir(parents=True, exist_ok=True)
    day = state.desk_day(NOW)[0]
    state.path().write_text(json.dumps({"schema_version": 1, "day": day, "accounts": {
        "paper": {"tripped_at": NOW, "tripped_loss": 451.03, "limit_usd": 405}}}), encoding="utf-8")
    assert state.record("paper", NOW + 5)["tripped_loss"] == 451.03
    assert state.record("paper", NOW + 5, line="bots") == {}
    assert _held(NOW + 5) == (True, True)                                       # the upgrade lifts no lock


def test_the_side_lines_rules():
    settings.update({"you_usd": 300, "bots_usd": 500})
    assert settings.current()["you_usd"] == 300 and settings.current()["bots_usd"] == 500
    settings.update({"you_usd": None})                                          # null turns a line off
    assert settings.current()["you_usd"] is None and settings.lines_on(settings.current()) == ["account", "bots"]
    for bad in ({"you_usd": 9}, {"bots_usd": 10.5}, {"bots_usd": "x"}, {"you_usd": True}, {"limit_usd": None}):
        with pytest.raises(settings.Invalid):
            settings.update(bad)


def test_saves_sent_together_each_keep_their_change(monkeypatch):
    """Two saves at once both read the same setting; one lock keeps each change (the order size limit's fix)."""
    import threading
    import time as _time

    from capture import manifest_io

    real = manifest_io.write_json_atomic

    def slow(path, doc):
        _time.sleep(0.05)
        real(path, doc)

    monkeypatch.setattr(manifest_io, "write_json_atomic", slow)
    saves = [{"you_usd": 300}, {"bots_usd": 500}, {"warn": False}]
    threads = [threading.Thread(target=settings.update, args=(patch,)) for patch in saves]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    settings.reset_for_tests()                                          # read back what the file holds
    got = settings.current()
    assert (got["you_usd"], got["bots_usd"], got["warn"]) == (300, 500, False)


# -- the venue door and the wire ----------------------------------------------------------------------
def test_the_venue_door_lets_your_line_sell_on_live_but_never_the_bots_line(monkeypatch):
    from execution import venue_door
    from execution.models import ExecutionCommand

    def close(origin):
        return ExecutionCommand(operation="place", idempotency_key="k", source="flatten", symbol="A", side="SELL",
                                qty=1, order_type="MKT", target_venue="live", origin=origin, intent="flatten")

    monkeypatch.setattr(venue_door, "ibkr_connected", lambda: True)
    monkeypatch.setattr(venue_door, "live_session_refusal", lambda: None)
    assert venue_door.target_refusal(close("loss_limit_you")) is None
    assert "never trades Live" in venue_door.target_refusal(close("loss_limit_bots"))
    paper = ExecutionCommand(operation="place", idempotency_key="k", source="flatten", symbol="A", side="SELL",
                             qty=1, order_type="MKT", target_venue="paper", origin="loss_limit_bots")
    assert venue_door.target_refusal(paper) is None


def test_the_wire_names_each_line(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from loss_limit.routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    got = client.put("/api/loss-limit", json={"bots_usd": 500}).json()
    assert got["schema_version"] == 2 and got["settings"]["bots_usd"] == 500 and got["settings"]["you_usd"] is None
    state.write("paper", {"tripped_at": NOW, "tripped_loss": 510.0, "limit_usd": 500}, line="bots")
    paper = client.get("/api/loss-limit").json()["accounts"]["paper"]
    assert set(paper["lines"]) == {"account", "you", "bots"}
    assert paper["lines"]["bots"]["on"] is True and paper["lines"]["you"]["on"] is False
    assert paper["lines"]["bots"]["tripped_loss"] == 510.0 and paper["lines"]["bots"]["no_new_buys"]["line"] == "bots"
    assert paper["no_new_buys"]["you"] is None and paper["no_new_buys"]["bots"]["line"] == "bots"
    bad = client.put("/api/loss-limit", json={"you_usd": 5})
    assert bad.status_code == 400 and "Your trades' limit" in bad.json()["detail"]
