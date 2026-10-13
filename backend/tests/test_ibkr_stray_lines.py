"""Lines IBKR answers after Nova cancelled them, and Level 2 lines IBKR refuses (operator report 2026-10-13).

On 2026-10-13 IBKR granted five Level 2 lines after Nova had cancelled them (its 2152 notice
arrived with no contract: ib_async had already let the request go), and those grants held all 3
of the login's Level 2 lines through every Nova restart. Four cancelled Time & Sales lines kept
printing (47,749 prints on request ids Nova no longer knew). And a refused line (309) sat on the
ladder as "Waiting for book data..." for good.

These tests drive the pinned ib_async's own IB, registry, decoder and error path, with only the
socket stubbed. On the live Gateway that evening a second cancel did not free a Level 2 line granted
after Nova's cancel; ``ibkr/depth/release.py`` keeps that from happening (``test_depth_release.py``).
"""
from __future__ import annotations

import asyncio
import importlib
import logging

import pytest
from ib_async import IB, Stock

from constants_ibkr import (
    IBKR_DEPTH_SMART,
    IBKR_ERROR_DEPTH_MAX_LINES,
    IBKR_NOTICE_DEPTH_EXCHANGES,
    IBKR_STRAY_LINE_RECANCEL_SEC,
)
from ibkr import stray_lines

GRANT_TEXT = "Exchanges - Depth: NASDAQ; IEX; Top: BYX; Need additional market data permission"
REFUSED_TEXT = "Max number (3) of market depth requests has been reached"


class _Clock:
    def __init__(self, start: float = 1_791_900_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(stray_lines.time, "time", c)
    return c


@pytest.fixture(autouse=True)
def _clean():
    stray_lines.reset_for_tests()
    yield
    stray_lines.reset_for_tests()


def _ib() -> tuple[IB, dict[str, list]]:
    """A real IB whose requests go nowhere; every cancel it sends is recorded."""
    ib = IB()
    sent: dict[str, list] = {"depth": [], "depth_cancel": [], "tape": [], "tape_cancel": []}
    seq = iter(range(100, 10_000))
    ib.client.getReqId = lambda: next(seq)
    ib.client.reqMktDepth = lambda reqId, *a: sent["depth"].append(reqId)
    ib.client.cancelMktDepth = lambda reqId, smart: sent["depth_cancel"].append((reqId, smart))
    ib.client.reqTickByTickData = lambda reqId, *a: sent["tape"].append(reqId)
    ib.client.cancelTickByTickData = lambda reqId: sent["tape_cancel"].append(reqId)
    return ib, sent


def _stock(symbol: str, con_id: int) -> Stock:
    contract = Stock(symbol, "SMART", "USD")
    contract.conId = con_id
    return contract


def _print(ib: IB, req_id: int) -> None:
    """One tickByTick AllLast message through ib_async's own decoder (msg 99, tick type 2)."""
    ib.client.decoder.tickByTick(["99", str(req_id), "2", "1791900000", "6.20", "100", "0", "NASDAQ", ""])


# ── Time & Sales: prints on a line Nova cancelled ─────────────────────────────


def _cancelled_tape_line(ib: IB, sent: dict, symbol: str = "NB", con_id: int = 620917098) -> int:
    contract = _stock(symbol, con_id)
    ib.reqTickByTickData(contract, "AllLast")
    req_id = sent["tape"][-1]
    stray_lines.note_cancelled(stray_lines.TAPE, req_id, symbol)
    ib.cancelTickByTickData(contract, "AllLast")
    assert sent["tape_cancel"] == [req_id]
    return req_id


def test_prints_on_a_cancelled_time_and_sales_line_cancel_it_again(clock, caplog):
    ib, sent = _ib()
    stray_lines.install(ib)
    req_id = _cancelled_tape_line(ib, sent)

    clock.now += 21  # NB 2026-10-13: cancelled 08:53:46, IBKR printed to it from 08:54:07 to 11:19
    with caplog.at_level(logging.WARNING):
        for _ in range(50):
            _print(ib, req_id)
    assert sent["tape_cancel"] == [req_id, req_id]  # one more, not fifty
    assert stray_lines.view()["recancelled"] == {"tape": 1}
    assert stray_lines.view()["last"]["symbol"] == "NB"
    assert "Unknown reqId" not in caplog.text  # the print is dropped, not logged fifty times
    assert "kept printing NB's Time & Sales" in caplog.text


def test_a_print_already_on_its_way_when_nova_cancelled_is_not_a_kept_line(clock):
    ib, sent = _ib()
    stray_lines.install(ib)
    req_id = _cancelled_tape_line(ib, sent)
    clock.now += 0.2
    _print(ib, req_id)
    assert sent["tape_cancel"] == [req_id]


def test_prints_on_a_request_id_nova_never_made_are_cancelled():
    ib, sent = _ib()
    stray_lines.install(ib)
    _print(ib, 277146)
    assert sent["tape_cancel"] == [277146]


def test_prints_on_a_live_line_still_reach_its_ticker_through_every_override(clock):
    from ibkr import tape_exchange_time

    ib, sent = _ib()
    tape_exchange_time.install(ib)
    stray_lines.install(ib)
    assert stray_lines.install(ib) is True  # idempotent
    ticker = ib.reqTickByTickData(_stock("JBDI", 896717191), "AllLast")
    _print(ib, sent["tape"][-1])
    assert ticker.last == 6.20
    assert tape_exchange_time.exchange_second(ticker.tickByTicks[-1]) == 1791900000
    assert sent["tape_cancel"] == []


# ── Level 2: IBKR refuses the line (309) ──────────────────────────────────────


@pytest.fixture
def depth(monkeypatch):
    """The depth facade on a real IB; IB-loop callbacks run inline."""
    import ibkr.client as client_mod
    import ibkr.depth as depth_mod
    from ibkr import loop_supervisor

    importlib.reload(depth_mod)
    depth_mod.reset_all()
    ib, sent = _ib()
    con_ids = {"JBDI": 896717191, "BKYI": 878361947, "PFAI": 779062950, "ABLV": 649166469}

    async def qualify(contract):
        contract.conId = con_ids[contract.symbol]
        return [contract]

    ib.qualifyContractsAsync = qualify
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "is_ready", lambda: True)
    monkeypatch.setattr(client_mod, "get_ib", lambda: ib)
    monkeypatch.setattr(loop_supervisor, "publish_to_http", lambda cb, *a, **k: cb(*a, **k))
    depth_mod._subscribe_lock = None
    yield depth_mod, ib, sent
    depth_mod.reset_all()


