"""Shared L1 genericTickList must stay on IBKR's legal STK set (#178).

Tick TYPE 49 (Halted) maps to ``ticker.halted`` via ib_async tickGeneric.
IBKR docs list Generic tick required = "-" -- it is not requestable.
Putting "49" in genericTickList is Warning 321 and poisons the L1 upgrade.
"""
from __future__ import annotations

from constants import IBKR_HALT_TICK_TYPE, IBKR_L1_GENERIC_TICKS
from ibkr import ticks_generic as _generic


def test_l1_generic_ticks_never_request_halt_tick_type_49():
    requested = set(_generic.parse(IBKR_L1_GENERIC_TICKS))
    assert "49" not in requested
    assert str(IBKR_HALT_TICK_TYPE) == "49"
    assert "49" not in _generic.STK_GENERIC_TICKS_LEGAL
    assert requested <= _generic.STK_GENERIC_TICKS_LEGAL
    assert "233" in requested


def test_merge_drops_illegal_tick_49_even_if_a_caller_asks():
    assert _generic.merge("233", "49") == "233"
    assert _generic.merge("233,49", "236") == "233,236"
    assert _generic.merge("49", "49") == ""


def test_merge_keeps_legal_rtvolume_and_shortable():
    assert _generic.merge("233", "236") == "233,236"
    assert _generic.has_all("233,236", "233")
    assert _generic.has_all("233,236", "236")
    assert not _generic.has_all("233", "49")
