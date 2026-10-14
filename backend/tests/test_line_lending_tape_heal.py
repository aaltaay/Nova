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


@pytest.fixture
def silent_line(desk, monkeypatch):
    """Missing-trades model; fake sends do not establish IBKR capacity."""
    from capture import feed_hold
    from ibkr import tape_recording, tape_silence

    facts = {"peers": ["PEER"], "recording": False, "missed": True}
    monkeypatch.setattr(tape_recording, "_last", {})
    monkeypatch.setattr(tape_recording, "_last_exchange", {})
    monkeypatch.setattr(tape_recording, "_since", {})
    monkeypatch.setattr(tape_silence, "pipeline_peers", lambda sym, now=None: list(facts["peers"]))
    monkeypatch.setattr(tape_silence, "missed_trades", lambda sym, now=None:
                        {"since": time.time() - 200} if facts["missed"] else None)
    monkeypatch.setattr(feed_hold, "held", lambda sym: {"tape": True} if facts["recording"] else None)
    monkeypatch.setattr(tape_heal, "TAPE_RECOVERY_HOLD_SEC", 0.15)
    monkeypatch.setattr(tape_heal, "TAPE_RECOVERY_VERIFY_SEC", 0.05)
    return facts, tape_recording


def _dead(*, never_printed=False, peers=("PEER",)):
    return {"state": "dead", "since": time.time() - 200, "pipeline": list(peers),
            "last_print_ts": None if never_printed else time.time() - 200,
            "text": "Level 1 reports trades this registered line missed"}


@pytest.mark.parametrize("never_printed", [False, True])
def test_registered_dead_line_holds_then_reasks_once_after_a_sibling_returns(desk, silent_line, never_printed):
    facts, producer = silent_line

    async def scenario():
        await _open_socket("AMOD")
        queue2 = tape.open_viewer_queue("AMOD")
        tape.ws_viewer_opened("AMOD")
        before = desk.next_req
        tape_heal.line_down("AMOD", silence=_dead(never_printed=never_printed))
        assert await _until(lambda: (tape_heal.silent_status("AMOD") or {}).get("state") == "holding")
        assert tape.is_subscribed("AMOD") and desk.next_req == before
        facts["peers"] = []
        assert await _until(lambda: desk.next_req > before)
        assert desk.next_req == before + 1 and tape.viewer_count("AMOD") == 2
        assert queue2 in tape._viewer_queues["AMOD"]
        producer._last["AMOD"] = time.time()
        assert await _until(lambda: tape_heal.silent_status("AMOD")["state"] == "resumed")

    asyncio.run(scenario())


def test_a_shared_line_returning_without_a_reask_is_kept(desk, silent_line):
    _facts, producer = silent_line

    async def scenario():
        await _open_socket("AMOD")
        before = desk.next_req
        tape_heal.line_down("AMOD", silence=_dead())
        await asyncio.sleep(0.01)
        producer._last["AMOD"] = time.time()
        assert await _until(lambda: not tape_heal.healing("AMOD"))
        assert desk.next_req == before and tape.is_subscribed("AMOD")

    asyncio.run(scenario())


def test_subscribe_without_prints_is_failed_and_never_churned(desk, silent_line):
    facts, _producer = silent_line
    facts["peers"] = []

    async def scenario():
        await _open_socket("AMOD")
        before = desk.next_req
        tape_heal.line_down("AMOD", silence=_dead(peers=()))
        assert await _until(lambda: (tape_heal.silent_status("AMOD") or {}).get("state") == "failed")
        assert desk.next_req == before + 1
        frames = _drain(tape._viewer_queues["AMOD"][0])
        assert frames[-1]["retry_at"] is None     # the desk must not say RETRYING after the bounded attempt
        for _ in range(10):
            tape_heal.line_down("AMOD", silence=_dead(peers=()))
            await asyncio.sleep(0.01)
        assert desk.next_req == before + 1 and tape.is_subscribed("AMOD")

    asyncio.run(scenario())


def test_persistent_pipeline_stops_watching_and_states_the_hold(desk, silent_line):
    async def scenario():
        await _open_socket("AMOD")
        before = desk.next_req
        tape_heal.line_down("AMOD", silence=_dead())
        assert await _until(lambda: not tape_heal.healing("AMOD"))
        assert tape_heal.silent_status("AMOD")["state"] == "holding"
        tape_heal.line_down("AMOD", silence=_dead())
        await asyncio.sleep(0.02)
        assert not tape_heal.healing("AMOD") and desk.next_req == before

    asyncio.run(scenario())


