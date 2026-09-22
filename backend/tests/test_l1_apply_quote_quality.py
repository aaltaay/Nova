"""The cached scanner row keeps whether its price is a print or IB's prior close (QA C50).

Only the WebSocket price patch carried ``quote_quality``; a REST reload then
served the prior close as a live price with an invented 0.00% change and gap.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constants_ibkr import IBKR_QUOTE_QUALITY_CLOSE_FALLBACK  # noqa: E402
from ibkr import l1_apply  # noqa: E402
from runtime_state.state import ScannerRuntimeState  # noqa: E402


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr("hod_tick_feed.feed_hod_on_tick", lambda *a, **k: None)
    monkeypatch.setattr("volume_boost.observe_l1", lambda *a, **k: None)
    l1_apply.reset_row_indexes_for_tests()
    s = ScannerRuntimeState()
    s.gainer_cache = [{"symbol": "CLSF", "price": 3.0, "prev_close": 3.0, "volume": 10}]
    s.loser_cache = [{"symbol": "LOSR", "price": 2.0, "prev_close": 2.5, "volume": 10}]
    yield s
    l1_apply.reset_row_indexes_for_tests()


def _apply(state, symbol, price, quality=None):
    return l1_apply.apply_l1_quote(symbol, price, 1000, 3.0, 100.0, quote_quality=quality, get_state=lambda: state)


def test_a_prior_close_fallback_is_stamped_on_the_cached_row(state):
    patch = _apply(state, "CLSF", 3.0, IBKR_QUOTE_QUALITY_CLOSE_FALLBACK)
    assert state.gainer_cache[0]["quote_quality"] == IBKR_QUOTE_QUALITY_CLOSE_FALLBACK
    assert patch["quote_quality"] == IBKR_QUOTE_QUALITY_CLOSE_FALLBACK


def test_a_real_print_states_a_print(state):
    _apply(state, "CLSF", 3.0, IBKR_QUOTE_QUALITY_CLOSE_FALLBACK)
    _apply(state, "CLSF", 3.2)
    row = state.gainer_cache[0]
    # The key stays, as None: the client never relabels a stated print.
    assert "quote_quality" in row and row["quote_quality"] is None
    assert row["price"] == 3.2


def test_losers_carry_it_too(state):
    _apply(state, "LOSR", 2.5, IBKR_QUOTE_QUALITY_CLOSE_FALLBACK)
    assert state.loser_cache[0]["quote_quality"] == IBKR_QUOTE_QUALITY_CLOSE_FALLBACK
