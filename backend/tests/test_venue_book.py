"""The brain's Nasdaq book (ADR 072 Amendment 5): a Level 2 request on the exchange itself, beside the all-exchange
line of the same stock, kept as its own book; it follows the brain's lane only while a Level 2 line is free, and its
request is never cancelled before IBKR answered it."""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from constants_ibkr import (
    IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT,
    IBKR_ERROR_DEPTH_MAX_LINES,
    IBKR_ERROR_DEPTH_RESET,
    IBKR_NOTICE_DEPTH_EXCHANGES,
)
from constants_venue_book import IBKR_VENUE_BOOK_ROWS
from ibkr import venue_book
from ibkr.venue_book import line
from line_lanes import lanes
from line_lanes.table import BRAIN, CLAUDE, YOU
from market_view.viewer_queues import BookVersion

CON_ID = 4242
INSERT, UPDATE, DELETE = 0, 1, 2
BID, ASK = 1, 0
DATA_LOST = 1101


def _new_ib(monkeypatch, first_req: int):
    """A real ib_async ``IB`` (its own subscription registry and wrapper), with the socket calls recorded."""
    from ib_async import IB

    ib = IB()
    ib.sent = []
    ids = iter(range(first_req, first_req + 1000))
    monkeypatch.setattr(ib.client, "getReqId", lambda: next(ids))
    monkeypatch.setattr(ib.client, "reqMktDepth", lambda req, contract, rows, smart, opts=None: ib.sent.append(("ask", req, contract.exchange, rows, smart)))
    monkeypatch.setattr(ib.client, "cancelMktDepth", lambda req, smart: ib.sent.append(("cancel", req, smart)))

    async def qualify(contract):
        contract.conId = CON_ID
        return [contract]

    monkeypatch.setattr(ib, "qualifyContractsAsync", qualify)
    return ib


@pytest.fixture
def ib(monkeypatch):
    from ibkr import client, session_errors
    from sim import mode

    ib = _new_ib(monkeypatch, 900)
    desk = {"ib": ib, "ready": True, "generation": 7, "connectivity": None}
    ib.desk = desk
    monkeypatch.setattr(client, "is_ready", lambda: desk["ready"])
    monkeypatch.setattr(client, "get_ib", lambda: desk["ib"] if desk["ready"] else None)
    monkeypatch.setattr(client, "current_generation", lambda: desk["generation"])
    monkeypatch.setattr(session_errors, "last_connectivity_code", lambda: desk["connectivity"])
    monkeypatch.setattr(mode, "is_replay_desk", lambda: False)
    venue_book.reset_for_tests()
    yield ib
    venue_book.reset_for_tests()


def _rows(ib, req, rows, side):
    for pos, (price, size, mm) in enumerate(rows):
        ib.wrapper.updateMktDepthL2(req, pos, mm, INSERT, side, price, size, False)


class _Read:
    """One TCP read as ib_async runs it: the last read's row operations are dropped, this one's reach each ticker."""

    def __init__(self, ib) -> None:
        self.ib = ib

    def __enter__(self):
        self.ib.wrapper.tcpDataArrived()
        return self.ib

    def __exit__(self, *exc) -> None:
        self.ib.wrapper.tcpDataProcessed()


def _asks(ib) -> list[tuple]:
    return [s for s in ib.sent if s[0] == "ask" and s[2] == "NASDAQ"]


def _cancels(ib) -> list[tuple]:
    return [s for s in ib.sent if s[0] == "cancel"]


def _open(ib, sym: str = "CUE", *, granted: bool = True) -> int:
    """Ask for ``sym``'s book; ``granted``: IBKR's first row has arrived. The request id."""
    asyncio.run(venue_book.follow(sym))
    req = _asks(ib)[-1][1]
    if granted:
        with _Read(ib):
            _rows(ib, req, [(4.03, 255.0, "NSDQ")], BID)
    return req


