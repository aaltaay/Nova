"""The lent lines on the wire (ADR 044 decision 6): GET /api/ibkr/depth/lines, PATCH
/api/ibkr/depth/lending, and the lender's /ws/ibkr/depth/{symbol} and /ws/ibkr/tape/{symbol} sockets."""
from __future__ import annotations

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from line_lending import loans, sockets
from sensors import focus_store
from tests.bot_helpers import headers, ready_l2
from tests.line_lending_desk import Lane, install, line_loan_lines, window

KEY = "lending-test-key"


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


@pytest.fixture
def lent(desk):
    """ABC (hidden) lent its line to AISP's first pullback near its trigger; DEF is in front, GHI hidden."""
    ready_l2(brain=None, heartbeat=False, symbols=("AISP",), depth_line=False)
    desk.lanes = [Lane("first_pullback", near=("AISP",))]
    now = time.time()
    for sym in ("ABC", "DEF", "GHI"):
        desk.tab_line(sym)
    focus_store.record_window(window("DEF", ["ABC", "DEF", "GHI"]), now=now)
    asyncio.run(loans.tick(now))
    loans._lock = None                                    # the app's loop makes its own
    assert loans.lenders() == ["ABC"]
    return desk


@pytest.fixture
def depth_socket(monkeypatch):
    from ibkr import depth as _depth
    from l2 import continuous

    async def not_idle(_symbol):
        return False

    monkeypatch.setattr(_depth, "needs_subscribe", lambda _s: False)
    monkeypatch.setattr(_depth, "current_book", lambda _s: None)
    monkeypatch.setattr(_depth, "release_when_idle", not_idle)
    monkeypatch.setattr(continuous, "start", lambda _s: None)


def test_the_lines_view_says_who_holds_each_line_and_the_loans(lent):
    from main import app

    body = TestClient(app).get("/api/ibkr/depth/lines").json()
    print("LINES VIEW", json.dumps(body))
    assert body["schema_version"] == 1 and body["cap"] == 3
    assert [(r["symbol"], r["held_by"], r["front"], r["viewers"]) for r in body["lines"]] == [
        ("AISP", "loan", False, 1), ("DEF", "tab", True, 1), ("GHI", "tab", False, 1)]
    (loan,) = body["lending"]["loans"]
    assert body["lending"]["on"] is True and body["lending"]["recent"] == []
    assert {k: loan[k] for k in ("lender", "borrower", "setup_type", "why")} == {
        "lender": "ABC", "borrower": "AISP", "setup_type": "first_pullback", "why": "near its trigger"}
    assert isinstance(loan["since"], float)


def test_switching_lending_off_answers_the_view_with_every_loan_ended(lent, monkeypatch):
    from main import app

    monkeypatch.setenv("NOVA_API_KEY", KEY)
    client = TestClient(app)
    assert client.patch("/api/ibkr/depth/lending", json={"on": False}).status_code == 401
    assert loans.lenders() == ["ABC"]
    body = client.patch("/api/ibkr/depth/lending", json={"on": False}, headers=headers(KEY)).json()
    assert body["lending"]["on"] is False and body["lending"]["loans"] == []
    assert body["lending"]["recent"][0]["end"] == "lending_off"
    assert [r["symbol"] for r in body["lines"]] == ["DEF", "GHI"]
    assert line_loan_lines()[-1]["inputs"]["end"] == "lending_off"
    assert client.patch("/api/ibkr/depth/lending", json={"on": "no"}, headers=headers(KEY)).status_code == 422
    assert client.patch("/api/ibkr/depth/lending", json={"on": True}, headers=headers(KEY)).json()["lending"]["on"]


def test_a_hidden_tabs_socket_meets_the_lent_frame_and_closes(lent, depth_socket):
    from main import app

    with TestClient(app).websocket_connect("/ws/ibkr/depth/ABC?tab=1&front=0") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "lent" and frame["to"]["symbol"] == "AISP"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert loans.lenders() == ["ABC"]


def test_the_tab_in_front_recalls_the_loan_and_gets_its_line(lent, depth_socket):
    from main import app

    with TestClient(app).websocket_connect("/ws/ibkr/depth/ABC?tab=1&front=1") as ws:
        assert ws.receive_json()["type"] == "subscribed"
    assert loans.lenders() == [] and "AISP" in lent.unsubscribed
    end = line_loan_lines()[-1]
    assert end["inputs"] == {"lender": "ABC", "borrower": "AISP", "setup_type": "first_pullback",
                             "setup_id": "AISP-2026-10-01-1", "end": "recalled", "tape_lent": True}


