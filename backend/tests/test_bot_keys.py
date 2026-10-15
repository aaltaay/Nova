"""The three keys (operator decisions 2026-10-15; bot.md, "The three keys"): the Bot switch in the header, a key per
bot family per venue, and each bot's own key. A bot acts only while all three are on; with any off it places no order,
not even a sell, and what it holds waits -- while what rests at the broker still fills and your own orders, a cover
included, always go through. The strategy bot runs the real execution door and practice broker (fixtures from
``test_bot_first_pullback``); the Live Trader bot's end-to-end cases are in ``test_live_trader_watcher``.
"""
from __future__ import annotations

import json

import pytest

from bot import family_keys, switch
from bot.audit import list_entries
from bot.autonomy import apply_patch
from bot.errors import BotError
from bot.first_pullback import runner
from bot.persist import load_session
from bot.session import get_session
from constants_bot import (
    BOT_FP_TIME_STOP_MIN,
    BOT_KEYS_FILENAME,
    BOT_REASON_KEY_UNKNOWN,
    BOT_REASON_KEYS_UNREADABLE,
    BOT_REASON_LIVE_NOT_BUILT,
    BOT_SKIP_FAMILY_OFF,
    BOT_SKIP_NOT_ACTIVE,
    BOT_SKIP_SETUP_NOT_STRATEGY,
)
from paths import cache_dir
from sim.mode import set_venue
from tests.bot_helpers import headers
from tests.test_bot_first_pullback import NOW, SYM, api_key, client, leg, paper, tick, trade_rows, trigger  # noqa: F401


def key_lines() -> list[dict]:
    return [r for r in list_entries(limit=50) if r["action"] == "bot_key"]