def test_nasdaqs_book_opens_beside_the_all_exchange_line_of_the_same_stock(ib):
    from ib_async import Stock

    smart = Stock("CUE", "SMART", "USD")
    smart.conId = CON_ID
    all_venues = ib.reqMktDepth(smart, numRows=10, isSmartDepth=True)       # the lane's own Level 2 line
    assert ib.reqMktDepth(smart, numRows=20, isSmartDepth=False) is all_venues, "ib_async keeps one Level 2 line a contract id"
    st = asyncio.run(venue_book.follow("cue"))
    assert st == {"venue": "NASDAQ", "symbol": "CUE", "up": True, "rows": False, "seq": 0, "at": None, "error": None}
    assert ib.sent == [("ask", 900, "SMART", 10, True), ("ask", 901, "NASDAQ", IBKR_VENUE_BOOK_ROWS, False)]
    q = venue_book.open_viewer("CUE")
    with _Read(ib):
        _rows(ib, 901, [(4.03, 255.0, ""), (4.02, 125.0, "NSDQ"), (4.02, 100.0, "ETMM")], BID)
        _rows(ib, 901, [(4.10, 100.0, "NSDQ"), (4.11, 200.0, "")], ASK)
        ib.wrapper.updateMktDepthL2(900, 0, "ARCA", INSERT, BID, 4.04, 700.0, True)   # the all-exchange line's own row
    book = venue_book.current("CUE")
    assert [(r["price"], r["size"], r["mm"]) for r in book["bids"]] == [(4.03, 255.0, ""), (4.02, 125.0, "NSDQ"), (4.02, 100.0, "ETMM")]
    assert [(r["price"], r["side"]) for r in book["asks"]] == [(4.10, "ask"), (4.11, "ask")]
    assert [(t.price, t.marketMaker) for t in all_venues.domTicks] == [(4.04, "ARCA")], "each request's rows reach its own ticker"
    frame = q.get_nowait()
    assert isinstance(frame, BookVersion) and frame.seq == 1 and frame.book is book
    with _Read(ib):                                                                # a size rewritten to the same size: no new frame
        ib.wrapper.updateMktDepthL2(901, 0, "", UPDATE, BID, 4.03, 255.0, False)
    assert q.empty() and venue_book.status()["seq"] == 1 and venue_book.status()["rows"] is True
    asyncio.run(venue_book.follow(None))                                           # the Nasdaq request's cancel is its own
    assert _cancels(ib) == [("cancel", 901, False)]
    assert ib.wrapper.subscriptions.find_market_data(CON_ID, "mktDepth") is not None, "the lane's own line is untouched"


def test_rows_follow_ibkrs_insert_update_delete_and_stop_at_twenty(ib):
    req = _open(ib, granted=False)
    with _Read(ib):
        _rows(ib, req, [(round(5.00 - i / 100, 2), 100.0 + i, "NSDQ") for i in range(IBKR_VENUE_BOOK_ROWS)], BID)
    with _Read(ib):
        ib.wrapper.updateMktDepthL2(req, 0, "", INSERT, BID, 5.01, 900.0, False)  # a better bid: every row moves down, the last falls off
        ib.wrapper.updateMktDepthL2(req, 1, "NSDQ", UPDATE, BID, 5.00, 50.0, False)
        ib.wrapper.updateMktDepthL2(req, 2, "", DELETE, BID, 0.0, 0.0, False)
    bids = venue_book.current("CUE")["bids"]
    assert [(r["price"], r["size"]) for r in bids[:3]] == [(5.01, 900.0), (5.00, 50.0), (4.98, 102.0)]
    assert len(bids) == IBKR_VENUE_BOOK_ROWS - 1 and [r["price"] for r in bids] == sorted((r["price"] for r in bids), reverse=True)


