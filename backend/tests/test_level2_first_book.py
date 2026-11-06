"""An open Level 2 with no book yet locks orders; a first-book watch says why (#913, ADR 045 amendment 2026-10-27).

BKYI, 2026-10-13 09:40 and 11:30 ET: after Gateway connectivity drops IBKR never answered the Level 2 request,
the depth socket said ``subscribed`` and beat every 0.25 s, and the ticket stayed open -- the gate read the
screen's null book stamp as no lag. The operator chose option 1 on 2026-10-27: lock while that stock's Level 2
is open and waiting for its first book; with no Level 2 open, the quote path is unchanged.
"""
from __future__ import annotations

import json
import logging
import time
from types import SimpleNamespace

import pytest

import instance_identity
from constants_market_view import BOOK_WAITING, MARKET_VIEW_FIRST_BOOK_WAIT_SEC
from ibkr.depth import first_book, handlers, release, state
from market_view import gate, versions
from tests.depth_ticks import depth_ticker

SYM = "BKYI"
_REAL_LINE_ANSWER = release.line_answer


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    from ibkr import feed_pulse
    from perf import stall_watch

    import sim.mode

    versions.reset_for_tests()
    state.reset_all()
    first_book.reset_for_tests()
    monkeypatch.setattr(feed_pulse, "gaps_for_tape", lambda now=None: [])
    monkeypatch.setattr(stall_watch, "stalled_ms", lambda name: 0.0)
    monkeypatch.setattr(sim.mode, "is_replay_desk", lambda: False)
    monkeypatch.setattr(gate, "_tape_missing", lambda symbol, now: None)   # no tape line: not judged here
    monkeypatch.setattr(release, "line_answer", lambda ib, contract: None)  # IBKR has not answered
    yield
    state.reset_all()
    versions.reset_for_tests()


def _open_line(symbol: str = SYM, at: float | None = None) -> float:
    """A live depth request for *symbol*, as ``subscribe_async`` makes it, with no book yet."""
    t = time.time() if at is None else at
    state.reserve_slot(symbol)
    state._contracts[symbol] = SimpleNamespace(conId=1, symbol=symbol)
    state.stamp_line(symbol, now=t)
    state.reset_book(symbol)
    return t


def _l1_tick(symbol: str = SYM) -> None:
    """An L1 tick or a print on the same ticker: the depth handler runs with no row operations."""
    handlers.on_update_book(SimpleNamespace(domTicks=[]), symbol)


def _book(symbol: str = SYM) -> None:
    handlers.on_update_book(depth_ticker(bids=[(2.10, 500)], asks=[(2.12, 800)]), symbol)


def _place(symbol: str = SYM, source: str = "manual"):
    act = time.time() * 1000.0
    view = {"schema_version": 1, "symbol": symbol, "action_wall_ms": act,
            "instance": instance_identity.INSTANCE_ID, "book": None, "quote": None, "desk": None}
    return SimpleNamespace(operation="place", source=source, symbol=symbol, view=view,
                           client_timing={"action_wall_ms": act}, backend_ingress_wall_ns=int((act + 20) * 1e6))


def test_beats_and_l1_ticks_without_a_book_keep_orders_locked():
    _open_line()
    for _ in range(5):
        _l1_tick()                                   # the handler fires, but no row has come
    assert first_book.waiting(SYM)["state"] == first_book.WAITING
    lock = gate.desk_lock(SYM)
    assert lock["code"] == BOOK_WAITING
    assert "has sent no book yet" in lock["text"] and "Flatten and cancels still work" in lock["text"]
    # The order the 2026-10-13 desk could send: null book and quote stamps, timely arrival.
    check = gate.check(_place())
    assert check.refused and check.code == BOOK_WAITING
    assert check.measures["book_waiting_since"] is not None and check.measures["book_lag_ms"] is None


def test_a_delayed_first_book_opens_the_ticket():
    _open_line()
    _l1_tick()
    assert gate.desk_lock(SYM)["code"] == BOOK_WAITING
    _book()
    assert first_book.waiting(SYM) is None
    assert gate.desk_lock(SYM) is None
    assert gate.check(_place()).verdict == "ok"


def test_a_new_request_starts_again_an_earlier_book_never_counts():
    _open_line()
    _book()
    assert first_book.waiting(SYM) is None
    # A retry or reconnect: subscribe_async stamps the line again before reqMktDepth.
    state.stamp_line(SYM)
    assert gate.desk_lock(SYM)["code"] == BOOK_WAITING
    _book()
    assert gate.desk_lock(SYM) is None


def test_no_level2_open_leaves_the_quote_path_as_it_was():
    assert first_book.waiting(SYM) is None
    assert gate.desk_lock(SYM) is None
    assert gate.check(_place()).verdict == "ok"


def test_a_line_let_go_is_no_longer_judged():
    _open_line()
    state.pop_contract(SYM)
    state.clear_symbol(SYM)
    assert first_book.waiting(SYM) is None and gate.desk_lock(SYM) is None


