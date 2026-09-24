"""Tape and depth lines belong to the IBKR session that opened them (#562).

A reconnect builds a new session and every tick-by-tick / depth request of the
old one dies with it. Nova's line maps used to outlive it: ``is_subscribed``
said yes, a viewer or a Record re-acquire joined the dead entry, and nothing
asked IBKR again. Here the fake IB behaves like ib_async 2.1.0 -- one
subscription registry per session, and a request for a line the registry
already holds hands that line back without asking IBKR.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import ibkr.depth as depth
import ibkr.tape_stream as tape
from capture import bridge_ibkr, feed_hold, keepalive
from constants import (
    IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT,
    IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST,
)
from ibkr import client, line_session, session_errors

ALL_LAST = "AllLast"
DEPTH = "mktDepth"


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self


class _Ticker:
    def __init__(self):
        self.updateEvent = _Event()
        self.tickByTicks = []
        self.domTicks = []


class _Registry:
    def __init__(self):
        self.subs: dict[tuple[int, str], SimpleNamespace] = {}

    def find_market_data(self, con_id, kind):
        return self.subs.get((con_id, kind))


class _IB:
    """One IBKR session: its own registry, request ids and a record of what reached IBKR."""

    CON_IDS = {"IPDN": 42, "WHLR": 43}

    def __init__(self):
        self.errorEvent = _Event()
        self.wrapper = SimpleNamespace(subscriptions=_Registry())
        self.next_req = 100
        self.requests: list[tuple[str, str]] = []
        self.cancels: list[tuple[str, str]] = []
        self.qualify_error: str | None = None

    async def qualifyContractsAsync(self, contract):
        if self.qualify_error:
            raise RuntimeError(self.qualify_error)
        contract.conId = self.CON_IDS[contract.symbol]
        return [contract]

    def _request(self, contract, kind):
        key = (contract.conId, kind)
        sub = self.wrapper.subscriptions.subs.get(key)
        if sub is None:  # a registered line is handed back and nothing is sent
            sub = SimpleNamespace(reqId=self.next_req, ticker=_Ticker())
            self.next_req += 1
            self.wrapper.subscriptions.subs[key] = sub
            self.requests.append((kind, contract.symbol))
        return sub.ticker

    def _cancel(self, contract, kind):
        self.cancels.append((kind, contract.symbol))
        self.wrapper.subscriptions.subs.pop((contract.conId, kind), None)

    def reqTickByTickData(self, contract, tick_type, **_kwargs):
        return self._request(contract, tick_type)

    def cancelTickByTickData(self, contract, tick_type):
        self._cancel(contract, tick_type)

    def reqMktDepth(self, contract, numRows=5, isSmartDepth=False, mktDepthOptions=None):
        return self._request(contract, DEPTH)

    def cancelMktDepth(self, contract, isSmartDepth=False):
        self._cancel(contract, DEPTH)


class _Stock:
    def __init__(self, symbol, *_args):
        self.symbol = symbol
        self.conId = 0


class _Session:
    """The desk's IBKR session as the line managers read it."""

    def __init__(self):
        self.ib = _IB()
        self.gen = 1
        self.code: int | None = None

    def reconnect(self):
        """The socket dropped and a new IB() reached READY."""
        self.ib = _IB()
        self.gen += 1

    def restore(self, code: int):
        """IBKR restored connectivity on the same socket (1101 / 1102): READY again."""
        self.code = code
        self.gen += 1


def _reset():
    tape.reset_for_tests()
    depth.reset_all()
    line_session.reset_for_tests()
    feed_hold.reset_for_tests()
    keepalive.reset_for_tests()


@pytest.fixture
def sess(monkeypatch):
    s = _Session()
    _reset()
    monkeypatch.setattr(client, "get_ib", lambda: s.ib)
    monkeypatch.setattr(client, "current_generation", lambda: s.gen)
    monkeypatch.setattr(client, "is_ready", lambda: True)
    monkeypatch.setattr(client, "is_connected", lambda: True)
    monkeypatch.setattr(session_errors, "last_connectivity_code", lambda: s.code)
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", _Stock)
    monkeypatch.setattr(tape, "_warm_10sec_fill", lambda _sym: None)
    monkeypatch.setattr(depth, "_load_ib_types", lambda: True)
    monkeypatch.setattr(depth, "_Stock", _Stock)
    monkeypatch.setattr(depth, "IBKR_DEPTH_RELEASE_GRACE_SEC", 0.0)
    import sim.mode

    monkeypatch.setattr(sim.mode, "is_replay_desk", lambda: False)
    monkeypatch.setattr(sim.mode, "is_sim_mode", lambda: False)
    yield s
    _reset()


async def _tape_viewer(symbol: str) -> asyncio.Queue:
    """A Time & Sales socket: the line, a viewer reference and its own queue."""
    assert (await tape.subscribe_async(symbol))["ok"] is True
    tape.ws_viewer_opened(symbol)
    return tape.open_viewer_queue(symbol)


