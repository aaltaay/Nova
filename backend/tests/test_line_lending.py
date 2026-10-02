"""A hidden Trader tab lends its Level 2 line to a setup Nova may buy (ADR 043 decision 6).

Who lends (a Trader tab no visible window shows; never the tab in front, a Record hold or an
unknown focus), who borrows (a strategy at On, Buy is Nova, the bot active; armed, near or in a
trade), and how a loan ends (setup_ended, trade_ended, recalled, lending_off), each with its
line_loan audit line.
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from line_lending import loans, setting, sockets
from line_lending.constants_line_lending import LINE_LENDING_FRONT_COOLDOWN_SEC
from sensors import focus_store
from tests.bot_helpers import ready_l2
from tests.line_lending_desk import Lane, install, line_loan_lines, window


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def desk(monkeypatch):
    from capture import feed_hold
    from leaderboard import auto_record
    from stock_mode import store

    d = install(monkeypatch)
    yield d
    loans.reset_for_tests()
    sockets.reset_for_tests()
    focus_store.reset_for_tests()
    feed_hold.reset_for_tests()
    store.reset_for_tests()
    auto_record.reset_for_tests()


def three_tabs(desk, *, front: str = "DEF", tabs=("ABC", "DEF", "GHI"), now: float | None = None) -> float:
    """Three Trader tabs hold the three lines; the window shows ``front``."""
    now = time.time() if now is None else now
    for sym in tabs:
        desk.tab_line(sym)
    focus_store.record_window(window(front, list(tabs)), now=now)
    return now


def near_aisp(desk, **kw):
    ready_l2(brain=None, heartbeat=False, symbols=("AISP",), depth_line=False, **kw)
    desk.lanes = [Lane("first_pullback", near=("AISP",))]


def test_a_hidden_tab_lends_its_line_to_a_setup_near_its_trigger(desk):
    near_aisp(desk)
    now = three_tabs(desk)
    focus_store.record_window(window("GHI", ["ABC", "DEF", "GHI"], instance="w0", window_id="old"), now=now - 60)
    focus_store.record_window(window("DEF", ["ABC", "DEF", "GHI"], instance="w0", window_id="old"), now=now - 30)
    run(loans.tick(now))
    # ABC: hidden, and looked at least recently (GHI and DEF were shown since).
    (lender, frame), = desk.frames
    assert lender == "ABC"
    assert frame["type"] == "lent" and frame["symbol"] == "ABC"
    assert frame["to"] == {"symbol": "AISP", "setup_type": "first_pullback", "setup_id": "AISP-2026-10-01-1"}
    assert frame["text"] == ("Level 2 lent to AISP's first pullback (near its trigger) -- back when it ends or "
                             "when you bring this tab to the front")
    assert "ABC" in desk.unsubscribed and desk.lines["AISP"]["viewers"] == 1
    assert desk.tape["AISP"] == 1                         # the tape gate reads prints beside the book
    (start,) = line_loan_lines()
    assert start["outcome"] == "lent"
    assert start["reason"] == "ABC's Level 2 lent to AISP's first pullback (near its trigger)"
    assert start["inputs"] == {"lender": "ABC", "borrower": "AISP", "setup_type": "first_pullback",
                               "setup_id": "AISP-2026-10-01-1"}
    print("LENT FRAME", json.dumps(frame))


def test_a_tab_on_a_stock_nova_needs_itself_never_lends(desk):
    ready_l2(brain=None, heartbeat=False, symbols=("AISP", "ABC"), depth_line=False)
    desk.lanes = [Lane("first_pullback", near=("AISP",)), Lane("bull_flag", armed=("ABC",))]
    from bot.persist import load_session, save_session

    row = load_session()
    row["setup_levels"] = {"first_pullback": 2, "bull_flag": 2}
    save_session(row)
    now = three_tabs(desk)
    run(loans.tick(now))
    assert [f[0] for f in desk.frames] == ["GHI"]              # ABC's own bull flag keeps its line


def test_a_loan_that_fails_midway_leaves_nothing_pending(desk, monkeypatch):
    from line_lending import lines

    async def broken(_symbol):
        raise RuntimeError("IB went away")

    monkeypatch.setattr(lines, "hold_borrower", broken)
    near_aisp(desk)
    now = three_tabs(desk)
    run(loans.tick(now))
    assert loans.lenders() == [] and loans.lent_frame("ABC") is None
    assert "IB went away" in loans.view()["error"]
    assert line_loan_lines() == []


def test_a_socket_for_the_lender_meets_the_lent_frame_until_its_tab_comes_to_the_front(desk):
    near_aisp(desk)
    now = three_tabs(desk)
    run(loans.tick(now))
    assert run(loans.on_socket_open("ABC", front=False, now=now))["to"]["symbol"] == "AISP"
    assert run(loans.on_socket_open("ABC", front=True, now=now + 1)) is None
    assert loans.lenders() == [] and "AISP" in desk.unsubscribed and "AISP" in desk.tape_dropped
    end = line_loan_lines()[-1]
    assert end["outcome"] == "ended" and end["inputs"]["end"] == "recalled"
    assert end["reason"] == "AISP's first pullback lost its Level 2 line: ABC came to the front"
    assert loans.view()["recent"][0]["end"] == "recalled"


def test_the_focus_sensor_showing_the_tab_recalls_the_loan(desk):
    near_aisp(desk)
    now = three_tabs(desk)
    run(loans.tick(now))
    focus_store.record_window(window("ABC", ["ABC", "DEF", "GHI"]), now=now + 5)
    run(loans.tick(now + 5))
    assert loans.lenders() == [] and line_loan_lines()[-1]["inputs"]["end"] == "recalled"


def test_a_recalled_tab_is_not_lent_again_at_once(desk):
    near_aisp(desk)
    now = three_tabs(desk)
    run(loans.tick(now))
    assert desk.frames[-1][0] == "ABC"
    run(loans.on_socket_open("ABC", front=True, now=now + 1))
    desk.tab_line("ABC")                                   # the tab took its line back, then went behind again
    focus_store.record_window(window("DEF", ["ABC", "DEF", "GHI"]), now=now + 2)
    run(loans.tick(now + 2))
    assert desk.frames[-1][0] == "GHI" and loans.lenders() == ["GHI"]


def test_the_tab_in_front_never_lends(desk):
    near_aisp(desk)
    now = time.time()
    desk.tab_line("DEF")
    for sym in ("ABC", "GHI"):                             # two other windows show these in front
        desk.tab_line(sym)
    focus_store.record_window(window("DEF", ["DEF"], instance="a", window_id="main"), now=now)
    focus_store.record_window(window("ABC", ["ABC"], instance="b", window_id="trader:ABC"), now=now)
    focus_store.record_window(window("GHI", ["GHI"], instance="c", window_id="trader:GHI"), now=now)
    run(loans.tick(now))
    assert desk.frames == [] and loans.lenders() == []


def test_a_line_a_record_holds_never_lends(desk):
    from capture import feed_hold

    near_aisp(desk)
    now = three_tabs(desk, front="DEF", tabs=("ABC", "DEF", "GHI"))
    for sym in ("ABC", "GHI"):
        feed_hold._held[sym] = {"tape": True, "depth": True}
        desk.lines[sym]["viewers"] += 1                    # the hold counts as a viewer
    run(loans.tick(now))
    assert desk.frames == []


def test_a_level2_outside_a_trader_tab_keeps_its_line(desk):
    near_aisp(desk)
    now = three_tabs(desk)
    for sym in ("ABC", "GHI"):                             # the Account page's ladder opens no ?tab=1
        sockets.opened(sym, tab=False, front=False, now=now - 120)
        desk.lines[sym]["viewers"] += 1
    run(loans.tick(now))
    assert desk.frames == []


def test_an_unknown_focus_never_lends(desk):
    near_aisp(desk)
    for sym in ("ABC", "DEF", "GHI"):
        desk.tab_line(sym)
    run(loans.tick(time.time()))
    assert desk.frames == []


def test_a_free_line_means_no_loan(desk):
    near_aisp(desk)
    now = three_tabs(desk, tabs=("ABC", "DEF"))
    run(loans.tick(now))
    assert desk.frames == []


def test_a_tab_seen_in_front_lately_is_not_lent(desk):
    near_aisp(desk)
    now = three_tabs(desk)
    sockets.seen_in_front("ABC", now - 5)
    sockets.seen_in_front("GHI", now - 5)
    run(loans.tick(now))
    assert desk.frames == []
    later = now - 5 + LINE_LENDING_FRONT_COOLDOWN_SEC
    focus_store.record_window(window("DEF", ["ABC", "DEF", "GHI"]), now=later)
    run(loans.tick(later))
    assert [f[0] for f in desk.frames] == ["ABC"]


def test_a_tab_the_operator_just_left_is_not_lent_at_once(desk):
    ready_l2(brain=None, heartbeat=False, symbols=("AISP",), depth_line=False)
    tabs = ["ABC", "DEF", "GHI"]
    now = three_tabs(desk, front="ABC")
    focus_store.record_window(window("GHI", tabs, instance="w2", window_id="trader:GHI"), now=now)
    run(loans.tick(now))                                  # nothing near yet; ABC and GHI are in front
    desk.lanes = [Lane("first_pullback", near=("AISP",))]
    for at in (now + 5, now + 20):                         # the operator moved from ABC to DEF
        focus_store.record_window(window("DEF", tabs), now=at)
        focus_store.record_window(window("GHI", tabs, instance="w2", window_id="trader:GHI"), now=at)
        run(loans.tick(at))
    assert desk.frames == []
    at = now + LINE_LENDING_FRONT_COOLDOWN_SEC + 1
    focus_store.record_window(window("DEF", tabs), now=at)
    focus_store.record_window(window("GHI", tabs, instance="w2", window_id="trader:GHI"), now=at)
    run(loans.tick(at))
    assert [f[0] for f in desk.frames] == ["ABC"]


@pytest.mark.parametrize("case", ["bot_off", "strategy_eyes", "buy_you"])
def test_no_loan_unless_nova_may_buy_the_setup(desk, case):
    from bot.persist import load_session, save_session

    near_aisp(desk, activate=case != "bot_off")
    if case == "strategy_eyes":
        row = load_session()
        row["setup_levels"] = {"first_pullback": 1}
        save_session(row)
    if case == "buy_you":
        row = load_session()
        row["symbol_allowlist"] = []
        save_session(row)
    now = three_tabs(desk)
    run(loans.tick(now))
    assert desk.frames == []


def test_auto_entry_is_a_nova_buy(desk):
    from bot.persist import load_session, save_session
    from stock_mode import store

    near_aisp(desk)
    row = load_session()
    row["symbol_allowlist"] = []
    save_session(row)
    store.sync_venue("paper")
    store.set_switch("AISP", {"buy": "nova", "sell": "you", "set_at": time.time()})
    now = three_tabs(desk)
    run(loans.tick(now))
    assert [f[1]["to"]["symbol"] for f in desk.frames] == ["AISP"]


def test_the_line_returns_when_the_setup_ends(desk):
    near_aisp(desk)
    now = three_tabs(desk)
    run(loans.tick(now))
    desk.lanes = [Lane("first_pullback")]                  # the setup failed
    run(loans.tick(now + 5))
    assert loans.lenders() == [] and desk.lines.get("AISP") is None
    end = line_loan_lines()[-1]
    assert end["inputs"]["end"] == "setup_ended"
    assert end["reason"] == ("ABC's Level 2 goes back from AISP's first pullback: it is no longer armed, near its "
                             "trigger or in a trade")


def test_a_trade_keeps_the_loan_until_it_ends(desk):
    from bot.persist import load_session, save_session

    ready_l2(brain=None, heartbeat=False, symbols=("AISP",), depth_line=False)
    desk.lanes = [Lane("first_pullback", trades=("AISP",))]
    now = three_tabs(desk)
    run(loans.tick(now))
    assert loans.view()["loans"][0]["why"] == "in a trade"
    desk.lanes = []                                        # the scoring window closed ...
    row = load_session()
    row["trade"] = {"symbol": "AISP", "state": "open", "venue": "paper"}
    save_session(row)
    run(loans.tick(now + 5))
    assert loans.lenders() == ["ABC"]                      # ... while Nova still holds the trade
    row["trade"] = {"symbol": "AISP", "state": "closed", "venue": "paper"}
    save_session(row)
    run(loans.tick(now + 10))
    assert loans.lenders() == [] and line_loan_lines()[-1]["inputs"]["end"] == "trade_ended"


def test_switching_lending_off_ends_every_loan(desk):
    near_aisp(desk)
    now = three_tabs(desk)
    run(loans.tick(now))
    setting.set_on(False)
    run(loans.tick(now + 5))
    assert loans.lenders() == [] and line_loan_lines()[-1]["inputs"]["end"] == "lending_off"
    run(loans.tick(now + 10))
    assert len(desk.frames) == 1                           # off: nothing is lent again


def test_the_switch_is_desk_wide_and_on_by_default(desk):
    from bot.persist import load_session
    from sim.mode import set_venue

    assert setting.is_on() == (True, None)
    set_venue("paper", persist=False)
    setting.set_on(False)
    assert load_session()["line_lending"] is False
    set_venue("sim", persist=False)                      # a venue's dial moves; the switch stays
    assert setting.is_on() == (False, None)
    set_venue("live", persist=False)
    assert setting.is_on() == (False, None)


def test_a_tape_line_ibkr_ends_after_the_loan_is_said(desk, monkeypatch):
    from ibkr import tape_line

    near_aisp(desk)
    now = three_tabs(desk)
    run(loans.tick(now))
    assert loans.view()["loans"][0]["tape"] is True
    desk.tape.pop("AISP")                                  # IBKR ended it: the tick-by-tick cap
    monkeypatch.setattr(tape_line, "ended", lambda s: {"code": 10190, "message": "Max number of tick-by-tick "
                                                       "requests has been reached."} if s == "AISP" else None)
    (loan,) = loans.view()["loans"]
    assert loan["tape"] is False and "10190" in loan["tape_error"]


def test_a_borrower_without_a_tape_line_still_gets_the_book(desk):
    near_aisp(desk)
    desk.tape_refused = "Max number of tick-by-tick requests has been reached."
    now = three_tabs(desk)
    run(loans.tick(now))
    (loan,) = loans.view()["loans"]
    assert loan["tape"] is False and "tick-by-tick" in loan["tape_error"]
    assert desk.lines["AISP"]["viewers"] == 1
