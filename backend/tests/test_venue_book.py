"""The brain's Nasdaq book (ADR 072 Amendment 5): a Level 2 request on the exchange itself, beside the all-exchange
line of the same stock, kept as its own book; it follows the brain's lane only while a Level 2 line is free."""
from __future__ import annotations

import asyncio
import json

import pytest

from constants_ibkr import IBKR_ERROR_DEPTH_MAX_LINES, IBKR_ERROR_DEPTH_RESET
from constants_venue_book import IBKR_VENUE_BOOK_ROWS
from ibkr import venue_book
from ibkr.venue_book import line
from line_lanes import lanes
from line_lanes.table import BRAIN, CLAUDE, YOU
from market_view.viewer_queues import BookVersion

CON_ID = 4242
INSERT, UPDATE, DELETE = 0, 1, 2
BID, ASK = 1, 0


@pytest.fixture
def ib(monkeypatch):
    """A real ib_async ``IB`` (its own subscription registry and wrapper), with the socket calls recorded."""
    from ib_async import IB

    from ibkr import client
    from sim import mode

    ib = IB()
    ib.sent = []
    ids = iter(range(900, 2000))
    monkeypatch.setattr(ib.client, "getReqId", lambda: next(ids))
    monkeypatch.setattr(ib.client, "reqMktDepth", lambda req, contract, rows, smart, opts=None: ib.sent.append(("ask", req, contract.exchange, rows, smart)))
    monkeypatch.setattr(ib.client, "cancelMktDepth", lambda req, smart: ib.sent.append(("cancel", req, smart)))

    async def qualify(contract):
        contract.conId = CON_ID
        return [contract]

    monkeypatch.setattr(ib, "qualifyContractsAsync", qualify)
    monkeypatch.setattr(client, "is_ready", lambda: True)
    monkeypatch.setattr(client, "get_ib", lambda: ib)
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


def _venue_req(ib) -> int:
    return next(s[1] for s in ib.sent if s[0] == "ask" and s[2] == "NASDAQ")


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


def test_rows_follow_ibkrs_insert_update_delete_and_stop_at_twenty(ib):
    asyncio.run(venue_book.follow("CUE"))
    req = _venue_req(ib)
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
    asyncio.run(venue_book.follow("CUE", now=1000.0))
    req = _venue_req(ib)
    with _Read(ib):
        _rows(ib, req, [(4.03, 255.0, "NSDQ")], BID)
    ib.errorEvent.emit(req + 50, IBKR_ERROR_DEPTH_MAX_LINES, "another request's refusal", None)
    ib.errorEvent.emit(req, 2152, "Exchanges - Depth: NASDAQ", None)                 # a notice, not a refusal
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
    assert not any(s[0] == "cancel" for s in ib.sent), "IBKR holds nothing for a refused request"
    asked = len(ib.sent)
    asyncio.run(venue_book.follow("CUE", now=__import__("time").time() + 1))        # not asked again at once
    assert len(ib.sent) == asked
    asyncio.run(venue_book.follow("CUE", now=__import__("time").time() + 60))
    assert len(ib.sent) == asked + 1 and venue_book.is_up("CUE")


def test_the_book_moves_with_the_brain_gives_its_line_back_and_outlives_no_session(ib, monkeypatch):
    asyncio.run(venue_book.follow("CUE"))
    first = _venue_req(ib)
    asyncio.run(venue_book.follow("MPU"))                                            # the brain's lane moved
    assert ib.sent[-2:] == [("cancel", first, False), ("ask", first + 1, "NASDAQ", IBKR_VENUE_BOOK_ROWS, False)]
    assert venue_book.is_up("MPU") and not venue_book.is_up("CUE")
    st = asyncio.run(venue_book.follow("MPU", room=False))                           # a lane needs the line
    assert st["up"] is False and "waits for one" in st["error"] and ib.sent[-1] == ("cancel", first + 1, False)
    asyncio.run(venue_book.follow("MPU"))
    assert venue_book.is_up("MPU")
    monkeypatch.setattr(line.line_session, "is_stale", lambda stamp: True)           # the IBKR session ended
    assert venue_book.symbol() is None and venue_book.current("MPU") is None
    sent = len(ib.sent)
    monkeypatch.setattr(line.line_session, "is_stale", lambda stamp: False)
    line._line.generation = -1
    monkeypatch.setattr(line.line_session, "is_stale", lambda stamp: stamp == -1)
    asyncio.run(venue_book.follow("MPU"))
    assert [s[0] for s in ib.sent[sent:]] == ["ask"], "a dead session's request is not cancelled; the book is asked for again"
    asyncio.run(venue_book.follow(None))
    assert venue_book.status() == {"venue": "NASDAQ", "symbol": None, "up": False, "rows": False, "seq": 0, "at": None, "error": None}


def test_no_book_on_a_replaying_desk_or_before_ibkr_is_ready(ib, monkeypatch):
    from ibkr import client
    from sim import mode

    monkeypatch.setattr(mode, "is_replay_desk", lambda: True)
    assert "replaying" in asyncio.run(venue_book.follow("CUE", now=1.0))["error"]
    monkeypatch.setattr(mode, "is_replay_desk", lambda: False)
    monkeypatch.setattr(client, "is_ready", lambda: False)
    assert asyncio.run(venue_book.follow("CUE", now=100.0))["error"] == "IBKR is not connected."
    assert ib.sent == []


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

    def close(reason="", **_kw):
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
    asyncio.run(venue_book.follow("CUE"))
    assert "Waiting for IBKR" not in (venue_book_ws.waiting_words("CUE") or "")
    with _Read(ib):
        _rows(ib, _venue_req(ib), [(4.03, 255.0, "NSDQ")], BID)
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