def test_a_standing_socket_reads_the_lent_frame_and_closes(desk, depth_socket, monkeypatch):
    from ibkr import depth as _depth
    from main import app

    frame = {"type": "lent", "symbol": "XYZ", "to": {"symbol": "AISP", "setup_type": "first_pullback",
                                                       "setup_id": "AISP-1"}, "since": 1.0, "text": "lent"}

    async def stream(_queue, timeout=1.0):
        yield frame

    monkeypatch.setattr(_depth, "stream", stream)
    with TestClient(app).websocket_connect("/ws/ibkr/depth/XYZ?tab=1") as ws:
        assert ws.receive_json()["type"] == "subscribed"
        got = ws.receive_json()
        while got["type"] == "book_watch":                # the book watcher's word rides beside the books
            got = ws.receive_json()
        assert got == frame
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert sockets.count("XYZ") == 0                      # the socket left the lending registry with its viewer


def test_a_trader_tabs_socket_is_registered_as_a_tab(desk, depth_socket, monkeypatch):
    from ibkr import depth as _depth
    from main import app

    seen: dict[str, int] = {}

    async def stream(_queue, timeout=1.0):
        seen["tabs"] = sockets.tab_count("XYZ")
        seen["all"] = sockets.count("XYZ")
        return
        yield  # an async generator, like the real stream

    monkeypatch.setattr(_depth, "stream", stream)
    with TestClient(app).websocket_connect("/ws/ibkr/depth/XYZ?tab=1&front=0") as ws:
        assert ws.receive_json()["type"] == "subscribed"
    assert seen == {"tabs": 1, "all": 1}
    assert sockets.count("XYZ") == 0


# -- the lender's Time & Sales socket -------------------------------------------------------
@pytest.fixture
def tape_socket(monkeypatch):
    from routes import trading_tape_ws

    monkeypatch.setattr(trading_tape_ws, "desk_connected", lambda: True)


def test_a_hidden_tabs_time_and_sales_meets_the_lent_frame_and_closes(lent, tape_socket):
    from main import app

    with TestClient(app).websocket_connect("/ws/ibkr/tape/ABC?tab=1&front=0") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "lent" and frame["symbol"] == "ABC" and frame["to"]["symbol"] == "AISP"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert loans.lenders() == ["ABC"] and "ABC" not in lent.tape


def test_the_tab_in_front_recalls_both_lines_from_its_time_and_sales(lent, tape_socket, monkeypatch):
    from ibkr import tape_stream
    from main import app

    async def quiet(_queue):
        return
        yield  # an async generator, like the real stream

    monkeypatch.setattr(tape_stream, "stream_batches", quiet)
    with TestClient(app).websocket_connect("/ws/ibkr/tape/ABC?tab=1&front=1") as ws:
        assert ws.receive_json()["type"] == "subscribed"
    assert loans.lenders() == [] and "AISP" in lent.unsubscribed
    assert ("AISP", "the loan of its line ended") in lent.tape_dropped and "ABC" in lent.tape
    assert line_loan_lines()[-1]["inputs"]["end"] == "recalled"


def test_a_standing_time_and_sales_reads_the_lent_frame_and_closes(desk, tape_socket, monkeypatch):
    from ibkr import tape_stream
    from main import app

    desk.tape["XYZ"] = 0
    frame = {"type": "lent", "symbol": "XYZ", "to": {"symbol": "AISP", "setup_type": "first_pullback",
                                                       "setup_id": "AISP-1"}, "since": 1.0, "text": "lent"}

    async def stream(_queue):
        yield [frame]  # one batch: what the viewer had waiting (ADR 045)

    monkeypatch.setattr(tape_stream, "stream_batches", stream)
    with TestClient(app).websocket_connect("/ws/ibkr/tape/XYZ?tab=1") as ws:
        assert ws.receive_json()["type"] == "subscribed"
        assert ws.receive_json() == frame
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert sockets.count("XYZ", sockets.TAPE) == 0        # the socket left the registry with its viewer