def test_recording_owns_shared_silence_recovery(desk, silent_line):
    facts, _producer = silent_line
    facts["recording"] = True

    async def scenario():
        await _open_socket("AMOD")
        before = desk.next_req
        tape_heal.line_down("AMOD", silence=_dead())
        assert not tape_heal.healing("AMOD")
        assert tape_heal.silent_status("AMOD")["state"] == "delegated"
        assert tape.is_subscribed("AMOD") and desk.next_req == before

    asyncio.run(scenario())


@pytest.mark.parametrize("state", ["halted", "quiet", "silent"])
def test_halt_quiet_or_uncertain_line_never_reasks(desk, silent_line, state):
    async def scenario():
        await _open_socket("AMOD")
        before = desk.next_req
        tape_heal.line_down("AMOD", silence={**_dead(), "state": state})
        await asyncio.sleep(0.02)
        assert not tape_heal.healing("AMOD") and desk.next_req == before

    asyncio.run(scenario())


def test_a_recording_starting_during_the_hold_takes_over_without_a_reask(desk, silent_line):
    facts, _producer = silent_line

    async def scenario():
        await _open_socket("AMOD")
        before = desk.next_req
        tape_heal.line_down("AMOD", silence=_dead())
        await asyncio.sleep(0.01)
        facts["recording"] = True
        assert await _until(lambda: not tape_heal.healing("AMOD"))
        assert tape_heal.silent_status("AMOD")["state"] == "delegated"
        assert desk.next_req == before and tape.is_subscribed("AMOD")

    asyncio.run(scenario())


def test_shared_stall_turning_quiet_or_halted_is_not_cancelled(desk, silent_line):
    facts, _producer = silent_line

    async def scenario():
        await _open_socket("AMOD")
        before = desk.next_req
        tape_heal.line_down("AMOD", silence=_dead())
        await asyncio.sleep(0.01)
        facts["missed"] = False
        facts["peers"] = []
        assert await _until(lambda: not tape_heal.healing("AMOD"))
        assert desk.next_req == before and tape.is_subscribed("AMOD")

    asyncio.run(scenario())


def test_last_socket_close_stops_silent_recovery_without_releasing_a_record_hold(desk, silent_line):
    async def scenario():
        token, _queue = await _open_socket("AMOD")
        tape.ws_viewer_opened("AMOD")             # another reference, such as a recording
        before = desk.next_req
        tape_heal.line_down("AMOD", silence=_dead())
        sockets.closed("AMOD", token, sockets.TAPE)
        tape.ws_viewer_closed("AMOD")
        assert await _until(lambda: not tape_heal.healing("AMOD"))
        assert tape.viewer_count("AMOD") == 1 and tape.is_subscribed("AMOD")
        assert desk.next_req == before

    asyncio.run(scenario())


def test_replay_and_session_changes_do_not_cancel_a_registered_line(desk, silent_line, monkeypatch):
    from ibkr import client
    from sim import mode

    generation = {"value": 1}
    monkeypatch.setattr(client, "current_generation", lambda: generation["value"])

    async def scenario():
        await _open_socket("AMOD")
        before = desk.next_req
        monkeypatch.setattr(mode, "is_replay_desk", lambda: True)
        tape_heal.line_down("AMOD", silence=_dead())
        assert not tape_heal.healing("AMOD")
        monkeypatch.setattr(mode, "is_replay_desk", lambda: False)
        tape_heal.line_down("AMOD", silence=_dead())
        await asyncio.sleep(0.01)
        generation["value"] = 2
        assert await _until(lambda: not tape_heal.healing("AMOD"))
        assert desk.next_req == before
        assert tape_heal.silent_status("AMOD") is None

    asyncio.run(scenario())


def test_refusal_after_silent_reask_is_failed_until_existing_healer_reopens(desk, silent_line):
    facts, _producer = silent_line
    facts["peers"] = []
    original = desk.reqTickByTickData

    def refuse_next(contract, kind, **kwargs):
        ticker = original(contract, kind, **kwargs)
        req = desk.find(contract.conId, kind).reqId
        asyncio.get_running_loop().call_soon(
            lambda: [h(req, 10190, "tick-by-tick cap", contract) for h in list(desk.errorEvent.handlers)])
        return ticker

    async def scenario():
        await _open_socket("AMOD")
        desk.reqTickByTickData = refuse_next
        tape_heal.line_down("AMOD", silence=_dead(peers=()))
        assert await _until(lambda: (tape_heal.silent_status("AMOD") or {}).get("state") == "failed")
        assert not tape.is_subscribed("AMOD")
        desk.reqTickByTickData = original
        tape_heal.line_down("AMOD")
        assert await _until(lambda: tape.is_subscribed("AMOD"))

    asyncio.run(scenario())