def test_a_replay_desk_is_never_held_by_a_live_request(monkeypatch):
    """Off the live edge the market is the replay: a paused replay is not an unanswered request."""
    import sim.mode

    _open_line()
    monkeypatch.setattr(sim.mode, "is_replay_desk", lambda: True)
    assert first_book.waiting(SYM) is None
    assert gate.desk_lock(SYM) is None


def test_a_replay_slot_is_not_a_live_line():
    state.reserve_slot(SYM)                       # what subscribe_async does on a replay desk
    assert first_book.waiting(SYM) is None


def test_protective_exits_are_never_gated_while_waiting():
    _open_line()
    for source in ("flatten", "kill"):
        assert gate.check(_place(source=source)).verdict == "exempt"


@pytest.mark.parametrize(("answer", "kind", "words"), [
    (None, first_book.UNANSWERED, "IBKR has not answered BKYI's Level 2 request in 5 s."),
    (release.GRANTED, first_book.GRANTED, "IBKR granted BKYI's Level 2 but has sent no rows in 5 s."),
    (release.REFUSED, first_book.REFUSED, "IBKR refused BKYI's Level 2 request."),
])
def test_past_the_wait_the_words_say_what_ibkr_has_done(monkeypatch, caplog, answer, kind, words):
    t0 = _open_line(at=1000.0)
    monkeypatch.setattr(release, "line_answer", lambda ib, contract: answer)
    within = first_book.waiting(SYM, now=t0 + MARKET_VIEW_FIRST_BOOK_WAIT_SEC - 0.1)
    assert within["state"] == first_book.WAITING and within["overdue"] is False
    with caplog.at_level(logging.WARNING, logger="ibkr.depth.first_book"):
        late = first_book.waiting(SYM, now=t0 + MARKET_VIEW_FIRST_BOOK_WAIT_SEC + 1)
        again = first_book.waiting(SYM, now=t0 + MARKET_VIEW_FIRST_BOOK_WAIT_SEC + 9)
    assert late == {"since": t0, "state": kind, "overdue": True, "text": words}
    assert again["text"] == words                      # steady: no running count in the words
    assert len([r for r in caplog.records if "first book" in r.getMessage()]) == 1   # once per request
    assert gate.desk_lock(SYM, now=t0 + 30)["text"].startswith(words)


def test_the_watch_never_cancels_or_frees_the_request(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(release, "release", lambda *a, **k: calls.append("release"))
    monkeypatch.setattr(release, "forget", lambda *a, **k: calls.append("forget"))
    t0 = _open_line(at=1000.0)
    first_book.waiting(SYM, now=t0 + 600)
    gate.desk_lock(SYM, now=t0 + 600)
    assert calls == []
    assert state.is_live(SYM) and SYM in state._subscriptions      # its slot is still held


def test_an_l1_fallback_waits_for_a_bid_or_an_ask():
    t0 = _open_line(at=1000.0)
    state.mark_shared_l1(SYM)
    state._subscriptions[SYM]["l1_fallback"] = True
    handlers.on_update_ticker(SimpleNamespace(bid=None, bidSize=None, ask=None, askSize=None), SYM)
    waiting = first_book.waiting(SYM, now=t0 + 10)
    assert waiting["state"] == first_book.L1_WAITING
    assert waiting["text"] == "BKYI's Level 1 fallback has sent no bid or ask in 5 s."
    handlers.on_update_ticker(SimpleNamespace(bid=2.1, bidSize=5, ask=2.12, askSize=8), SYM)
    assert first_book.waiting(SYM, now=t0 + 11) is None


def test_the_beat_says_what_the_line_waits_for():
    from ibkr.depth.stream import beat_frame

    t0 = _open_line(at=1000.0)
    beat = json.loads(beat_frame(SYM, now=t0 + 1))
    assert beat["seq"] == 0 and beat["first_book"]["state"] == first_book.WAITING
    assert beat["first_book"]["overdue"] is False
    assert json.loads(beat_frame(SYM, now=t0 + 6))["first_book"]["state"] == first_book.UNANSWERED
    _book()
    assert json.loads(beat_frame(SYM))["first_book"] is None


def test_line_answer_reads_ib_asyncs_request_without_touching_it(monkeypatch):
    """``release.line_answer`` is a read: no IB or contract, no answer; else ``answer_of`` of the registered request."""
    monkeypatch.setattr(release, "line_answer", _REAL_LINE_ANSWER)
    assert release.line_answer(None, None) is None
    ticker = SimpleNamespace(domBidsDict={}, domAsksDict={})
    sub = SimpleNamespace(reqId=4242, ticker=ticker)
    registry = SimpleNamespace(find_market_data=lambda con_id, kind: sub)
    ib = SimpleNamespace(wrapper=SimpleNamespace(subscriptions=registry))
    contract = SimpleNamespace(conId=1)
    assert release.line_answer(ib, contract) is None                 # asked, not answered
    ticker.domBidsDict = {0: object()}
    assert release.line_answer(ib, contract) == release.GRANTED      # its rows prove the grant
