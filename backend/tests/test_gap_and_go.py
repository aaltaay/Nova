"""
Unit tests for Gap and Go setup detection — mock bars, no network, no orders.
"""
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy.gap_and_go import evaluate_gap_and_go

_ET = ZoneInfo("America/New_York")


def _mock_candidate(**overrides) -> dict:
    base = {
        "symbol": "MOCK",
        "price": 5.50,           # above the mock premarket high of 5.20
        "change_pct": 0.18,
        "rel_volume": 7.0,
        "has_news": True,
        "float": 6_000_000,
    }
    base.update(overrides)
    return base


def _mock_bars(today: str = "2026-07-10") -> list[dict]:
    """Pre-market bars (high 5.20) followed by one 9:31 AM bar."""
    return [
        {"t": f"{today}T08:00:00Z", "h": 5.00, "l": 4.80, "o": 4.85, "c": 4.95, "v": 10000},
        {"t": f"{today}T09:00:00Z", "h": 5.20, "l": 4.90, "o": 4.95, "c": 5.10, "v": 20000},
        {"t": f"{today}T13:31:00Z", "h": 5.55, "l": 5.30, "o": 5.30, "c": 5.50, "v": 50000},
    ]


class TestNeverPlacesOrders:
    def test_would_execute_is_always_false(self):
        now = datetime(2026, 7, 10, 9, 45, tzinfo=_ET)
        signal = evaluate_gap_and_go(_mock_candidate(), _mock_bars(), now_et=now)
        assert signal.would_execute is False


class TestTimeWindow:
    def test_inside_window_930_to_1000(self):
        now = datetime(2026, 7, 10, 9, 45, tzinfo=_ET)
        signal = evaluate_gap_and_go(_mock_candidate(), _mock_bars(), now_et=now)
        assert signal.in_time_window is True

    def test_before_window_is_excluded(self):
        now = datetime(2026, 7, 10, 9, 0, tzinfo=_ET)
        signal = evaluate_gap_and_go(_mock_candidate(), _mock_bars(), now_et=now)
        assert signal.in_time_window is False
        assert signal.eligible is False

    def test_after_window_is_excluded(self):
        now = datetime(2026, 7, 10, 10, 30, tzinfo=_ET)
        signal = evaluate_gap_and_go(_mock_candidate(), _mock_bars(), now_et=now)
        assert signal.in_time_window is False
        assert signal.eligible is False


class TestPremarketHighBreak:
    def test_price_above_premarket_high_triggers(self):
        now = datetime(2026, 7, 10, 9, 45, tzinfo=_ET)
        signal = evaluate_gap_and_go(_mock_candidate(price=5.50), _mock_bars(), now_et=now)
        assert signal.premarket_high == 5.20
        assert signal.triggered is True

    def test_price_below_premarket_high_does_not_trigger(self):
        now = datetime(2026, 7, 10, 9, 45, tzinfo=_ET)
        signal = evaluate_gap_and_go(_mock_candidate(price=5.10), _mock_bars(), now_et=now)
        assert signal.triggered is False
        assert signal.eligible is False

    def test_no_premarket_bars_means_no_premarket_high(self):
        now = datetime(2026, 7, 10, 9, 45, tzinfo=_ET)
        bars = [{"t": "2026-07-10T13:31:00Z", "h": 5.55, "l": 5.30, "o": 5.30, "c": 5.50, "v": 50000}]
        signal = evaluate_gap_and_go(_mock_candidate(), bars, now_et=now)
        assert signal.premarket_high is None
        assert signal.triggered is False


class TestFivePillarsGate:
    def test_fails_five_pillars_blocks_eligibility_even_if_triggered(self):
        now = datetime(2026, 7, 10, 9, 45, tzinfo=_ET)
        candidate = _mock_candidate(rel_volume=1.0)  # fails relative volume pillar
        signal = evaluate_gap_and_go(candidate, _mock_bars(), now_et=now)
        assert signal.triggered is True          # price action condition still true
        assert signal.five_pillars.all_pass is False
        assert signal.eligible is False           # but overall signal is blocked


class TestEligibleSignalMath:
    def test_full_signal_has_entry_stop_target(self):
        now = datetime(2026, 7, 10, 9, 45, tzinfo=_ET)
        signal = evaluate_gap_and_go(_mock_candidate(price=5.50), _mock_bars(), now_et=now)
        assert signal.eligible is True
        assert signal.entry_price == 5.50
        # stop = entry - 0.20 (GAP_AND_GO_MAX_STOP_DOLLARS)
        assert signal.stop_price == 5.30
        # risk = 0.20, target = entry + risk * 2.0 (GAP_AND_GO_MIN_PROFIT_LOSS_RATIO)
        assert signal.target_price == 5.90
        assert any("No order has been placed" in note for note in signal.notes)

    def test_to_dict_never_implies_execution(self):
        now = datetime(2026, 7, 10, 9, 45, tzinfo=_ET)
        signal = evaluate_gap_and_go(_mock_candidate(price=5.50), _mock_bars(), now_et=now)
        payload = signal.to_dict()
        assert payload["would_execute"] is False
        assert payload["eligible"] is True
