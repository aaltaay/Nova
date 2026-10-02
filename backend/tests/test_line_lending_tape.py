"""A loan lends the Time & Sales line with the Level 2 line (ADR 043 decision 6).

IBKR counts tick-by-tick lines like depth lines (three here): three Trader tabs hold three
AllLast lines, so a borrower that only got a book would be refused its tape and read WAIT for
want of prints. These cover the start (both lines lent, the lender's AllLast line cancelled at
once), the recall (both given back at once), a refused tape line (refused at the ask, or ended
by IBKR afterwards), its retry, and the tape reading true once prints arrive.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from line_lending import loans, sockets
from line_lending.constants_line_lending import LINE_LENDING_TAPE_RETRY_SEC, LINE_LENDING_TAPE_SAY_AFTER_SEC
from sensors import focus_store
from tests.bot_helpers import ready_l2
from tests.line_lending_desk import CAP_ERROR, Lane, install, line_loan_lines, window


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def desk(monkeypatch):
    from capture import feed_hold
    from leaderboard import auto_record
    from stock_mode import store

    d = install(monkeypatch)
    ready_l2(brain=None, heartbeat=False, symbols=("AISP",), depth_line=False)
    d.lanes = [Lane("first_pullback", near=("AISP",))]
    yield d
    loans.reset_for_tests()
    sockets.reset_for_tests()
    focus_store.reset_for_tests()
    feed_hold.reset_for_tests()
    store.reset_for_tests()
    auto_record.reset_for_tests()


def three_tabs(desk, now: float, *, front: str = "DEF") -> None:
    """Three Trader tabs hold the three depth lines and the three AllLast lines; DEF is in front."""
    for sym in ("ABC", "DEF", "GHI"):
        desk.tab_line(sym)
    focus_store.record_window(window(front, ["ABC", "DEF", "GHI"]), now=now)


def refresh_focus(now: float) -> None:
    focus_store.record_window(window("DEF", ["ABC", "DEF", "GHI"]), now=now)


def test_a_loan_lends_both_lines_and_frees_the_tape_at_once(desk):
    now = time.time()
    three_tabs(desk, now)
    run(loans.tick(now))
    # The lender's Time & Sales got the same frame as its Level 2, and its AllLast line went at once.
    assert [s for s, _ in desk.tape_frames] == ["ABC"] and desk.tape_frames[0][1] == desk.frames[0][1]
    assert [s for s, _ in desk.tape_dropped] == ["ABC"] and "ABC" not in desk.tape
    # The borrower holds both lines: within IBKR's three tick-by-tick lines.
    assert desk.lines["AISP"]["viewers"] == 1 and desk.tape_viewers["AISP"] == 1 and "AISP" in desk.tape
    (loan,) = loans.view()["loans"]
    assert loan["tape_lent"] is True and loan["tape_state"] == "waiting" and loan["tape"] is False
    assert loan["tape_error"] is None


def test_the_tape_reads_true_once_prints_arrive(desk):
    now = time.time()
    three_tabs(desk, now)
    run(loans.tick(now))
    desk.last_print["AISP"] = now + 1
    (loan,) = loans.view()["loans"]
    assert loan["tape"] is True and loan["tape_state"] == "receiving" and loan["tape_last_print"] == now + 1


def test_a_recall_gives_both_lines_back_in_one_step(desk):
    now = time.time()
    three_tabs(desk, now)
    run(loans.tick(now))
    assert run(loans.on_socket_open("ABC", front=True, now=now + 1)) is None
    # Both of the borrower's lines are cancelled at once: the lender's tab finds room for its own.
    assert "AISP" in desk.unsubscribed and ("AISP", "the loan of its line ended") in desk.tape_dropped
    assert "AISP" not in desk.tape and desk.tape_viewers["AISP"] == 0
    assert len(desk.tape) == 2                             # room for ABC's AllLast line again
    end = line_loan_lines()[-1]
    assert end["inputs"]["end"] == "recalled" and end["inputs"]["tape_lent"] is True


def test_the_end_of_the_setup_gives_both_lines_back(desk):
    now = time.time()
    three_tabs(desk, now)
    run(loans.tick(now))
    desk.lanes = []
    run(loans.tick(now + 5))
    assert ("AISP", "the loan of its line ended") in desk.tape_dropped and "AISP" not in desk.lines
    assert loans.view()["recent"][0]["tape_lent"] is True


def test_a_tape_line_refused_at_the_ask_is_said_with_the_start(desk):
    now = time.time()
    three_tabs(desk, now)
    desk.tape_refused = CAP_ERROR
    run(loans.tick(now))
    (start,) = line_loan_lines()
    assert start["outcome"] == "lent" and start["inputs"]["tape_error"] == CAP_ERROR
    assert "AISP has no Time & Sales line" in start["reason"]
    (loan,) = loans.view()["loans"]
    assert loan["tape"] is False and loan["tape_state"] == "refused" and loan["tape_error"] == CAP_ERROR
    assert desk.lines["AISP"]["viewers"] == 1               # the book is still lent


def test_a_tape_line_ibkr_ends_afterwards_is_said_and_asked_again(desk):
    now = time.time()
    three_tabs(desk, now)
    run(loans.tick(now))
    desk.end_tape("AISP")                                  # 10190 arrives on its own, after the request
    refresh_focus(now + 5)
    run(loans.tick(now + 5))
    said = [r for r in line_loan_lines() if r["outcome"] == "tape_refused"]
    assert len(said) == 1 and "10190" in said[0]["inputs"]["tape_error"]
    assert "AISP's first pullback has no Time & Sales line" in said[0]["reason"]
    (loan,) = loans.view()["loans"]
    assert loan["tape_state"] == "refused" and "10190" in loan["tape_error"]
    # Not asked again while IBKR's 15 s rule stands; once it passes, asked again -- and it comes up.
    later = now + LINE_LENDING_TAPE_RETRY_SEC + 1
    refresh_focus(later)
    run(loans.tick(later))
    assert desk.tape_asked.count("AISP") == 1
    desk.guard["AISP"] = 0.0
    run(loans.tick(later + 1))
    assert desk.tape_asked.count("AISP") == 2 and "AISP" in desk.tape
    run(loans.tick(later + 2))
    assert [r["outcome"] for r in line_loan_lines()][-1] == "tape_opened"
    assert loans.view()["loans"][0]["tape_error"] is None
    assert len([r for r in line_loan_lines() if r["outcome"] == "tape_refused"]) == 1


def test_a_held_line_down_without_ibkrs_word_is_said_only_after_a_while(desk):
    now = time.time()
    three_tabs(desk, now)
    run(loans.tick(now))
    desk.tape.pop("AISP")                                  # a reconnect is asking for it again
    refresh_focus(now + 5)
    run(loans.tick(now + 5))
    assert [r for r in line_loan_lines() if r["outcome"] == "tape_refused"] == []
    at = now + 5 + LINE_LENDING_TAPE_SAY_AFTER_SEC
    refresh_focus(at)
    run(loans.tick(at))
    assert len([r for r in line_loan_lines() if r["outcome"] == "tape_refused"]) == 1


def test_a_lender_whose_tape_another_panel_watches_keeps_its_tape(desk):
    now = time.time()
    three_tabs(desk, now)
    for sym in ("ABC", "GHI"):                             # a Time & Sales outside a Trader tab watches these
        sockets.opened(sym, tab=False, front=False, now=now - 120, kind=sockets.TAPE)
        desk.tape_viewers[sym] += 1
    run(loans.tick(now))
    assert [s for s, _ in desk.frames] == ["ABC"] and desk.tape_frames == [] and desk.tape_dropped == []
    (loan,) = loans.view()["loans"]
    assert loan["tape_lent"] is False and loan["tape_error"] == CAP_ERROR   # three AllLast lines stand
    assert line_loan_lines()[0]["reason"].startswith("ABC's Level 2 lent to AISP's")


def test_a_lender_that_can_give_its_tape_is_chosen_first(desk):
    now = time.time()
    three_tabs(desk, now)
    sockets.opened("ABC", tab=False, front=False, now=now - 120, kind=sockets.TAPE)
    desk.tape_viewers["ABC"] += 1                          # ABC's tape cannot go; GHI's can
    run(loans.tick(now))
    assert [s for s, _ in desk.frames] == ["GHI"] and [s for s, _ in desk.tape_frames] == ["GHI"]
    assert loans.view()["loans"][0]["tape_lent"] is True


def test_a_borrower_with_its_own_tape_line_borrows_only_the_book(desk):
    now = time.time()
    three_tabs(desk, now)
    desk.tape["AISP"] = 0                                  # some other holder's AllLast line is up already
    run(loans.tick(now))
    assert desk.tape_frames == [] and desk.tape_dropped == []
    (loan,) = loans.view()["loans"]
    assert loan["tape_lent"] is False and loan["tape_state"] == "waiting"
