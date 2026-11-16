"""The three lanes (ADR 071): only a lane opens a live line; your lane moves only to a stock you open in front, at
once, and no timer ends it; Claude's lane is the seat's; a stock two lanes are on is one pair of lines."""
from __future__ import annotations

import asyncio

import pytest

from line_lanes import lanes
from line_lanes import sockets as lane_sockets
from line_lanes.table import BOTS, CLAUDE, YOU


class _Lines:
    """One kind of IBKR line: which stocks are up, their viewers, what ended, and the frames pushed to viewers."""

    def __init__(self) -> None:
        self.up: set[str] = set()
        self.viewers: dict[str, int] = {}
        self.asked: list[str] = []
        self.ended: list[str] = []
        self.frames: list[tuple[str, str, dict]] = []

    async def subscribe_async(self, symbol: str, **_kw) -> dict:
        why = lanes.refusal(symbol)
        if why is not None:
            return {"ok": False, "error": why, "lane": True}
        self.asked.append(symbol)
        self.up.add(symbol)
        return {"ok": True, "error": None}

    def ws_viewer_opened(self, symbol: str) -> None:
        self.viewers[symbol] = self.viewers.get(symbol, 0) + 1

    def ws_viewer_closed(self, symbol: str) -> bool:
        left = self.viewers.get(symbol, 0) - 1
        if left <= 0:
            self.viewers.pop(symbol, None)
            return True
        self.viewers[symbol] = left
        return False

    def forget_viewers(self, symbol: str) -> None:
        self.viewers.pop(symbol, None)

    def push_lane(self, symbol: str, message: str, lane: dict) -> None:
        self.frames.append((symbol, message, dict(lane)))

    def end(self, symbol: str, *_args) -> bool:
        if symbol not in self.up:
            return False
        self.up.discard(symbol)
        self.ended.append(symbol)
        return True


@pytest.fixture
def desk(monkeypatch):
    from ibkr import depth, tape_line, tape_stream
    from l2 import continuous
    from sim import mode

    book, tape = _Lines(), _Lines()
    monkeypatch.setattr(mode, "is_replay_desk", lambda: False)
    for mod, lines in ((depth, book), (tape_stream, tape)):
        for name in ("subscribe_async", "ws_viewer_opened", "ws_viewer_closed", "forget_viewers", "push_lane"):
            monkeypatch.setattr(mod, name, getattr(lines, name))
    monkeypatch.setattr(depth, "is_live", lambda s: s in book.up)
    monkeypatch.setattr(depth, "is_subscribed", lambda s: s in book.up)
    monkeypatch.setattr(depth, "unsubscribe", book.end)
    monkeypatch.setattr(tape_stream, "is_subscribed", lambda s: s in tape.up)
    monkeypatch.setattr(tape_line, "drop_line", tape.end)
    monkeypatch.setattr(continuous, "start", lambda s: {"ok": True})

    async def stop(_symbol):
        return None

    monkeypatch.setattr(continuous, "stop", stop)
    lanes.enforce(True)
    return book, tape


def _open_pane(symbol: str, *, front: bool = True) -> None:
    """What a Trader tab's Level 2 socket does first: in front, it moves your lane."""
    asyncio.run(lane_sockets.opening(symbol, front=front))


def test_a_pane_in_front_puts_your_lane_and_both_lines_on_its_stock(desk):
    book, tape = desk
    _open_pane("XLAB")
    assert lanes.table().you == "XLAB"
    assert book.up == {"XLAB"} and tape.up == {"XLAB"}
    assert book.viewers == {"XLAB": 1} and tape.viewers == {"XLAB": 1}   # the lane's own reference on each line


def test_no_timer_ends_your_lane_closing_the_pane_leaves_both_lines_up(desk):
    book, tape = desk
    _open_pane("XLAB")
    book.ws_viewer_opened("XLAB")          # the socket counts as a viewer ...
    book.ws_viewer_closed("XLAB")          # ... and the phone's page goes to the background
    assert lane_sockets.ends_line("XLAB") is False                    # the route never ends a lane's line
    assert book.up == {"XLAB"} and tape.up == {"XLAB"} and not book.ended and not tape.ended