def test_ibkrs_reset_empties_the_book_and_its_refusal_ends_the_line_in_words(ib):
    req = _open(ib)
    ib.errorEvent.emit(req + 50, IBKR_ERROR_DEPTH_MAX_LINES, "another request's refusal", None)
    ib.errorEvent.emit(req, 2104, "Market data farm connection is OK", None)         # a notice, not a refusal
    assert venue_book.is_up("CUE")
    with _Read(ib):                                                                  # one read: an old row, the reset, the new book
        ib.wrapper.updateMktDepthL2(req, 1, "NSDQ", INSERT, BID, 4.02, 111.0, False)
        ib.errorEvent.emit(req, IBKR_ERROR_DEPTH_RESET, "Market depth data has been RESET", None)
        _rows(ib, req, [(4.05, 300.0, "NSDQ")], BID)
    assert [(r["price"], r["size"]) for r in venue_book.current("CUE")["bids"]] == [(4.05, 300.0)]
    q = venue_book.open_viewer("CUE")
    ib.errorEvent.emit(req, IBKR_ERROR_DEPTH_MAX_LINES, "Max number (3) of market depth requests has been reached", None)
    st = venue_book.status()
    assert st["up"] is False and st["symbol"] == "CUE" and "All 3 Level 2 lines are in use" in st["error"]
    assert q.get_nowait()["type"] == "closed" and venue_book.current("CUE") is None
    assert _cancels(ib) == [] and venue_book.held() == [], "IBKR holds nothing for a refused request"
    asyncio.run(venue_book.follow("CUE", now=time.time() + 1))                       # not asked again at once
    assert len(_asks(ib)) == 1
    asyncio.run(venue_book.follow("CUE", now=time.time() + 60))
    assert len(_asks(ib)) == 2 and venue_book.is_up("CUE")


def test_a_request_ibkr_has_not_answered_is_never_cancelled(ib):
    """ibkr/depth/release.py's rule: a Level 2 request cancelled before its grant can stay held inside IB Gateway."""
    first = _open(ib, "CUE", granted=False)
    st = asyncio.run(venue_book.follow("MPU"))                                       # the brain's lane moved before IBKR answered
    assert _cancels(ib) == [] and venue_book.held() == ["CUE"]
    assert len(_asks(ib)) == 1 and st["up"] is False and "Waiting for IBKR to answer" in st["error"]
    with _Read(ib):                                                                  # IBKR grants the old request: now it is cancelled
        _rows(ib, first, [(4.03, 255.0, "NSDQ")], BID)
    assert _cancels(ib) == [("cancel", first, False)] and venue_book.held() == []
    assert venue_book.current("MPU") is None, "a held request's rows are nobody's book"
    asyncio.run(venue_book.follow("MPU", now=time.time() + 60))
    assert [a[1] for a in _asks(ib)] == [first, first + 1] and venue_book.is_up("MPU")


def test_an_unanswered_request_is_taken_back_and_one_ibkr_refuses_is_forgotten(ib):
    first = _open(ib, "CUE", granted=False)
    asyncio.run(venue_book.follow(None))
    assert venue_book.held() == ["CUE"] and _cancels(ib) == []
    asyncio.run(venue_book.follow("CUE"))                                            # wanted again: the request still out carries on
    assert len(_asks(ib)) == 1 and venue_book.held() == [] and venue_book.is_up("CUE")
    with _Read(ib):
        _rows(ib, first, [(4.03, 255.0, "NSDQ")], BID)
    assert venue_book.current("CUE")["bids"][0]["price"] == 4.03 and _cancels(ib) == []
    asyncio.run(venue_book.follow(None))                                             # granted now: the cancel goes out at once
    assert _cancels(ib) == [("cancel", first, False)]
    second = _open(ib, "MPU", granted=False)
    asyncio.run(venue_book.follow(None))
    ib.errorEvent.emit(second, IBKR_ERROR_DEPTH_MAX_LINES, "Max number (3) of market depth requests has been reached", None)
    assert venue_book.held() == [] and len(_cancels(ib)) == 1, "a refused held request is forgotten, never cancelled"
    third = _open(ib, "HIHO", granted=False)
    ib.errorEvent.emit(third, IBKR_NOTICE_DEPTH_EXCHANGES, "Exchanges - Depth: NASDAQ", None)   # IBKR's grant notice, before any row
    asyncio.run(venue_book.follow(None))
    assert _cancels(ib)[-1] == ("cancel", third, False) and venue_book.held() == []


