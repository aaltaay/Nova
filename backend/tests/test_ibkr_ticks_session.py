"""A Level 1 line belongs to the IBKR session that opened it (#565).

At READY ``ibkr.ticks`` lets go of the last session's L1 lines and each owner
subscribes again. After a 1101 restore on the same socket IBKR has forgotten
the line, but ib_async still holds its ``reqMktData`` and hands the dead
ticker back to the re-subscribe without asking IBKR. The fake IB here behaves
like ib_async 2.1.0: one subscription registry per session, and a
``reqMktData`` for a contract the registry already holds sends nothing.
"""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from constants import (
    IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT,
    IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST,
)
from ibkr import client, session_errors, ticks
from tests.fakes.fake_ibkr_feed import FakeTicker

MKT_DATA = "mktData"


class _Registry:
    def __init__(self):
        self.subs: dict[tuple[int, str], SimpleNamespace] = {}

    def find_market_data(self, con_id, kind):
        return self.subs.get((con_id, kind))


class _IB:
    """One IBKR session: its own registry and a log of what reached IBKR, in order."""

    CON_IDS = {"IPDN": 42, "WHLR": 43}

    def __init__(self, log: list[tuple[str, str]] | None = None):
        self.wrapper = SimpleNamespace(subscriptions=_Registry())
        self.log = log if log is not None else []
        self.cancel_error: Exception | None = None
        self.next_req = 1

    @property
    def requests(self) -> list[str]:
        return [sym for what, sym in self.log if what == "reqMktData"]

    @property
    def cancels(self) -> list[str]:
        return [sym for what, sym in self.log if what == "cancelMktData"]

    async def qualifyContractsAsync(self, contract):
        contract.conId = self.CON_IDS[contract.symbol]
        return [contract]

    def reqMktData(self, contract, generic_ticks="", snapshot=False, regulatory=False):
        key = (contract.conId, MKT_DATA)
        sub = self.wrapper.subscriptions.subs.get(key)
        if sub is None:  # a registered line is handed back and nothing is sent
            sub = SimpleNamespace(reqId=self.next_req, ticker=FakeTicker(contract.symbol))
            self.next_req += 1
            self.wrapper.subscriptions.subs[key] = sub
            self.log.append(("reqMktData", contract.symbol))
        return sub.ticker

    def cancelMktData(self, contract):
        # ib_async unregisters the line even when sending the cancel fails.
        self.wrapper.subscriptions.subs.pop((contract.conId, MKT_DATA), None)
        if self.cancel_error is not None:
            raise self.cancel_error
        self.log.append(("cancelMktData", contract.symbol))
        return True


class _Session:
    def __init__(self):
        self.ib: _IB | None = _IB()
        self.code: int | None = None


@pytest.fixture
def sess(monkeypatch):
    s = _Session()
    ticks._subs.clear()
    ticks._subscribe_lock = None
    monkeypatch.setattr(client, "get_ib", lambda: s.ib)
    monkeypatch.setattr(session_errors, "last_connectivity_code", lambda: s.code)
    yield s
    ticks._subs.clear()
    ticks._subscribe_lock = None


def _run(coro):
    ticks._subscribe_lock = None  # each asyncio.run is a new loop
    return asyncio.run(coro)


def _handlers(symbol: str) -> int:
    return len(ticks.get_ticker(symbol).updateEvent._handlers)


def test_a_1101_restore_cancels_the_lost_line_before_the_owner_asks_again(sess):
    ib = sess.ib
    assert _run(ticks.subscribe("IPDN", ticks.OWNER_HOD)) is True
    dead = ticks.get_ticker("IPDN")
    # Why the cancel is needed: ib_async hands the registered line back unasked.
    assert ib.reqMktData(SimpleNamespace(symbol="IPDN", conId=42)) is dead
    assert ib.requests == ["IPDN"]

    sess.code = IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST
    assert _run(ticks.clear_all_subscriptions(reason="1101 restore", ib=ib)) == 1
    assert ticks.subscribed_symbols() == []
    assert dead.updateEvent._handlers == []  # Nova's handler left the dead ticker

    assert _run(ticks.subscribe("IPDN", ticks.OWNER_HOD)) is True
    assert ib.log == [("reqMktData", "IPDN"), ("cancelMktData", "IPDN"), ("reqMktData", "IPDN")]
    assert ticks.get_ticker("IPDN") is not dead
    assert _handlers("IPDN") == 1
    assert ticks.owners_for("IPDN") == {ticks.OWNER_HOD}


