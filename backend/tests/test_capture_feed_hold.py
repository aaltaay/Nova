"""Session Record owns its IBKR lines and records whatever the desk is doing (#315).

The operator's rule: Record works whenever they choose -- on Paper, Live or a Sim
desk, with or without a Time & Sales or Level 2 panel open. That needs Record to
hold its own tape + depth lines, a Sim desk to keep live ticks out of its practice
panels while still recording them, and a switch to Sim to leave a recording alone.
"""
import asyncio
from types import SimpleNamespace

import pytest

from capture import feed_hold


class FakeTape:
    def __init__(self, ok=True):
        self.ok, self.subscribed, self.viewers, self.calls = ok, set(), {}, []

    def is_subscribed(self, sym):
        return sym in self.subscribed

    async def subscribe_async(self, sym):
        self.calls.append(("subscribe", sym))
        if not self.ok:
            return {"ok": False, "error": "IBKR tape transport down -- Gateway not connected"}
        self.subscribed.add(sym)
        return {"ok": True, "error": None}

    def ws_viewer_opened(self, sym):
        self.viewers[sym] = self.viewers.get(sym, 0) + 1

    def ws_viewer_closed(self, sym):
        self.viewers[sym] -= 1
        return self.viewers[sym] <= 0

    def unsubscribe(self, sym):
        self.calls.append(("unsubscribe", sym))


class FakeDepth(FakeTape):
    def __init__(self, ok=True):
        super().__init__(ok)
        self.live = set()

    def is_live(self, sym):
        return sym in self.live

    async def subscribe_async(self, sym, *, live=False):
        self.calls.append(("subscribe", sym, live))
        if self.ok and live:
            self.live.add(sym)
            self.subscribed.add(sym)
        return {"ok": self.ok, "error": None if self.ok else "depth refused"}

    async def release_when_idle(self, sym):
        return True


@pytest.fixture
def lines(monkeypatch):
    import ibkr
    import l2.recorder as l2_recorder
    tape, depth = FakeTape(), FakeDepth()
    monkeypatch.setattr(ibkr, "tape_stream", tape, raising=False)
    monkeypatch.setattr(ibkr, "depth", depth, raising=False)
    monkeypatch.setitem(__import__("sys").modules, "ibkr.tape_stream", tape)
    monkeypatch.setitem(__import__("sys").modules, "ibkr.depth", depth)
    monkeypatch.setattr(l2_recorder, "is_recording", lambda sym: False)
    feed_hold.reset_for_tests()
    yield SimpleNamespace(tape=tape, depth=depth)
    feed_hold.reset_for_tests()


def test_record_opens_and_holds_both_lines_like_a_viewer(lines):
    assert asyncio.run(feed_hold.acquire("imcc")) is None
    assert lines.tape.viewers["IMCC"] == 1 and lines.depth.viewers["IMCC"] == 1
    # Depth is asked for LIVE: on a Sim desk a plain subscribe is a replay slot.
    assert ("subscribe", "IMCC", True) in lines.depth.calls
    assert feed_hold.held("IMCC") == {"tape": True, "depth": True}


def test_a_panel_closing_cannot_pull_the_recording_feed(lines):
    asyncio.run(feed_hold.acquire("IMCC"))
    lines.tape.ws_viewer_opened("IMCC")                  # a Time & Sales panel opens...
    assert lines.tape.ws_viewer_closed("IMCC") is False  # ...and closes: Record still holds
    asyncio.run(feed_hold.release("IMCC"))
    assert ("unsubscribe", "IMCC") in lines.tape.calls   # released only when Record lets go


def test_release_leaves_a_line_a_panel_is_still_watching(lines):
    asyncio.run(feed_hold.acquire("IMCC"))
    lines.tape.ws_viewer_opened("IMCC")                  # a panel is open on the symbol
    asyncio.run(feed_hold.release("IMCC"))
    assert ("unsubscribe", "IMCC") not in lines.tape.calls


def test_no_tape_means_no_recording_and_nothing_held(lines):
    lines.tape.ok = False
    error = asyncio.run(feed_hold.acquire("IMCC"))
    assert error == "IBKR tape transport down -- Gateway not connected"
    assert feed_hold.held("IMCC") is None and not lines.tape.viewers


def test_depth_refused_still_records_prints(lines):
    lines.depth.ok = False
    assert asyncio.run(feed_hold.acquire("IMCC")) is None
    assert feed_hold.held("IMCC") == {"tape": True, "depth": False}


# ---------------------------------------------------------------------------
# A Sim desk records live ticks but never shows them