async def _depth_viewer(symbol: str) -> asyncio.Queue:
    assert (await depth.subscribe_async(symbol))["ok"] is True
    depth.ws_viewer_opened(symbol)
    return depth.open_viewer_queue(symbol)


async def _settle() -> None:
    """What the READY hook runs on the HTTP loop, and the asks it starts."""
    line_session.settle()
    tasks = list(line_session._renewing.values())
    if tasks:
        await asyncio.gather(*tasks)


def test_a_line_of_an_ended_session_is_not_subscribed(sess):
    async def run():
        await _tape_viewer("IPDN")
        await _depth_viewer("WHLR")
        sess.reconnect()
        assert tape.is_subscribed("IPDN") is False
        assert depth.is_subscribed("WHLR") is False and depth.is_live("WHLR") is False
        assert depth.current_book("WHLR") is None          # never the old session's book as current
        assert depth.subscribed_symbols() == []
        assert bridge_ibkr.producer_health("IPDN")["state"] == "disconnected"

    asyncio.run(run())


def test_held_lines_are_asked_for_again_on_the_new_session(sess):
    async def run():
        tape_q = await _tape_viewer("IPDN")
        depth_q = await _depth_viewer("WHLR")
        old = sess.ib
        sess.reconnect()
        await _settle()
        assert tape.is_subscribed("IPDN") is True and depth.is_live("WHLR") is True
        assert sess.ib.requests == [(ALL_LAST, "IPDN"), (DEPTH, "WHLR")]
        assert old.cancels == [] and sess.ib.cancels == []  # nothing sent to the old IB, nothing to cancel on the new
        assert tape.guard_remaining("IPDN") == 0.0           # no cancel, so IB's 15 s rule never started
        # The viewers kept their queues: the new lines feed them.
        assert tape._viewer_queues["IPDN"] == [tape_q]
        assert tape._tickers["IPDN"]["ticker"].updateEvent.handlers
        new_book = depth._tickers["WHLR"]
        for handler in list(new_book.updateEvent.handlers):
            handler(new_book)
        assert depth_q.get_nowait()["l1_fallback"] is False

    asyncio.run(run())


def test_lines_of_the_current_session_are_untouched(sess):
    async def run():
        await _tape_viewer("IPDN")
        await _depth_viewer("WHLR")
        ticker = tape._tickers["IPDN"]["ticker"]
        await _settle()
        assert sess.ib.requests == [(ALL_LAST, "IPDN"), (DEPTH, "WHLR")]
        assert sess.ib.cancels == [] and line_session._renewing == {}
        assert tape._tickers["IPDN"]["ticker"] is ticker and depth.is_live("WHLR") is True

    asyncio.run(run())


def test_a_line_nobody_watches_is_let_go_and_not_asked_for(sess):
    async def run():
        assert (await tape.subscribe_async("IPDN"))["ok"] is True   # no viewer reference
        sess.reconnect()
        await _settle()
        assert "IPDN" not in tape._tickers and sess.ib.requests == []

    asyncio.run(run())


def test_a_viewer_joining_a_dead_entry_gets_a_real_request(sess):
    """No READY hook ran: the subscribe itself lets the dead line go and asks the new session."""
    async def run():
        assert (await tape.subscribe_async("IPDN"))["ok"] is True
        assert (await depth.subscribe_async("WHLR"))["ok"] is True
        old = sess.ib
        sess.reconnect()
        assert (await tape.subscribe_async("IPDN"))["ok"] is True
        assert (await depth.subscribe_async("WHLR"))["ok"] is True
        assert sess.ib.requests == [(ALL_LAST, "IPDN"), (DEPTH, "WHLR")]
        assert old.cancels == [] and sess.ib.cancels == []
        assert tape.is_subscribed("IPDN") and depth.is_live("WHLR")

    asyncio.run(run())


def test_a_restore_that_kept_its_data_keeps_the_lines(sess):
    """1102: the same socket, IBKR kept the lines -- restamped, nothing cancelled or asked."""
    async def run():
        await _tape_viewer("IPDN")
        await _depth_viewer("WHLR")
        sess.restore(IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT)
        await _settle()
        assert tape.is_subscribed("IPDN") is True and depth.is_live("WHLR") is True
        assert sess.ib.cancels == [] and sess.ib.requests == [(ALL_LAST, "IPDN"), (DEPTH, "WHLR")]

    asyncio.run(run())