def test_a_1102_restore_keeps_the_line_and_cancels_nothing(sess):
    ib = sess.ib
    assert _run(ticks.subscribe("IPDN", ticks.OWNER_HOD)) is True
    assert _run(ticks.subscribe("IPDN", ticks.OWNER_DETAIL)) is True
    kept = ticks.get_ticker("IPDN")

    sess.code = IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT
    assert _run(ticks.clear_all_subscriptions(reason="1102 restore", ib=ib)) == 0
    assert ib.cancels == []
    assert ticks.subscribed_symbols() == ["IPDN"]
    assert ticks.get_ticker("IPDN") is kept
    assert ticks.owners_for("IPDN") == {ticks.OWNER_HOD, ticks.OWNER_DETAIL}
    assert _handlers("IPDN") == 1

    # The owner's reconcile joins the kept line: no request, no second handler.
    assert _run(ticks.subscribe("IPDN", ticks.OWNER_HOD)) is True
    assert ib.log == [("reqMktData", "IPDN")]
    assert _handlers("IPDN") == 1


@pytest.mark.parametrize("code", [None, IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST])
def test_a_new_session_cancels_nothing_on_the_old_ib(sess, code):
    old = sess.ib
    assert _run(ticks.subscribe("IPDN", ticks.OWNER_SCANNER)) is True
    sess.ib = _IB()  # the socket dropped; a new IB() reached READY
    sess.code = code  # even a 1101 left over from the old socket

    assert _run(ticks.clear_all_subscriptions(reason="reconnect", ib=sess.ib)) == 1
    assert old.cancels == [] and sess.ib.cancels == []
    assert ticks.subscribed_symbols() == []

    assert _run(ticks.subscribe("IPDN", ticks.OWNER_SCANNER)) is True
    assert sess.ib.requests == ["IPDN"]
    assert old.requests == ["IPDN"]


def test_only_the_lost_lines_are_cancelled_and_every_one_is_let_go(sess):
    ib = sess.ib
    assert _run(ticks.subscribe("IPDN", ticks.OWNER_HOD)) is True
    assert _run(ticks.subscribe("WHLR", ticks.OWNER_SCANNER)) is True
    # WHLR's line is not in this IB's registry any more (another request replaced it).
    ib.wrapper.subscriptions.subs.pop((43, MKT_DATA))

    sess.code = IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST
    assert _run(ticks.clear_all_subscriptions(reason="1101 restore", ib=ib)) == 2
    assert ib.cancels == ["IPDN"]
    assert ticks.subscribed_symbols() == []


def test_a_cancel_that_raises_is_logged_and_the_line_still_let_go(sess, caplog):
    ib = sess.ib
    assert _run(ticks.subscribe("IPDN", ticks.OWNER_HOD)) is True
    ib.cancel_error = RuntimeError("socket write failed")
    sess.code = IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST

    with caplog.at_level(logging.WARNING, logger="ibkr.ticks_session"):
        assert _run(ticks.clear_all_subscriptions(reason="1101 restore", ib=ib)) == 1
    assert "IPDN" in caplog.text and "raised" in caplog.text
    assert ticks.subscribed_symbols() == []

    ib.cancel_error = None
    assert _run(ticks.subscribe("IPDN", ticks.OWNER_HOD)) is True
    assert ib.requests == ["IPDN", "IPDN"]  # ib_async dropped the entry, so this one is real


def test_ready_settles_the_l1_lines_on_the_session_ib(sess, monkeypatch):
    """``client._on_session_ready`` hands its own IB to the settle, not whatever get_ib says."""
    ib = sess.ib
    assert _run(ticks.subscribe("IPDN", ticks.OWNER_HOD)) is True
    ib.reqMarketDataType = lambda _n: None
    monkeypatch.setattr(client._session_errors, "install_error_hook", lambda _ib: None)
    monkeypatch.setattr(client._session_errors, "reset_session_md_flags", lambda: None)
    sess.code = IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST
    sess.ib = None

    _run(client._on_session_ready(ib, reason="1101 restore generation 2"))
    assert ib.cancels == ["IPDN"]
    assert ticks.subscribed_symbols() == []


def test_the_pinned_ib_async_sends_a_real_request_after_a_1101(sess):
    """The same round trip on ib_async's own IB and registry, with only the socket stubbed."""
    from ib_async import IB

    ib = IB()
    sent: list[tuple[str, int]] = []
    req_ids = iter(range(100, 200))
    ib.client.getReqId = lambda: next(req_ids)
    ib.client.reqMktData = lambda req_id, *_args: sent.append(("reqMktData", req_id))
    ib.client.cancelMktData = lambda req_id: sent.append(("cancelMktData", req_id))

    async def qualify(contract):
        contract.conId = 42
        return [contract]

    ib.qualifyContractsAsync = qualify
    sess.ib = ib
    assert _run(ticks.subscribe("IPDN", ticks.OWNER_HOD)) is True
    assert sent == [("reqMktData", 100)]

    sess.code = IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT
    assert _run(ticks.clear_all_subscriptions(reason="1102 restore", ib=ib)) == 0
    assert sent == [("reqMktData", 100)]

    sess.code = IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST
    assert _run(ticks.clear_all_subscriptions(reason="1101 restore", ib=ib)) == 1
    assert _run(ticks.subscribe("IPDN", ticks.OWNER_HOD)) is True
    assert sent == [("reqMktData", 100), ("cancelMktData", 100), ("reqMktData", 101)]