def test_a_live_print_on_a_sim_desk_is_recorded_but_not_shown(monkeypatch):
    from datetime import datetime, timezone
    import ibkr.tape_recording as fanout
    from ibkr import tape_events
    import sim.mode as sim_mode
    from archive import bar_builder, write_queue
    from ibkr import tape_10sec
    monkeypatch.setattr(write_queue, "enqueue_tape_print", lambda **kw: None)
    monkeypatch.setattr(bar_builder, "on_tape_print", lambda **kw: None)
    monkeypatch.setattr(tape_10sec, "on_print", lambda *a: None)
    dispatched, shown = [], []
    monkeypatch.setattr(fanout, "dispatch", lambda payload: dispatched.append(payload))

    def ticker():  # the handler consumes (clears) the tick list, so one per call
        return SimpleNamespace(tickByTicks=[SimpleNamespace(
            time=datetime.now(timezone.utc), price=6.2, size=100, exchange="NSDQ", specialConditions="")])

    depth = SimpleNamespace(current_book=lambda sym: None)
    monkeypatch.setattr(sim_mode, "is_sim_mode", lambda: True)
    tape_events.on_tape_update(ticker(), "IMCC", lambda sym, payload: shown.append(payload), depth)
    assert len(dispatched) == 1 and shown == []
    monkeypatch.setattr(sim_mode, "is_sim_mode", lambda: False)
    tape_events.on_tape_update(ticker(), "IMCC", lambda sym, payload: shown.append(payload), depth)
    assert len(dispatched) == 2 and len(shown) == 1


def test_a_live_book_on_a_sim_desk_is_recorded_and_kept_for_sides_but_not_shown(monkeypatch):
    from ibkr.depth import handlers, state
    import sim.mode as sim_mode
    recorded, shown = [], []
    monkeypatch.setattr(sim_mode, "is_sim_mode", lambda: True)
    monkeypatch.setattr(handlers, "_record_book", lambda sym, book: recorded.append(book))
    monkeypatch.setattr(state, "push_book", lambda sym, book: shown.append(book))
    ticker = SimpleNamespace(domBids=[SimpleNamespace(price=6.2, size=200, marketMaker="NSDQ")],
                             domAsks=[SimpleNamespace(price=6.29, size=117, marketMaker="NSDQ")])
    handlers.on_update_book(ticker, "IMCC")
    assert len(recorded) == 1 and shown == []
    # The stored book still updates: the live print side is classified against it.
    assert state.current_book("IMCC")["bids"][0]["price"] == 6.2
    state.clear_symbol("IMCC")


def test_live_depth_on_a_sim_desk_skips_the_replay_slot(monkeypatch):
    import importlib
    from ibkr.depth import state
    subscribe = importlib.import_module("ibkr.depth.subscribe")  # the module, not the facade's function
    import ibkr.client as client
    import sim.mode as sim_mode
    monkeypatch.setattr(sim_mode, "is_sim_mode", lambda: True)
    monkeypatch.setattr(client, "is_ready", lambda: False)
    monkeypatch.setattr(client, "unavailable_detail", lambda what: f"{what} unavailable")
    # A panel's plain subscribe on Sim gets the replay slot...
    assert asyncio.run(subscribe.subscribe_async("IMCC"))["ok"] is True
    assert state.is_subscribed("IMCC") and not state.is_live("IMCC")
    # ...Record's live subscribe goes for the real line instead (here: Gateway down).
    result = asyncio.run(subscribe.subscribe_async("IMCC", live=True))
    assert result["ok"] is False and "unavailable" in result["error"]
    state.clear_symbol("IMCC")


# ---------------------------------------------------------------------------
# Switching to Sim leaves a recording running


def test_switching_the_desk_to_sim_does_not_stop_a_recording(monkeypatch):
    import capture.mode as capture_mode
    import sim.mode as sim_mode
    import sim.feed as sim_feed
    stops = []
    monkeypatch.setattr(capture_mode, "is_capture_mode", lambda: True)
    monkeypatch.setattr(capture_mode, "set_capture_mode", lambda *a, **k: stops.append((a, k)))
    monkeypatch.setattr(sim_feed, "start_sim_feed_threadsafe", lambda: None)
    try:
        sim_mode.set_sim_mode(True)
        assert stops == []
    finally:
        monkeypatch.setattr(sim_feed, "stop_sim_feed_threadsafe", lambda: None)
        sim_mode.set_sim_mode(False)
        sim_mode.reset_for_tests()