def test_a_cancel_that_cannot_be_sent_leaves_the_request_held_and_is_sent_again(ib, monkeypatch):
    req = _open(ib)
    calls = {"n": 0}

    def flaky(r, smart):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("socket busy")
        ib.sent.append(("cancel", r, smart))

    monkeypatch.setattr(ib.client, "cancelMktDepth", flaky)
    asyncio.run(venue_book.follow(None))
    assert venue_book.held() == ["CUE"] and _cancels(ib) == []
    assert ib.wrapper.subscriptions.find_market_data(CON_ID, line.KIND) is not None, "ib_async still holds the request"
    asyncio.run(venue_book.follow(None))                                             # the next look sends it
    assert _cancels(ib) == [("cancel", req, False)] and venue_book.held() == []


def test_nothing_is_cancelled_while_ibkr_is_not_ready_even_when_the_answer_arrives_then(ib):
    """A degraded session keeps its generation until the next READY: the readiness itself is asked."""
    req = _open(ib, granted=False)
    asyncio.run(venue_book.follow(None))
    assert venue_book.held() == ["CUE"]
    ib.desk["ready"] = False                                                         # degraded: same socket, same generation
    with _Read(ib):
        _rows(ib, req, [(4.03, 255.0, "NSDQ")], BID)                                 # the grant arrives during the outage
    assert _cancels(ib) == [] and venue_book.held() == ["CUE"], "the request stays tracked"
    assert ib.wrapper.subscriptions.find_market_data(CON_ID, line.KIND) is not None
    asyncio.run(venue_book.follow(None))
    assert _cancels(ib) == [] and venue_book.held() == ["CUE"]
    ib.desk["ready"] = True                                                          # READY again: decided now
    asyncio.run(venue_book.follow(None))
    assert _cancels(ib) == [("cancel", req, False)] and venue_book.held() == []
    second = _open(ib, "MPU")                                                        # and a granted line let go while not ready
    ib.desk["ready"] = False
    asyncio.run(venue_book.follow(None))
    assert len(_cancels(ib)) == 1 and venue_book.held() == ["MPU"]
    ib.desk["ready"] = True
    asyncio.run(venue_book.follow(None))
    assert _cancels(ib)[-1] == ("cancel", second, False) and venue_book.held() == []


def test_the_book_moves_with_the_brain_and_gives_its_line_back(ib):
    first = _open(ib, "CUE")
    second = _open(ib, "MPU")                                                        # the brain's lane moved
    assert ib.sent[-2:] == [("cancel", first, False), ("ask", second, "NASDAQ", IBKR_VENUE_BOOK_ROWS, False)]
    assert venue_book.is_up("MPU") and not venue_book.is_up("CUE")
    st = asyncio.run(venue_book.follow("MPU", room=False))                           # a lane needs the line
    assert st["up"] is False and "waits for one" in st["error"] and ib.sent[-1] == ("cancel", second, False)
    asyncio.run(venue_book.follow("MPU"))
    assert venue_book.is_up("MPU")
    _rows(ib, _asks(ib)[-1][1], [(2.5, 100.0, "NSDQ")], BID)
    asyncio.run(venue_book.follow(None))
    assert venue_book.status() == {"venue": "NASDAQ", "symbol": None, "up": False, "rows": False, "seq": 0, "at": None, "error": None}


def test_a_line_ibkr_kept_through_a_restore_lives_on_and_is_not_asked_twice(ib):
    """1102: the same socket, its data kept. The generation moves, the request does not."""
    req = _open(ib)
    ib.desk["generation"] += 1
    ib.desk["connectivity"] = IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT
    assert venue_book.symbol() is None                                               # not counted until it is settled
    asyncio.run(venue_book.follow("CUE"))
    assert venue_book.is_up("CUE") and len(_asks(ib)) == 1 and _cancels(ib) == []
    with _Read(ib):
        ib.wrapper.updateMktDepthL2(req, 0, "NSDQ", UPDATE, BID, 4.03, 999.0, False)
    assert venue_book.current("CUE")["bids"][0]["size"] == 999.0