def test_opening_another_stock_moves_the_lane_at_once_and_tells_the_old_panes(desk):
    book, tape = desk
    _open_pane("XLAB")
    _open_pane("TGHL")
    assert lanes.table().you == "TGHL"
    assert book.ended == ["XLAB"] and tape.ended == ["XLAB"]       # cancelled at once, before TGHL's were asked
    assert book.asked == ["XLAB", "TGHL"] and book.up == {"TGHL"} and tape.up == {"TGHL"}
    symbol, message, on = book.frames[-1]
    assert symbol == "XLAB" and "Your Level 2 moved to TGHL" in message and on["you"] == "TGHL"
    assert tape.frames[-1][0] == "XLAB"


def test_a_pane_not_in_front_never_moves_the_lane_and_opens_no_line(desk):
    book, tape = desk
    _open_pane("XLAB")
    _open_pane("TGHL", front=False)
    assert lanes.table().you == "XLAB"
    result = asyncio.run(book.subscribe_async("TGHL"))
    assert result["ok"] is False and result["lane"] is True
    assert result["error"] == "Your Level 2 is on XLAB -- open TGHL in front to bring it here."
    assert "TGHL" not in book.up and "TGHL" not in tape.up


def test_the_gate_names_no_lane_before_you_opened_a_stock():
    lanes.enforce(True)
    assert lanes.refusal("AMOD") == "No lane is on AMOD: open it in front to bring your Level 2 here."
    lanes.enforce(False)
    assert lanes.refusal("AMOD") is None


def test_claudes_lane_is_the_seats_and_never_yours(desk):
    from agent_trader import lines as claude

    book, tape = desk
    _open_pane("XLAB")
    assert asyncio.run(claude.acquire("RUNR")) is None
    assert lanes.table().claude == "RUNR" and claude.holds_depth("RUNR") and claude.holds_tape("RUNR")
    assert book.up == {"XLAB", "RUNR"}
    _open_pane("TGHL")                                              # your lane moves; Claude's stays
    assert lanes.table().claude == "RUNR" and "RUNR" in book.up and book.ended == ["XLAB"]
    asyncio.run(claude.release())
    assert lanes.table().claude is None and book.ended == ["XLAB", "RUNR"]


def test_a_stock_two_lanes_are_on_is_one_pair_of_lines_and_ends_with_the_last(desk):
    book, tape = desk
    _open_pane("XLAB")
    asyncio.run(lanes.put(BOTS, "XLAB"))
    assert book.asked == ["XLAB"] and lanes.table().owners_of("XLAB") == (YOU, BOTS)
    _open_pane("TGHL")                                              # you leave: the bots still watch XLAB
    assert "XLAB" in book.up and book.ended == []
    asyncio.run(lanes.put(BOTS, None))
    assert book.ended == ["XLAB"] and tape.ended == ["XLAB"]


def test_a_recording_ends_before_its_stocks_lines_do(desk):
    book, _tape = desk
    order: list[str] = []

    async def before(symbol: str) -> None:
        order.append(f"record off {symbol} (line up: {symbol in book.up})")

    lanes.on_before_close(before)
    try:
        asyncio.run(lanes.put(CLAUDE, "RUNR"))
        asyncio.run(lanes.put(CLAUDE, None))
    finally:
        lanes._before_close.remove(before)
    assert order == ["record off RUNR (line up: True)"] and book.ended == ["RUNR"]


def test_ensure_asks_again_for_a_lane_line_ibkr_ended(desk):
    book, tape = desk
    asyncio.run(lanes.put(BOTS, "AISP"))
    tape.up.discard("AISP")                                         # IBKR ended the AllLast line
    asyncio.run(lanes.ensure())
    assert "AISP" in tape.up and tape.asked == ["AISP", "AISP"]
    assert tape.viewers == {"AISP": 1}                              # the lane's reference is never doubled
