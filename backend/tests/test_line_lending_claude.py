"""A hidden Trader tab lends its lines to Claude's seat (ADR 068 decision 14, approved design v3, 2026-10-27).

Picked by a bot loan's rule; the tab's words say Claude and what it does; the front never takes the line back,
nor does lending's switch -- only the operator's right-click (Take my Level 2 back from Claude), Claude letting
its line go, or the tab closing ends it. A tab taken back is not taken again while open, and its Level 2 is
admitted past Claude's reservation.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from agent_trader import lines as agent_lines
from agent_trader import seat, tab_line, view
from agent_trader.constants_agent_trader import SEAT_IN, SEAT_WATCHING
from line_lending import claude_loan, loans, setting, sockets
from sensors import focus_store
from tests.line_lending_desk import install, line_loan_lines, window


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def desk(monkeypatch):
    from capture import feed_hold
    from leaderboard import auto_record
    from stock_mode import store

    d = install(monkeypatch)
    seat.reset_for_tests()
    agent_lines.reset_for_tests()
    tab_line.reset_for_tests()
    yield d
    loans.reset_for_tests()
    sockets.reset_for_tests()
    focus_store.reset_for_tests()
    feed_hold.reset_for_tests()
    store.reset_for_tests()
    auto_record.reset_for_tests()
    seat.reset_for_tests()
    agent_lines.reset_for_tests()
    tab_line.reset_for_tests()


def three_tabs(desk, *, front: str = "DEF", now: float | None = None) -> float:
    now = time.time() if now is None else now
    for sym in ("ABC", "DEF", "GHI"):
        desk.tab_line(sym)
    focus_store.record_window(window(front, ["ABC", "DEF", "GHI"]), now=now)
    return now


def seat_takes(desk, sym: str):
    """What the seat's ``lines.acquire`` does on the stand-in desk: open the line and hold a reference."""
    async def take() -> str | None:
        got = await desk.subscribe_async(sym, live=True)
        if not got["ok"]:
            return got["error"]
        desk.ws_viewer_opened(sym)
        agent_lines._held[sym] = {"depth": True, "tape": False}
        return None
    return take


def lend_abc(desk, now: float) -> loans.Loan:
    lender = claude_loan.lender_for("RUNR", skip=set(), now=now)
    assert lender == "ABC"                       # hidden, never shown since: looked at least recently
    loan = run(claude_loan.lend(lender, "RUNR", "watching", seat_takes(desk, "RUNR"), now=now))
    assert loan is not None
    return loan


def test_claude_takes_a_hidden_tabs_lines_and_the_tab_says_so(desk):
    now = three_tabs(desk)
    lend_abc(desk, now)
    (lender, frame), = desk.frames
    assert lender == "ABC" and frame["to"] == {"symbol": "RUNR", "setup_type": "claude", "setup_id": None}
    assert frame["tier"] == "watching" and frame["why"] == "watching RUNR"
    assert frame["text"] == ("Level 2 lent to Claude (watching RUNR) -- back when Claude lets it go, or right-click "
                             "this tab to take it back")
    assert "ABC" in desk.unsubscribed and desk.lines["RUNR"]["viewers"] == 1
    assert ("ABC", "lent to Claude") in desk.tape_dropped
    (start,) = line_loan_lines()
    assert start["outcome"] == "lent" and start["reason"] == ("ABC's Level 2 and Time & Sales lent to Claude "
                                                              "(watching RUNR)")
    assert loans.view()["loans"][0]["setup_type"] == "claude"


def test_the_front_never_takes_claudes_line_back(desk):
    now = three_tabs(desk)
    lend_abc(desk, now)
    assert run(loans.on_socket_open("ABC", front=True, now=now + 1))["to"]["setup_type"] == "claude"
    assert loans.lent_frame("ABC", front=True)["tier"] == "watching"
    focus_store.record_window(window("ABC", ["ABC", "DEF", "GHI"]), now=now + 5)
    run(loans.tick(now + 5))                     # the bots' tick: the tab in front ends no loan to Claude
    assert run(loans.recall("ABC", now=now + 6)) is False
    assert loans.lenders() == ["ABC"] and [r["outcome"] for r in line_loan_lines()] == ["lent"]


def test_lendings_switch_is_the_bots_not_claudes(desk):
    now = three_tabs(desk)
    lend_abc(desk, now)
    setting.set_on(False)
    run(loans.tick(now + 5))
    assert run(loans.end_all("lending_off", "line lending was switched off")) == 0
    assert loans.lenders() == ["ABC"]


