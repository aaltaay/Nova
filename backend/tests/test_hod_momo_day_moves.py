"""HOD Momo's change and gap: the quote's previous close, else the board row's; yesterday's never carried over."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import hod_momo as hm
import hod_momo_day_moves as moves
from hod_momo_models import TickerSnap
from hod_momo_session import clear_day_fields
from tests.conftest import reset_hod_engine_state


def _boards(monkeypatch, gappers=(), gainers=(), afterhours=()):
    state = SimpleNamespace(gapper_cache=list(gappers), gainer_cache=list(gainers), afterhours_cache=list(afterhours))
    monkeypatch.setattr("runtime_state.get_runtime_state", lambda: state)


def test_change_from_the_quote_close_when_it_has_one(monkeypatch):
    _boards(monkeypatch, gappers=[{"symbol": "PFAI", "prev_close": 9.99}])
    change, gap = moves.day_moves("PFAI", 5.22, {"prev_close": 2.61})
    assert change == pytest.approx(100.0)
    assert gap is None  # no open before 09:30: unknown, never 0


def test_change_from_the_board_row_when_the_quote_has_no_close(monkeypatch):
    # PFAI 2026-10-13: Gappers carried prev_close 2.61 while HOD alerted all premarket with no change %.
    _boards(monkeypatch, gainers=[{"symbol": "OTHER", "prev_close": 1.0}],
            gappers=[{"symbol": "pfai", "previous_close": 2.61}])
    change, _ = moves.day_moves("PFAI", 5.94, {"prev_close": None})
    assert change == pytest.approx((5.94 - 2.61) / 2.61 * 100.0)


def test_gap_from_todays_open(monkeypatch):
    _boards(monkeypatch)
    change, gap = moves.day_moves("ABC", 11.0, {"prev_close": 10.0, "open": 10.5})
    assert change == pytest.approx(10.0)
    assert gap == pytest.approx(5.0)


def test_no_close_anywhere_is_unknown(monkeypatch):
    _boards(monkeypatch)
    assert moves.day_moves("ABC", 11.0, {"prev_close": 0}) == (None, None)


def test_session_roll_forgets_the_days_figures_and_keeps_the_slow_ones():
    snap = TickerSnap(price=3.03, change_pct=58.6, gap_pct=4.0, volume=2_000_000, rvol=9.0, rvol_5min=3.0,
                      float_shares=3_500_000, avg_volume=500_000.0, fifty_two_week_high=7.0)
    clear_day_fields({"DCX": snap})
    assert (snap.change_pct, snap.gap_pct, snap.volume, snap.rvol, snap.rvol_5min) == (None, None, None, None, None)
    assert (snap.float_shares, snap.avg_volume, snap.fifty_two_week_high) == (3_500_000, 500_000.0, 7.0)


def test_strategy_5_reads_a_board_close_change(monkeypatch):
    """End to end through update_ticker_snapshot: the snap carries the change Strategy 5 needs."""
    reset_hod_engine_state()
    _boards(monkeypatch, gappers=[{"symbol": "PFAI", "prev_close": 2.61}])
    change, gap = moves.day_moves("PFAI", 4.6, {"prev_close": None})
    hm.update_ticker_snapshot("PFAI", price=4.6, change_pct=change, gap_pct=gap)
    assert hm.get_state().ticker_snaps["PFAI"].change_pct == pytest.approx(76.245, abs=0.01)