def test_a_restore_that_lost_its_data_cancels_on_this_session_and_asks_again(sess, monkeypatch):
    """1101: IBKR forgot the lines but ib_async still holds them, so a plain ask would send nothing."""
    monkeypatch.setattr(tape, "IBKR_TAPE_RESUBSCRIBE_GUARD_SEC", 0.0)

    async def run():
        await _tape_viewer("IPDN")
        await _depth_viewer("WHLR")
        sess.restore(IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST)
        await _settle()
        assert sess.ib.cancels == [(ALL_LAST, "IPDN"), (DEPTH, "WHLR")]
        assert sess.ib.requests == [(ALL_LAST, "IPDN"), (DEPTH, "WHLR")] * 2
        assert tape.is_subscribed("IPDN") is True and depth.is_live("WHLR") is True

    asyncio.run(run())


def test_viewers_are_told_when_the_new_session_will_not_give_the_line(sess, monkeypatch):
    monkeypatch.setattr(line_session, "IBKR_LINE_RENEW_BACKOFF_SEC", (0.0, 0.0))

    async def run():
        tape_q = await _tape_viewer("IPDN")
        depth_q = await _depth_viewer("WHLR")
        sess.reconnect()
        sess.ib.qualify_error = "No security definition has been found"
        await _settle()
        told = tape_q.get_nowait()
        assert told["type"] == "error" and told["released"] is True
        assert "No security definition" in told["message"]
        said = depth_q.get_nowait()
        assert said["type"] == "error" and said["evicted"] is True
        assert tape.is_subscribed("IPDN") is False and depth.is_live("WHLR") is False

    asyncio.run(run())


def test_the_ready_hook_hands_the_settle_to_the_http_loop(sess, monkeypatch):
    """ADR 010: the IB loop only publishes; nothing is dropped or asked for inline."""
    from ibkr import loop_supervisor

    published = []
    monkeypatch.setattr(loop_supervisor, "publish_to_http", lambda cb, *a, **k: published.append(cb))

    async def run():
        await _tape_viewer("IPDN")
        sess.reconnect()
        line_session.on_session_ready(sess.gen)
        assert published == [line_session.settle]
        assert "IPDN" in tape._tickers and sess.ib.requests == []

    asyncio.run(run())


def test_earn_usable_runs_the_hook_with_the_new_generation(monkeypatch):
    from unittest.mock import MagicMock

    import ibkr.account as account_mod
    import ibkr.account_stream as account_stream
    import ibkr.session_state as session_state
    import ibkr.session_usable as session_usable

    async def _noop(*_a, **_k):
        return None

    seen = []
    monkeypatch.setattr(account_mod, "refresh_positions_cache", _noop)
    monkeypatch.setattr(account_stream, "ensure_account_updates", _noop)
    monkeypatch.setattr(client, "_on_session_ready", _noop)
    monkeypatch.setattr(line_session, "on_session_ready", seen.append)
    session_state.reset_for_testing()
    session_usable.reset_for_tests()
    ib = MagicMock()
    ib.isConnected.return_value = True
    try:
        ok, _detail = asyncio.run(session_usable.earn_usable(ib, "connect"))
        assert ok is True and seen == [session_state.generation()] == [1]
    finally:
        session_state.reset_for_testing()
        session_usable.reset_for_tests()


def test_the_keepalive_takes_a_recordings_lines_again_after_a_reconnect(sess):
    """The Gateway-drop re-acquire needs the producer disconnected AND the client ready: now it fires."""
    ops = []

    async def start(symbol):
        raise AssertionError("the recorder never stopped: no new segment")

    async def note(symbol, **kwargs):
        ops.append(("note", symbol, kwargs))

    tape_ops = keepalive.TapeOps(end=lambda s, why: ops.append(("end", s)),
                                 renew=feed_hold.renew_tape, note=note)

    def payload():
        return {"capture": True, "capture_symbol": "IPDN", "capture_symbols": ["IPDN"],
                "sessions": {"IPDN": {"producer": bridge_ibkr.producer_health("IPDN"),
                                      "book": bridge_ibkr.book_health("IPDN")}}}

    async def run():
        assert await feed_hold.acquire("IPDN") is None
        assert feed_hold.held("IPDN") == {"tape": True, "depth": True}
        old = sess.ib
        sess.reconnect()                                   # and the READY hook never ran
        assert payload()["sessions"]["IPDN"]["producer"]["state"] == "disconnected"
        await keepalive.tick(now=1_000.0, payload=payload(), recorder_status={}, ready=client.is_ready,
                             acquire=feed_hold.acquire, release=feed_hold.release, start=start, tape=tape_ops)
        assert sess.ib.requests == [(ALL_LAST, "IPDN"), (DEPTH, "IPDN")]
        assert old.cancels == [] and sess.ib.cancels == []
        assert tape.is_subscribed("IPDN") and depth.is_live("IPDN")
        assert feed_hold.held("IPDN") == {"tape": True, "depth": True}
        assert ops == []                                   # a Gateway drop, not a lost tape
        rows = keepalive.status_fields({}, ["IPDN"])["capture_sessions"]
        assert rows[0]["reacquired"] == 1
        assert payload()["sessions"]["IPDN"]["producer"]["state"] != "disconnected"

    asyncio.run(run())