# -- the file ----------------------------------------------------------------------------------------
def test_a_key_the_file_does_not_hold_reads_on_and_each_venue_keeps_its_own():
    set_venue("paper")
    assert family_keys.is_on("strategy") and family_keys.is_on("live_trader")
    assert family_keys.turn("strategy", False) is True
    raw = json.loads((cache_dir() / BOT_KEYS_FILENAME).read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1 and raw["venues"]["paper"]["strategy"] is False
    family_keys.reset_for_tests()                                   # a restart keeps it: a key is a setting
    assert not family_keys.is_on("strategy", "paper") and family_keys.is_on("live_trader", "paper")
    assert family_keys.is_on("strategy", "sim")                     # Sim keeps its own
    set_venue("sim")
    assert family_keys.is_on("strategy")


def test_pressing_a_key_into_its_own_state_writes_nothing():
    set_venue("paper")
    assert family_keys.turn("live_trader", True) is False
    assert key_lines() == [] and not (cache_dir() / BOT_KEYS_FILENAME).exists()
    family_keys.turn("live_trader", False)
    (line,) = key_lines()
    assert line["outcome"] == "off" and line["inputs"] == {"family": "live_trader", "venue": "paper", "on": False}
    assert "not even a sell" in line["reason"]


def test_live_has_no_family_keys_and_an_unknown_family_is_refused():
    set_venue("live")
    assert family_keys.state("strategy") == (False, family_keys._LIVE_WHY)
    with pytest.raises(BotError) as live:
        family_keys.turn("strategy", True)
    assert live.value.reason == BOT_REASON_LIVE_NOT_BUILT
    set_venue("paper")
    with pytest.raises(BotError) as unknown:
        family_keys.turn("crypto", False)
    assert unknown.value.reason == BOT_REASON_KEY_UNKNOWN


@pytest.mark.parametrize("body", ['{"schema_version": 9, "venues": {}}', "not json"])
def test_an_unknown_or_unreadable_file_reads_every_key_off_and_refuses_writes(body):
    set_venue("paper")
    path = cache_dir() / BOT_KEYS_FILENAME
    path.write_text(body, encoding="utf-8")
    family_keys.reset_for_tests()
    on, why = family_keys.state("strategy")
    assert on is False and BOT_KEYS_FILENAME in why
    with pytest.raises(BotError) as refused:
        family_keys.turn("strategy", True)
    assert refused.value.reason == BOT_REASON_KEYS_UNREADABLE
    assert path.read_text(encoding="utf-8") == body                 # never overwritten


def test_the_route_turns_a_key_and_answers_the_session(api_key):  # noqa: F811
    set_venue("paper")
    got = client.post("/api/bot/session/keys", json={"family": "strategy", "on": False}, headers=headers(api_key))
    assert got.status_code == 200, got.text
    keys = got.json()["keys"]
    assert keys["venue"] == "paper" and keys["strategy"]["on"] is False and keys["live_trader"]["on"] is True
    assert "Strategy Bots" in keys["strategy"]["why_off"]
    gate = next(g for g in got.json()["gates"] if g["id"] == "strategy_key")
    assert gate["ok"] is False and "Strategy Bots key is off" in gate["detail"]["text"]
    bad = client.post("/api/bot/session/keys", json={"family": "nope", "on": True}, headers=headers(api_key))
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == BOT_REASON_KEY_UNKNOWN


# -- the strategy bot: all three on, or no order ---------------------------------------------------
def _set(paper, *, switch_on: bool, family_on: bool, own_on: bool) -> None:  # noqa: F811
    apply_patch({"setup_levels": {"first_pullback": 2 if own_on else 1}}, desk=True)
    family_keys.turn("strategy", family_on)
    if not switch_on:
        switch.turn(False)


@pytest.mark.parametrize("switch_on", [True, False])
@pytest.mark.parametrize("family_on", [True, False])
@pytest.mark.parametrize("own_on", [True, False])
def test_the_strategy_bot_buys_only_with_all_three_keys_on(paper, switch_on, family_on, own_on):  # noqa: F811
    _set(paper, switch_on=switch_on, family_on=family_on, own_on=own_on)
    runner.submit(trigger())
    trade = tick(paper)
    bought = trade is not None and trade.get("state") == "open"
    assert bought == (switch_on and family_on and own_on)
    if not bought:
        (skip,) = trade_rows("skipped")
        codes = set(skip["inputs"]["codes"])
        assert (BOT_SKIP_NOT_ACTIVE in codes) == (not switch_on)
        assert (BOT_SKIP_FAMILY_OFF in codes) == (not family_on)
        # the switch off also puts the master at Eyes (ADR 044), so every strategy reads below Strategy then
        assert (BOT_SKIP_SETUP_NOT_STRATEGY in codes) == (not own_on or not switch_on)
        assert paper.broker.ledger.held_qty(SYM) == 0.0


@pytest.mark.parametrize("off", ["switch", "family"])
def test_with_a_key_off_the_bot_sends_no_exit_but_the_brokers_stop_still_fills(paper, off):  # noqa: F811
    runner.submit(trigger())
    trade = tick(paper)
    legs = trade["target_order_id"], trade["stop_order_id"]
    if off == "switch":
        switch.turn(False)
    else:
        family_keys.turn("strategy", False)
    trade = tick(paper, NOW + BOT_FP_TIME_STOP_MIN * 60 + 1)          # past the time stop: no sell
    trade = tick(paper, NOW + BOT_FP_TIME_STOP_MIN * 60 + 2)
    assert trade["state"] == "open" and paper.broker.ledger.held_qty(SYM) == 1.0
    assert {leg(paper, oid)["status"] for oid in legs} == {"Submitted"}  # its bracket rests untouched
    said = [r for r in trade_rows("note") if "places no order" in r["reason"] or "place no order" in r["reason"]]
    assert len(said) == 1                                              # said once
    paper.broker.try_fill_working(SYM, [(NOW + 950, 9.85)])
    trade = tick(paper, NOW + 951)                                     # the broker's own stop is read
    assert trade["state"] == "closed" and trade["exit_reason"] == "stop"


def test_the_strategy_turned_off_holds_its_own_trade_too(paper):  # noqa: F811
    """A strategy's own level is its trade's third key: below On, the trade places no order (Codex review, #1006)."""
    runner.submit(trigger())
    tick(paper)
    apply_patch({"setup_levels": {"first_pullback": 1}}, desk=True)
    trade = tick(paper, NOW + BOT_FP_TIME_STOP_MIN * 60 + 1)
    assert trade["state"] == "open" and paper.broker.ledger.held_qty(SYM) == 1.0
    (said,) = [r for r in trade_rows("note") if "is not On" in r["reason"]]
    assert said["inputs"]["code"] == "BOT_SETUP_NOT_STRATEGY"
    apply_patch({"setup_levels": {"first_pullback": 2}}, desk=True)
    trade = tick(paper, NOW + BOT_FP_TIME_STOP_MIN * 60 + 2)
    assert trade["state"] == "exiting" and trade["exit_why"] == "time"


def test_the_keys_back_on_the_held_exit_goes(paper):  # noqa: F811
    runner.submit(trigger())
    tick(paper)
    family_keys.turn("strategy", False)
    assert tick(paper, NOW + BOT_FP_TIME_STOP_MIN * 60 + 1)["state"] == "open"
    family_keys.turn("strategy", True)
    trade = tick(paper, NOW + BOT_FP_TIME_STOP_MIN * 60 + 2)
    assert trade["state"] == "exiting" and trade["exit_why"] == "time"


def test_with_every_key_off_your_own_close_goes_through_and_the_bot_takes_back_its_legs(paper):  # noqa: F811
    runner.submit(trigger())
    trade = tick(paper)
    family_keys.turn("strategy", False)
    switch.turn(False)
    paper.broker.cancel(trade["target_order_id"])
    paper.broker.place(SYM, "SELL", 1, "MKT")                          # yours: no key stands in your way
    tick(paper, NOW + 2)
    trade = tick(paper, NOW + 3)
    assert trade["state"] == "closed" and trade["exit_reason"] == "outside"
    assert paper.broker.ledger.working_orders() == []                 # its stop leg cancelled: a cancel sends nothing
    assert paper.broker.ledger.held_qty(SYM) == 0.0


def test_the_squares_and_the_session_say_the_strategy_key(paper):  # noqa: F811
    from bot.trigger_cells import _bot_on

    family_keys.turn("strategy", False)
    view = get_session()
    assert view["keys"]["strategy"]["on"] is False and view["bot_on"] is True     # the switch itself is still on
    assert runner.playing(load_session())[0] is False
    assert _bot_on({"level": 2, "active": True, "venue": "paper", "strategy_key": False})["ok"] is False
    assert _bot_on({"level": 2, "active": True, "venue": "paper"})["ok"] is True  # an older line: the switch alone
