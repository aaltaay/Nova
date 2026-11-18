"""The prints the PC already holds for a Time & Sales socket that asks, and what each socket was sent.

Operator report 2026-11-17: the phone's tape "was not moving". GMM's line was up the whole time and IBKR delivered
every print to Nova; a fresh phone socket still opened on an empty tape, and one that dropped never got what it
had missed.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import ibkr.tape_stream as tape
from ibkr import tape_recording
from main import app
from routes import tape_recent, trading_tape_ws
from routes.ws_delivery import Delivery
from sensors import rings

OPENED = 1_794_944_031.0  # 14:33:51 ET, when the lane came to GMM


@pytest.fixture(autouse=True)
def _clean():
    rings.reset_for_tests()
    yield
    rings.reset_for_tests()
    tape_recording._since.pop("GMM", None)


def _live(receive_ts: float, **more) -> dict:
    return {"type": "print", "symbol": "GMM", "price": 1.3, "size": 100, "source": "ibkr",
            "receive_ts": receive_ts, **more}


def _line_open(monkeypatch, since: float | None = OPENED) -> None:
    if since is None:
        tape_recording._since.pop("GMM", None)
    else:
        tape_recording._since["GMM"] = since


def test_every_print_takes_a_rising_seq_before_the_ring_and_the_queues_see_it(monkeypatch):
    q: asyncio.Queue = asyncio.Queue()
    monkeypatch.setitem(tape._viewer_queues, "GMM", [q])
    tape._push_queue("GMM", _live(OPENED + 1))
    tape._push_queue("GMM", _live(OPENED + 2))
    tape._push_queue("GMM", {"type": "lane", "symbol": "GMM", "message": "moved", "lane": {}})
    first, second, lane = q.get_nowait(), q.get_nowait(), q.get_nowait()
    assert second["seq"] == first["seq"] + 1
    assert "seq" not in lane                                     # only a print has a place in the tape
    assert [p["seq"] for p in rings.recent_prints("GMM")] == [first["seq"], second["seq"]]
    # A later process starts above every print of this one: its count begins at its own start, in epoch ms.
    assert first["seq"] > 1_700_000_000_000


def test_a_socket_that_did_not_ask_is_sent_nothing_held(monkeypatch):
    _line_open(monkeypatch)
    tape._push_queue("GMM", _live(OPENED + 1))
    assert tape_recent.asked({}) == (0, None)
    assert tape_recent.asked({"recent": "x"}) == (0, None)
    assert tape_recent.held("GMM", 0, None) == []


def test_the_newest_n_prints_of_the_lines_own_stretch_oldest_first(monkeypatch):
    _line_open(monkeypatch)
    tape._push_queue("GMM", _live(OPENED - 3600))                # before the line reopened: a gap would not show
    for k in range(1, 6):
        tape._push_queue("GMM", _live(OPENED + k, price=1.0 + k / 100))
    held = tape_recent.held("GMM", 3, None)
    assert [p["price"] for p in held] == [1.03, 1.04, 1.05]
    assert len(tape_recent.held("GMM", 50, None)) == 5           # never the print from before the opening


def test_after_a_drop_it_is_every_print_above_the_last_one_the_socket_has(monkeypatch):
    _line_open(monkeypatch)
    for k in range(1, 6):
        tape._push_queue("GMM", _live(OPENED + k, price=1.0 + k / 100))
    seqs = [p["seq"] for p in rings.recent_prints("GMM")]
    n, after = tape_recent.asked({"recent": "40", "after": str(seqs[1])})
    assert (n, after) == (40, seqs[1])
    assert [p["seq"] for p in tape_recent.held("GMM", n, after)] == seqs[2:]
    assert tape_recent.held("GMM", n, seqs[-1]) == []            # it has them all
    # A seq from an earlier process is below every print of this one: nothing new is hidden.
    assert [p["seq"] for p in tape_recent.held("GMM", n, 5)] == seqs


def test_a_replays_print_or_an_unknown_opening_is_never_sent(monkeypatch):
    _line_open(monkeypatch)
    tape._push_queue("GMM", {"type": "print", "symbol": "GMM", "price": 9.0, "size": 1, "source": "sim",
                             "receive_ts": OPENED + 1})
    tape._push_queue("GMM", {"type": "print", "symbol": "GMM", "price": 9.0, "size": 1, "source": "ibkr"})
    assert tape_recent.held("GMM", 40, None) == []
    tape._push_queue("GMM", _live(OPENED + 2))
    _line_open(monkeypatch, None)                                # no line of this process: nothing is proven
    assert tape_recent.held("GMM", 40, None) == []


def test_asking_is_capped_at_the_panes_own_ring():
    assert tape_recent.asked({"recent": "100000"}) == (tape_recent.TAPE_RECENT_MAX, None)


def test_the_socket_sends_what_the_pc_holds_right_after_subscribed_and_logs_its_delivery(monkeypatch, caplog):
    from fastapi.testclient import TestClient

    from line_lanes import sockets as lane_sockets

    ws_mod = trading_tape_ws
    _line_open(monkeypatch)
    for k in range(1, 4):
        tape._push_queue("GMM", _live(OPENED + k, price=1.0 + k / 100))
    live = _live(OPENED + 9, price=1.5)

    monkeypatch.setattr(ws_mod, "desk_connected", lambda: True)
    monkeypatch.setattr(ws_mod, "is_replay_desk", lambda: False)
    monkeypatch.setattr(ws_mod, "_gate", lambda symbol: None)
    monkeypatch.setattr(ws_mod, "_silence", lambda symbol, halt_seen_at: None)
    monkeypatch.setattr(ws_mod._lanes, "refusal", lambda symbol: None)

    async def opening(symbol, front=False):
        return None

    monkeypatch.setattr(lane_sockets, "opening", opening)
    monkeypatch.setattr(lane_sockets, "opened", lambda symbol, **kw: 1)
    monkeypatch.setattr(lane_sockets, "closed", lambda symbol, token, kind=None: None)
    monkeypatch.setattr(lane_sockets, "line_down", lambda symbol, **kw: None)
    monkeypatch.setattr(tape, "is_subscribed", lambda symbol: True)
    monkeypatch.setattr(tape, "ws_viewer_opened", lambda symbol: None)
    monkeypatch.setattr(tape, "ws_viewer_closed", lambda symbol: False)
    monkeypatch.setattr(tape, "open_viewer_queue", lambda symbol: object())
    monkeypatch.setattr(tape, "close_viewer_queue", lambda symbol, queue: None)

    async def stream(_queue):
        yield [live]

    monkeypatch.setattr(tape, "stream_batches", stream)
    caplog.set_level("INFO", logger="routes.ws_delivery")
    with TestClient(app).websocket_connect("/ws/ibkr/tape/GMM?front=1&recent=2") as ws:
        assert ws.receive_json()["type"] == "subscribed"
        held = ws.receive_json()
        assert held["type"] == "prints" and held["recent"] is True
        assert [p["price"] for p in held["items"]] == [1.02, 1.03]       # the newest two, oldest first
        assert all(isinstance(p["seq"], int) for p in held["items"])
        assert ws.receive_json()["price"] == 1.5                          # then the live print
    said = [r.getMessage() for r in caplog.records if r.name == "routes.ws_delivery"]
    assert len(said) == 1
    assert "Time & Sales socket GMM" in said[0] and "3 prints sent" in said[0] and "front=1" in said[0]


def test_a_desk_pane_that_does_not_ask_gets_no_recent_frame(monkeypatch):
    held = tape_recent.held("GMM", *tape_recent.asked({"tab": "1", "front": "1"}))
    assert held == []


def test_delivery_words_say_who_how_long_and_how_much():
    d = Delivery("depth", "GMM", SimpleNamespace(client=SimpleNamespace(host="100.87.37.8")), front=False)
    d.opened = 1000.0
    assert d.words(now=1044.2) == ("Level 2 socket GMM from 100.87.37.8 closed after 44.2 s: "
                                   "0 books sent, last none, front=0")
    d.sent()
    assert "1 book sent" in d.words(now=1050.0)
    assert Delivery("tape", "GMM", object(), front=True).client == "unknown"
