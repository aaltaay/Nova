"""Paper resting orders hold the symbol's tape line and its archive registration."""
from __future__ import annotations

import asyncio
import sys

import pytest

from l2 import tape as l2_tape
from practice import tape_hold


class FakeTape:
    def __init__(self, ok: bool = True) -> None:
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
        self.viewers[sym] = self.viewers.get(sym, 0) - 1
        return self.viewers[sym] <= 0

    def unsubscribe(self, sym):
        self.calls.append(("unsubscribe", sym))


@pytest.fixture
def line(monkeypatch):
    import ibkr

    tape = FakeTape()
    monkeypatch.setattr(ibkr, "tape_stream", tape, raising=False)
    monkeypatch.setitem(sys.modules, "ibkr.tape_stream", tape)
    l2_tape.clear_watched_for_tests()
    tape_hold.reset_for_tests()
    yield tape
    tape_hold.reset_for_tests()
    l2_tape.clear_watched_for_tests()


def test_hold_opens_the_line_counts_as_a_viewer_and_registers_the_archive(line) -> None:
    assert asyncio.run(tape_hold.acquire("imcc")) is None
    assert line.viewers["IMCC"] == 1 and ("subscribe", "IMCC") in line.calls
    assert l2_tape.is_watched("IMCC") and l2_tape.session_id("IMCC") is None
    assert tape_hold.held("IMCC") == {"tape": True, "watch": True}
    assert asyncio.run(tape_hold.acquire("IMCC")) is None  # idempotent
    assert line.viewers["IMCC"] == 1 and tape_hold.held_symbols() == ["IMCC"]


def test_release_closes_the_line_and_the_registration_it_owned(line) -> None:
    asyncio.run(tape_hold.acquire("IMCC"))
    tape_hold.release("IMCC")
    assert line.viewers["IMCC"] == 0 and ("unsubscribe", "IMCC") in line.calls
    assert not l2_tape.is_watched("IMCC") and tape_hold.held_symbols() == []
    tape_hold.release("IMCC")  # nothing held: a no-op


def test_release_leaves_a_panels_viewer_and_a_recorders_registration_alone(line) -> None:
    l2_tape.watch_symbol("IMCC", "rec-1")  # a recorder already persists this symbol
    line.ws_viewer_opened("IMCC")  # a Time & Sales panel is watching
    asyncio.run(tape_hold.acquire("IMCC"))
    assert tape_hold.held("IMCC") == {"tape": True, "watch": False}
    tape_hold.release("IMCC")
    assert line.viewers["IMCC"] == 1 and ("unsubscribe", "IMCC") not in line.calls
    assert l2_tape.session_id("IMCC") == "rec-1"


def test_a_recorder_taking_over_the_registration_keeps_it_after_release(line) -> None:
    asyncio.run(tape_hold.acquire("IMCC"))
    l2_tape.watch_symbol("IMCC", "rec-2")
    tape_hold.release("IMCC")
    assert l2_tape.is_watched("IMCC") and l2_tape.session_id("IMCC") == "rec-2"


def test_a_refused_line_holds_nothing_and_says_why(line) -> None:
    line.ok = False
    error = asyncio.run(tape_hold.acquire("IMCC"))
    assert error and "Gateway" in error
    assert tape_hold.held_symbols() == [] and not l2_tape.is_watched("IMCC")


def test_reconcile_holds_the_wanted_symbols_and_releases_the_rest(line) -> None:
    asyncio.run(tape_hold.acquire("AAA"))
    assert asyncio.run(tape_hold.reconcile(["bbb", "BBB", ""])) == {}
    assert tape_hold.held_symbols() == ["BBB"] and line.viewers["AAA"] == 0
    line.ok = False
    errors = asyncio.run(tape_hold.reconcile(["BBB", "CCC"]))
    assert list(errors) == ["CCC"] and tape_hold.held_symbols() == ["BBB"]


def test_reconcile_re_registers_a_symbol_a_recorder_stopped_watching(line) -> None:
    asyncio.run(tape_hold.acquire("IMCC"))
    l2_tape.unwatch_symbol("IMCC")  # a recorder stop pulled the registration
    asyncio.run(tape_hold.reconcile(["IMCC"]))
    assert l2_tape.is_watched("IMCC")