def test_the_words_follow_what_claude_does(desk):
    now = three_tabs(desk)
    lend_abc(desk, now)
    claude_loan.follow("RUNR", "in_trade")
    assert "(in a trade on RUNR)" in loans.lent_frame("ABC")["text"]
    claude_loan.follow("RUNR", "")               # Paper unread: the words stay
    assert loans.view()["loans"][0]["why"] == "in a trade on RUNR"


def test_a_tab_the_operator_took_back_is_skipped(desk):
    now = three_tabs(desk)
    assert claude_loan.lender_for("RUNR", skip={"ABC"}, now=now) == "GHI"
    assert claude_loan.lender_for("RUNR", skip={"ABC", "GHI"}, now=now) is None   # DEF is in front


def test_the_operators_right_click_gives_the_tab_its_lines_back(desk, monkeypatch):
    now = three_tabs(desk)
    seat.claim(now=now)
    seat.set_symbol("RUNR", now=now)
    lend_abc(desk, now)
    released: list[bool] = []

    async def release(symbol=None, *, at_once=False):
        released.append(at_once)
        agent_lines._held.clear()

    monkeypatch.setattr(agent_lines, "release", release)
    monkeypatch.setattr(tab_line, "_holds_shares", lambda: True)
    assert run(tab_line.take_back("DEF", now=now + 1)) == "DEF's Level 2 is not lent to Claude"
    assert run(tab_line.take_back("abc", now=now + 1)) is None
    assert released == [True] and loans.lenders() == []
    end = line_loan_lines()[-1]
    assert end["inputs"]["end"] == "taken_back"
    assert end["reason"] == "ABC's Level 2 and Time & Sales go back from Claude: you took it back"
    assert tab_line.may_return("ABC") and tab_line.on_hold(now + 5) and not tab_line.on_hold(now + 11)
    last = seat.snapshot()["events"][-1]
    assert last["kind"] == "tab_line_back"
    assert last["text"] == "You took ABC's line back from Claude · RUNR stop and sell still rest"


def test_the_loan_ends_when_claude_lets_its_line_go_or_the_tab_closes(desk):
    now = three_tabs(desk)
    lend_abc(desk, now)
    agent_lines._held.clear()                    # the seat gave its line up (off, yielded, quiet)
    run(tab_line.keep(now + 1))
    assert loans.lenders() == [] and line_loan_lines()[-1]["inputs"]["end"] == "claude_let_go"

    loans.reset_for_tests()
    desk.tab_line("ABC")
    lend_abc(desk, now + 2)
    focus_store.record_window(window("DEF", ["DEF", "GHI"]), now=now + 3)
    run(tab_line.keep(now + 3))
    assert loans.lenders() == [] and line_loan_lines()[-1]["inputs"]["end"] == "tab_closed"


def test_a_taken_back_tab_is_forgotten_once_it_closes(desk):
    now = three_tabs(desk)
    tab_line._taken_back.add("ABC")
    focus_store.record_window(window("DEF", ["DEF", "GHI"]), now=now + 1)
    run(tab_line.keep(now + 1))
    assert tab_line.taken_back() == []


def test_a_taken_back_tab_is_admitted_past_claudes_reservation(monkeypatch):
    import ibkr.depth as depth

    seat.reset_for_tests()
    agent_lines.reset_for_tests()
    tab_line.reset_for_tests()
    book = {"SPIK": 1, "FLTX": 1}
    monkeypatch.setattr(depth, "subscribed_symbols", lambda: list(book))
    monkeypatch.setattr(depth, "viewer_count", lambda s: book.get(s, 0))
    seat.claim()
    assert agent_lines.desk_refusal("ABC") is not None
    tab_line._taken_back.add("ABC")
    assert agent_lines.desk_refusal("ABC") is None
    assert agent_lines.desk_refusal("XYZ") is not None
    seat.reset_for_tests()
    tab_line.reset_for_tests()


def test_the_pill_says_where_claudes_line_came_from():
    base = "Claude · Watching RUNR"
    assert view.pill_text(SEAT_WATCHING, base, holds=True, lent_from="SMPL") == (
        "Claude · Watching RUNR · on your SMPL tab's line")
    assert view.pill_text(SEAT_WATCHING, base, holds=True, lent_from=None) == base
    assert view.pill_text(SEAT_IN, "Claude · In RUNR +$24.00", holds=False, lent_from=None) == (
        "Claude · In RUNR +$24.00 · no Level 2")
