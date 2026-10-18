"""Heavy reads share a fixed number of slots across processes (``research/market_reads/slots.py``, ADR 059)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import slots  # noqa: E402


@pytest.fixture
def one_slot(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_READ_SLOTS", "1")
    monkeypatch.setattr(slots, "_folder", lambda: tmp_path)


def test_a_second_heavy_read_waits_for_the_slot_then_gives_up(one_slot):
    with slots.heavy("first") as n:
        assert n == 0
        with pytest.raises(slots.Busy, match="second"):
            with slots.heavy("second", wait=0.3):
                pass


def test_a_released_slot_is_free_again(one_slot):
    with slots.heavy("first"):
        pass
    with slots.heavy("again", wait=0.3) as n:
        assert n == 0