def test_a_line_ibkr_lost_is_cancelled_if_answered_and_a_dropped_sockets_is_forgotten(ib, monkeypatch):
    first = _open(ib)
    ib.desk["generation"] += 1
    ib.desk["connectivity"] = DATA_LOST                                              # the same socket, IBKR forgot the line
    q = venue_book.open_viewer("CUE")
    asyncio.run(venue_book.follow("CUE"))
    assert ib.sent[-2:] == [("cancel", first, False), ("ask", first + 1, "NASDAQ", IBKR_VENUE_BOOK_ROWS, False)]
    assert q.get_nowait()["reason"] == "its IBKR session ended" and venue_book.is_up("CUE")
    with _Read(ib):
        _rows(ib, first + 1, [(4.0, 10.0, "NSDQ")], BID)
    ib.desk["ready"] = False                                                         # IBKR's connection lost: nothing is decided or sent
    ib.desk["generation"] += 1
    sent = len(ib.sent)
    st = asyncio.run(venue_book.follow("CUE"))
    assert len(ib.sent) == sent and st["up"] is False
    new = _new_ib(monkeypatch, 100)                                                  # a new socket: the old request died with it
    ib.desk.update(ib=new, ready=True)
    asyncio.run(venue_book.follow("CUE", now=time.time() + 60))
    assert len(ib.sent) == sent, "nothing is cancelled on a socket that dropped"
    assert _asks(new) == [("ask", 100, "NASDAQ", IBKR_VENUE_BOOK_ROWS, False)] and venue_book.is_up("CUE")


def test_no_book_on_a_replaying_desk_or_before_ibkr_is_ready(ib, monkeypatch):
    from sim import mode

    req = _open(ib)
    q = venue_book.open_viewer("CUE")
    monkeypatch.setattr(mode, "is_replay_desk", lambda: True)                        # the desk goes to a recorded session
    st = asyncio.run(venue_book.follow("CUE"))
    assert st["up"] is False and "replaying" in st["error"] and _cancels(ib) == [("cancel", req, False)]
    assert q.get_nowait()["type"] == "closed" and venue_book.current("CUE") is None
    asyncio.run(venue_book.follow("CUE", now=time.time() + 60))
    assert len(_asks(ib)) == 1, "no live book is asked for while replaying"
    monkeypatch.setattr(mode, "is_replay_desk", lambda: False)
    ib.desk["ready"] = False
    assert asyncio.run(venue_book.follow("CUE", now=time.time() + 120))["error"] == "IBKR is not connected."
    assert len(_asks(ib)) == 1


class _Lines:
    def __init__(self, log: list, kind: str) -> None:
        self.up: set[str] = set()
        self.log, self.kind = log, kind

    async def subscribe_async(self, symbol: str, **_kw) -> dict:
        self.log.append((self.kind, "ask", symbol))
        self.up.add(symbol)
        return {"ok": True, "error": None}

    def end(self, symbol: str, *_a) -> bool:
        self.up.discard(symbol)
        return True


@pytest.fixture
def desk(monkeypatch):
    """The lanes over stand-in lines; the Nasdaq book's own calls are recorded in the same log."""
    from ibkr import depth, tape_line, tape_stream
    from l2 import continuous

    log: list = []
    book, tape = _Lines(log, "level2"), _Lines(log, "tape")
    for mod, lines in ((depth, book), (tape_stream, tape)):
        monkeypatch.setattr(mod, "subscribe_async", lines.subscribe_async)
        for name in ("ws_viewer_opened", "forget_viewers"):
            monkeypatch.setattr(mod, name, lambda s: None)
        monkeypatch.setattr(mod, "push_lane", lambda s, m, lane: None)
    monkeypatch.setattr(depth, "is_live", lambda s: s in book.up)
    monkeypatch.setattr(depth, "is_subscribed", lambda s: s in book.up)
    monkeypatch.setattr(depth, "unsubscribe", book.end)
    monkeypatch.setattr(tape_stream, "is_subscribed", lambda s: s in tape.up)
    monkeypatch.setattr(tape_line, "drop_line", tape.end)
    monkeypatch.setattr(continuous, "start", lambda s: {"ok": True})
    monkeypatch.setattr(continuous, "stop", lambda s: None)
    state = {"on": None}

    async def follow(sym, *, room=True, now=None):
        state["on"] = sym if room else None
        log.append(("nasdaq", "follow", sym, room))
        return {}

    def close(reason=""):
        log.append(("nasdaq", "close", state["on"]))
        state["on"] = None

    monkeypatch.setattr(venue_book, "follow", follow)
    monkeypatch.setattr(venue_book, "close", close)
    monkeypatch.setattr(venue_book, "symbol", lambda: state["on"])
    lanes.reset_for_tests()
    yield log
    lanes.reset_for_tests()


