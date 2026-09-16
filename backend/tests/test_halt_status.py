"""Tick-49 observe: first start sticks, clear on resume, tape quiet ignored."""
from __future__ import annotations

from ibkr import halt_status
from ibkr.halt_eta import KIND_LULD, KIND_REGULATORY, KIND_UNKNOWN


class _Ticker:
    def __init__(self, halted=None):
        self.halted = halted


def setup_function(_fn):
    halt_status.reset()


def test_first_luld_tick_records_observed_start():
    snap, changed = halt_status.observe_code("reto", 2, now=1_000.0)
    assert changed is True
    assert snap is not None
    assert snap["halted"] is True
    assert snap["kind"] == KIND_LULD
    assert snap["halt_start"] == 1_000.0
    assert snap["halt_start_source"] == "observed_tick_49"
    assert snap["source"] == "ibkr_tick_49"


def test_same_halt_keeps_original_start():
    halt_status.observe_code("RETO", 2.0, now=1_000.0)
    snap, changed = halt_status.observe_code("reto", 2, now=1_200.0)
    assert changed is False
    assert snap is not None
    assert snap["halt_start"] == 1_000.0


def test_code_zero_clears_immediately():
    halt_status.observe_code("RETO", 2, now=1_000.0)
    snap, changed = halt_status.observe_code("RETO", 0, now=1_010.0)
    assert changed is True
    assert snap is None
    assert halt_status.snapshot("RETO") is None


def test_nan_and_unavailable_are_not_halts():
    snap, changed = halt_status.observe_from_ticker("RETO", _Ticker(float("nan")))
    assert snap is None and changed is False
    snap, changed = halt_status.observe_code("RETO", -1)
    assert snap is None and changed is False
    # Quiet tape (no ticker.halted) must not invent a chip.
    snap, changed = halt_status.observe_from_ticker("RETO", _Ticker())
    assert snap is None and changed is False


def test_regulatory_and_unknown_codes():
    snap, _ = halt_status.observe_code("NEWS", 1, now=50.0)
    assert snap is not None
    assert snap["kind"] == KIND_REGULATORY
    halt_status.reset()
    snap, _ = halt_status.observe_code("ODD", 7, now=50.0)
    assert snap is not None
    assert snap["kind"] == KIND_UNKNOWN