def _subscribe(depth_mod, symbol: str) -> dict:
    return asyncio.run(depth_mod.subscribe_async(symbol))


def test_a_refused_level_2_line_is_not_open_and_its_ladder_is_told_why(depth):
    depth_mod, ib, sent = depth
    assert _subscribe(depth_mod, "JBDI")["ok"] is True
    req_id = sent["depth"][-1]
    queue = depth_mod.open_viewer_queue("JBDI")

    ib.wrapper.error(req_id, IBKR_ERROR_DEPTH_MAX_LINES, REFUSED_TEXT, "")

    frame = queue.get_nowait()
    assert frame["type"] == "error" and frame["evicted"] is True
    assert "Nova holds none of them" in frame["message"]
    assert "restarting IB Gateway frees them" in frame["message"]
    assert depth_mod.refusal("JBDI") == frame["message"]
    assert depth_mod.is_subscribed("JBDI") is False
    assert depth_mod.needs_subscribe("JBDI") is True
    assert sent["depth_cancel"] == []  # IBKR never opened it: nothing to cancel

    # ib_async let the refused request go, so asking again is a real request.
    assert _subscribe(depth_mod, "JBDI")["ok"] is True
    assert len(sent["depth"]) == 2
    assert depth_mod.refusal("JBDI") is None


def test_the_refusal_names_novas_own_lines_when_they_fill_the_cap(depth):
    depth_mod, ib, sent = depth
    for symbol in ("BKYI", "PFAI", "ABLV"):
        assert _subscribe(depth_mod, symbol)["ok"] is True
    from ibkr.depth.subscribe import refusal_message

    message = refusal_message("JBDI")
    assert "(BKYI, PFAI, ABLV)" in message and "Close one" in message
    assert "IB Gateway" not in message


def test_a_refusal_of_an_older_request_leaves_the_newer_line_alone(depth):
    depth_mod, ib, sent = depth
    assert _subscribe(depth_mod, "JBDI")["ok"] is True
    first = sent["depth"][-1]
    ib.wrapper.error(first, IBKR_NOTICE_DEPTH_EXCHANGES, GRANT_TEXT, "")  # granted, so letting go cancels it
    depth_mod.unsubscribe("JBDI")
    assert _subscribe(depth_mod, "JBDI")["ok"] is True
    assert sent["depth"][-1] != first
    ib.wrapper.error(first, IBKR_ERROR_DEPTH_MAX_LINES, REFUSED_TEXT, "")
    assert depth_mod.is_subscribed("JBDI") is True


def test_a_level_2_line_nova_lets_go_before_ibkr_answers_is_cancelled_on_the_grant(depth, clock):
    """BKYI: let go 0.75 s in, granted 2.2 s in. The cancel waits for the grant, so nothing is held."""
    depth_mod, ib, sent = depth
    assert _subscribe(depth_mod, "BKYI")["ok"] is True
    req_id = sent["depth"][-1]
    depth_mod.unsubscribe("BKYI")
    assert sent["depth_cancel"] == []

    clock.now += 2.2
    ib.wrapper.error(req_id, IBKR_NOTICE_DEPTH_EXCHANGES, GRANT_TEXT, "")
    assert sent["depth_cancel"] == [(req_id, IBKR_DEPTH_SMART)]  # after the grant: the order that frees it


def test_a_ladder_whose_line_was_refused_before_its_socket_was_ready_hears_why(monkeypatch):
    """The 309 lands while the socket is still opening: it says why and closes, never beats."""
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    from ibkr import depth as _depth
    from l2 import continuous
    from main import app

    async def not_idle(_symbol):
        return False

    why = "IBKR refused this Level 2 (IB error 309): all 3 of its Level 2 lines are in use"
    monkeypatch.setattr(_depth, "needs_subscribe", lambda _s: False)
    monkeypatch.setattr(_depth, "refusal", lambda _s: why)
    monkeypatch.setattr(_depth, "release_when_idle", not_idle)
    monkeypatch.setattr(continuous, "start", lambda _s: None)
    with TestClient(app).websocket_connect("/ws/ibkr/depth/JBDI") as ws:
        assert ws.receive_json() == {"type": "error", "symbol": "JBDI", "message": why, "evicted": True}
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