def test_the_book_follows_the_brains_lane_and_yields_before_a_lane_needs_the_third_line(desk):
    log = desk

    async def run():
        await lanes.put(BRAIN, "CUE")
        assert log[-1] == ("nasdaq", "follow", "CUE", True) and lanes.venue_room()
        await lanes.put(YOU, "CUE")                                   # you on the brain's stock: one shared pair, the book stays
        assert log[-1] == ("nasdaq", "follow", "CUE", True) and ("nasdaq", "close", "CUE") not in log
        await lanes.put(YOU, "ANPA")
        assert log[-1] == ("nasdaq", "follow", "CUE", True)           # two stocks on the lanes: the third line is the book's
        log.clear()
        await lanes.put(CLAUDE, "MPU")                                # three stocks: Claude's line comes first
        assert log.index(("nasdaq", "close", "CUE")) < log.index(("level2", "ask", "MPU")), log
        assert log[-1] == ("nasdaq", "follow", "CUE", False) and not lanes.venue_room()
        await lanes.put(CLAUDE, None)
        assert log[-1] == ("nasdaq", "follow", "CUE", True)           # a line is free again
        log.clear()
        await lanes.put(BRAIN, "HIHO")                                # the brain moves: the old stock's book ends first
        assert log[0] == ("nasdaq", "close", "CUE") and log[-1] == ("nasdaq", "follow", "HIHO", True)
        await lanes.put(BRAIN, None)
        assert log[-1] == ("nasdaq", "follow", None, True)

    asyncio.run(run())


def test_the_brains_lane_says_its_nasdaq_book_on_the_wire(ib, monkeypatch):
    from capture import mode as capture_mode
    from line_lanes import view

    monkeypatch.setattr(capture_mode, "capture_symbols", lambda: [])
    asyncio.run(venue_book.follow("CUE"))
    got = view.view(now=5.0)["brain"]["nasdaq_book"]
    assert got["venue"] == "NASDAQ" and got["symbol"] == "CUE" and got["up"] is True and got["error"] is None
    assert "nasdaq_book" not in view.view(now=5.0)["you"]


def test_the_socket_joins_says_why_it_waits_and_never_opens_a_line(ib):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes import venue_book_ws
    from routes.trading import ws_router

    assert venue_book_ws.waiting_words("CUE") == "The brain's lane is not on CUE."
    _open(ib)
    assert venue_book_ws.waiting_words("CUE") is None
    app = FastAPI()
    app.include_router(ws_router)
    sent = len(ib.sent)
    with TestClient(app).websocket_connect("/ws/ibkr/venue-book/cue") as ws:
        assert ws.receive_json() == {"type": "subscribed", "symbol": "CUE", "venue": "NASDAQ"}
        frame = ws.receive_json()
        assert frame["type"] == "book" and frame["venue"] == "NASDAQ" and frame["seq"] == 1
        assert frame["data"]["bids"] == [{"price": 4.03, "size": 255.0, "side": "bid", "mm": "NSDQ"}]
    assert len(ib.sent) == sent and venue_book.is_up("CUE"), "a socket joining or leaving asks IBKR for nothing"
    assert json.loads(venue_book_ws.book_frame("CUE", BookVersion(2, 9.0, {"bids": [], "asks": []}), now=10.0))["sent"] == 10.0
