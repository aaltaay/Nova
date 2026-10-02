"""A Time & Sales socket never sits on a dead line (#698).

2026-10-02 07:54 ET: three recordings held IBKR's tick-by-tick lines, IBKR refused AMOD's with
10190 after the request, and the tab's Time & Sales read ERROR until the operator switched tabs.
Here the same cap, refused the same way: the line comes back by itself -- idle lines cancelled,
auto-record's lowest line given back for the tab in front, asked again after IBKR's 15 s rule --
and the socket is told what is happening and when the line is back.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

import ibkr.tape_stream as tape
from ibkr import tape_line
from line_lending import focus, socket_gate, sockets, tape_heal

CAP = 3  # this fake IBKR's tick-by-tick cap


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self


class _IB:
    """Holds at most ``CAP`` AllLast lines; a request past it is answered 10190 after it is made."""

    def __init__(self):
        self.errorEvent = _Event()
        self.wrapper = SimpleNamespace(subscriptions=SimpleNamespace(find_market_data=self.find))
        self.subs: dict[int, SimpleNamespace] = {}
        self.next_req = 100
        self.refused: list[str] = []

    def find(self, con_id, _kind):
        return self.subs.get(con_id)

    async def qualifyContractsAsync(self, contract):
        contract.conId = sum(ord(c) for c in contract.symbol) * 7
        return [contract]

    def reqTickByTickData(self, contract, _tick_type, **_kwargs):
        if contract.conId not in self.subs:
            full = len(self.subs) >= CAP
            req = self.next_req
            self.next_req += 1
            self.subs[contract.conId] = SimpleNamespace(reqId=req)
            if full:
                self.refused.append(contract.symbol)
                msg = "Max number of tick-by-tick requests has been reached."
                asyncio.get_running_loop().call_soon(
                    lambda: [h(req, 10190, msg, contract) for h in list(self.errorEvent.handlers)])
        return SimpleNamespace(tickByTicks=[], updateEvent=_Event())

    def cancelTickByTickData(self, contract, _tick_type):
        self.subs.pop(contract.conId, None)


class _Stock:
    def __init__(self, symbol, *_args):
        self.symbol = symbol
        self.conId = 0


@pytest.fixture
def desk(monkeypatch):
    fake = _IB()
    tape.reset_for_tests()
    tape_heal.reset_for_tests()
    sockets.reset_for_tests()
    from ibkr import client
    from leaderboard import auto_record
    from sim import mode

    monkeypatch.setattr(tape._client, "get_ib", lambda: fake)
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", _Stock)
    monkeypatch.setattr(tape, "_warm_10sec_fill", lambda _sym: None)
    monkeypatch.setattr(tape, "IBKR_TAPE_RESUBSCRIBE_GUARD_SEC", 0.05)
    monkeypatch.setattr(client, "is_ready", lambda: True)
    monkeypatch.setattr(mode, "is_replay_desk", lambda: False)
    monkeypatch.setattr(tape_heal, "LINE_LENDING_TAPE_HEAL_BACKOFF_SEC", (0.0, 0.05))
    monkeypatch.setattr(tape_heal, "LINE_LENDING_TAPE_HEAL_CONFIRM_SEC", 0.05)
    monkeypatch.setattr(tape_heal, "LINE_LENDING_TAPE_HEAL_POLL_SEC", 0.01)
    fake.front = {"AMOD"}
    monkeypatch.setattr(focus, "read", lambda now=None: focus.FocusRead(
        known=True, front=frozenset(fake.front), tabs=frozenset({"AMOD"})))
    fake.gave_back: list[str] = []

    async def make_room_for(symbol, *, tape_refused=False, for_record=False):
        assert tape_refused
        victim = "SSM"                                  # auto-record's lowest-ranked recording
        fake.gave_back.append(victim)
        tape.ws_viewer_closed(victim)                   # the recording lets go of its line...
        tape_line.release_now(victim, "Record gave its line to another symbol")  # ...at once
        return victim

    monkeypatch.setattr(auto_record, "make_room_for", make_room_for)
    monkeypatch.setattr(auto_record, "held_symbols", lambda: ["SSM"])
    yield fake
    tape_heal.reset_for_tests()
    tape.reset_for_tests()
    sockets.reset_for_tests()


async def _recordings(*symbols):
    for sym in symbols:
        assert (await tape.subscribe_async(sym))["ok"]
        tape.ws_viewer_opened(sym)                      # a Record hold counts as a viewer


async def _open_socket(sym):
    """What /ws/ibkr/tape does: a viewer, a registered socket, a queue, a subscribe."""
    tape.ws_viewer_opened(sym)
    token = sockets.opened(sym, tab=True, front=True, now=time.time(), kind=sockets.TAPE)
    queue = tape.open_viewer_queue(sym)
    assert (await tape.subscribe_async(sym))["ok"]      # IBKR says no only after the request
    await asyncio.sleep(0.01)
    return token, queue


def _drain(queue):
    out = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


async def _until(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        await asyncio.sleep(0.01)
    return False


def test_the_tab_in_front_gets_its_time_and_sales_back_by_itself(desk):
    async def scenario():
        await _recordings("SDEV", "TNMG", "SSM")
        _token, queue = await _open_socket("AMOD")
        assert desk.refused == ["AMOD"] and not tape.is_subscribed("AMOD")
        first = _drain(queue)
        assert first[-1]["type"] == "error" and "10190" in first[-1]["message"]
        socket_gate.line_down("AMOD")                   # the socket read IBKR's error
        seen: list[dict] = []
        healed = await _until(lambda: seen.extend(_drain(queue)) or any(f["type"] == "subscribed" for f in seen))
        return healed, seen

    healed, seen = asyncio.run(scenario())
    assert healed
    assert desk.gave_back == ["SSM"]                    # auto-record's line, once, for the tab in front
    assert "SSM" not in tape._tickers                   # cancelled at once, not after the linger
    status = next(f for f in seen if f.get("healing"))
    assert "every tick-by-tick line is in use" in status["message"]
    assert "auto-record gave back SSM's recording line" in status["message"]
    assert isinstance(status["retry_at"], float)
    assert tape.is_subscribed("AMOD") and desk.refused == ["AMOD"]


def test_idle_lines_are_cancelled_before_any_recording_is_touched(desk):
    async def scenario():
        await _recordings("SDEV", "TNMG")
        assert (await tape.subscribe_async("AIXI"))["ok"]   # a tab closed: its line lingers
        _token, queue = await _open_socket("AMOD")
        assert desk.refused == ["AMOD"]
        socket_gate.line_down("AMOD")
        return await _until(lambda: tape.is_subscribed("AMOD"))

    assert asyncio.run(scenario())
    assert desk.gave_back == []                         # the idle AIXI line made the room
    assert "AIXI" not in tape._tickers


def test_a_hidden_tab_never_takes_a_recording_and_waits_for_a_line(desk):
    desk.front = set()                                  # the operator looks at another tab

    async def scenario():
        await _recordings("SDEV", "TNMG", "SSM")
        _token, queue = await _open_socket("AMOD")
        socket_gate.line_down("AMOD")
        await asyncio.sleep(0.3)
        held = _drain(queue)
        assert desk.gave_back == [] and len(desk.refused) >= 2      # it kept asking; it took nothing
        assert not any(f["type"] == "subscribed" for f in held)
        assert any("held by" in f.get("message", "") and "SSM (auto-record)" in f["message"] for f in held)
        tape.ws_viewer_closed("SDEV")                   # a recording stops: a line frees
        tape_line.release_now("SDEV", "stopped")
        seen: list[dict] = []
        return await _until(lambda: seen.extend(_drain(queue)) or any(f["type"] == "subscribed" for f in seen))

    assert asyncio.run(scenario())
    assert tape.is_subscribed("AMOD")


def test_it_stops_asking_once_no_socket_watches(desk):
    desk.front = set()

    async def scenario():
        await _recordings("SDEV", "TNMG", "SSM")
        token, _queue = await _open_socket("AMOD")
        socket_gate.line_down("AMOD")
        assert tape_heal.healing("AMOD")
        sockets.closed("AMOD", token, sockets.TAPE)     # the tab closed
        return await _until(lambda: not tape_heal.healing("AMOD"))

    assert asyncio.run(scenario())
    assert desk.refused == ["AMOD"]                     # never asked IBKR again for nobody
