"""The operator's lane (ADR 071 decisions 2, 3): no timer ends its lines; it moves only to another stock, at once."""
import asyncio

import pytest

from line_lanes import sockets as lane
from line_lanes import yours


class _Lines:
    """One kind of line: which stocks are up and how many viewers each has."""

    def __init__(self) -> None:
        self.up: set[str] = set()
        self.viewers: dict[str, int] = {}
        self.ended: list[str] = []

    def open(self, symbol: str) -> None:
        self.up.add(symbol)

    def ws_viewer_opened(self, symbol: str) -> None:
        self.viewers[symbol] = self.viewers.get(symbol, 0) + 1

    def ws_viewer_closed(self, symbol: str) -> bool:
        left = self.viewers.get(symbol, 0) - 1
        if left <= 0:
            self.viewers.pop(symbol, None)
            return True
        self.viewers[symbol] = left
        return False

    def viewer_count(self, symbol: str) -> int:
        return self.viewers.get(symbol, 0)

    def end(self, symbol: str) -> None:
        self.up.discard(symbol)
        self.ended.append(symbol)


@pytest.fixture
def desk(monkeypatch):
    from ibkr import depth, tape_line, tape_stream
    from l2 import continuous, recorder
    from sim import mode

    book, tape = _Lines(), _Lines()
    lingering: list[str] = []
    monkeypatch.setattr(mode, "is_replay_desk", lambda: False)
    for name in ("ws_viewer_opened", "ws_viewer_closed", "viewer_count"):
        monkeypatch.setattr(depth, name, getattr(book, name))
        monkeypatch.setattr(tape_stream, name, getattr(tape, name))
    monkeypatch.setattr(depth, "is_live", lambda s: s in book.up)
    monkeypatch.setattr(depth, "is_subscribed", lambda s: s in book.up)
    monkeypatch.setattr(depth, "unsubscribe", book.end)
    monkeypatch.setattr(tape_stream, "is_subscribed", lambda s: s in tape.up)
    monkeypatch.setattr(tape_stream, "unsubscribe", lingering.append)

    def release_now(symbol, why):
        if tape.viewer_count(symbol) > 0 or symbol not in tape.up:
            return False
        tape.end(symbol)
        return True

    async def stop(symbol):
        return None

    monkeypatch.setattr(tape_line, "release_now", release_now)
    monkeypatch.setattr(continuous, "stop", stop)
    monkeypatch.setattr(recorder, "is_recording", lambda s: False)
    return book, tape, lingering


def _socket_opens(book, tape, symbol, *, front=True):
    """A pane's two sockets open: each moves the lane, asks for its line, counts as a viewer, then the lane holds."""
    for lines, kind in ((book, lane.DEPTH), (tape, lane.TAPE)):
        asyncio.run(lane.opening(symbol, front=front))
        lines.open(symbol)
        lines.ws_viewer_opened(symbol)
        lane.opened(symbol, kind, front=front)


def _socket_closes(book, tape, symbol):
    """Both sockets close; True for a line whose last viewer that was (the line would then end on its timer)."""
    return book.ws_viewer_closed(symbol), tape.ws_viewer_closed(symbol)


def test_the_phone_leaving_ends_nothing_both_lines_stay_up(desk):
    book, tape, lingering = desk
    _socket_opens(book, tape, "XLAB")
    assert yours.stock() == "XLAB"

    assert _socket_closes(book, tape, "XLAB") == (False, False)   # the lane still watches both

    assert book.viewer_count("XLAB") == 1 and tape.viewer_count("XLAB") == 1
    assert book.ended == [] and tape.ended == [] and lingering == []


def test_coming_back_joins_the_lines_that_never_ended(desk):
    book, tape, _ = desk
    _socket_opens(book, tape, "XLAB")
    _socket_closes(book, tape, "XLAB")
    _socket_opens(book, tape, "XLAB")
    assert book.viewer_count("XLAB") == 2 and tape.viewer_count("XLAB") == 2   # the lane's and the pane's, once each
    assert tape.ended == []


def test_opening_another_stock_ends_the_old_lines_at_once(desk):
    book, tape, lingering = desk
    _socket_opens(book, tape, "XLAB")
    _socket_closes(book, tape, "XLAB")

    asyncio.run(lane.opening("TGHL", front=True))               # before TGHL's line is even asked for

    assert book.ended == ["XLAB"] and tape.ended == ["XLAB"]
    assert lingering == []                                       # cancelled now, not after a linger
    assert yours.stock() == "TGHL"


def test_a_stock_another_pane_still_watches_keeps_its_lines_when_the_lane_moves(desk):
    book, tape, _ = desk
    _socket_opens(book, tape, "SPY")                             # a Trader tab, left open
    _socket_opens(book, tape, "XLAB")                            # the phone
    assert book.ended == [] and tape.ended == []                 # SPY's own sockets still watch it
    assert book.viewer_count("SPY") == 1 and tape.viewer_count("SPY") == 1


def test_a_hidden_socket_never_moves_the_lane(desk):
    book, tape, _ = desk
    _socket_opens(book, tape, "XLAB")
    _socket_opens(book, tape, "SPY", front=False)
    assert yours.stock() == "XLAB"
    assert book.viewer_count("SPY") == 1                         # its own socket only: no lane reference


def test_a_line_that_is_not_up_is_not_held(desk):
    book, tape, _ = desk
    asyncio.run(lane.opening("XLAB", front=True))
    lane.opened("XLAB", lane.TAPE, front=True)                   # IBKR's 15 seconds: the tape was refused
    assert tape.viewer_count("XLAB") == 0
    assert not yours.holds("XLAB", lane.TAPE)
    tape.open("XLAB")
    lane.opened("XLAB", lane.TAPE, front=True)                   # the next try got it
    assert yours.holds("XLAB", lane.TAPE)


def test_a_replay_desk_has_no_lane(desk, monkeypatch):
    from sim import mode

    book, tape, _ = desk
    monkeypatch.setattr(mode, "is_replay_desk", lambda: True)
    _socket_opens(book, tape, "XLAB")
    assert yours.stock() is None
    assert book.viewer_count("XLAB") == 1


def test_a_lane_fault_never_costs_the_socket(desk, monkeypatch):
    async def boom(symbol):
        raise RuntimeError("lane table broke")

    monkeypatch.setattr(yours, "moving_to", boom)
    asyncio.run(lane.opening("XLAB", front=True))                # logged, not raised
