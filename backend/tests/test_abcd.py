"""Unit tests for the ABCD setup module — mock bars only, no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy.abcd import evaluate_abcd


def _candidate(**overrides) -> dict:
    base = {
        "symbol": "MOCK",
        "price": 3.60,
        "change_pct": 0.20,
        "rel_volume": 8.0,
        "has_news": True,
        "float": 5_000_000,
    }
    base.update(overrides)
    return base


def _perfect_bars() -> list[dict]:
    """4 flat padding bars (for the 9-EMA window) + A (swing low) + impulsive
    move to B (swing high) + a shallow pullback to C holding the 9 EMA."""
    pad = [{"o": 3.05, "h": 3.07, "l": 3.03, "c": 3.05} for _ in range(4)]
    return pad + [
        {"o": 2.95, "h": 3.00, "l": 2.90, "c": 2.98},  # point A (swing low, l=2.90)
        {"o": 2.98, "h": 3.20, "l": 3.00, "c": 3.15},
        {"o": 3.15, "h": 3.50, "l": 3.15, "c": 3.48},  # point B (swing high, h=3.50)
        {"o": 3.48, "h": 3.45, "l": 3.30, "c": 3.32},  # pullback candle
        {"o": 3.32, "h": 3.34, "l": 3.25, "c": 3.30},  # point C (pullback low, l=3.25)
    ]


class TestPerfectSetup:
    def test_eligible_when_price_breaks_above_point_b(self):
        signal = evaluate_abcd(_candidate(price=3.60), _perfect_bars())
        assert signal.pattern_found is True
        assert signal.holds_9ema is True
        assert signal.triggered is True
        assert signal.eligible is True
        assert signal.would_execute is False

    def test_entry_stop_target_math_uses_20_cent_stop(self):
        signal = evaluate_abcd(_candidate(price=3.60), _perfect_bars())
        assert signal.entry_price == 3.60
        assert signal.stop_price == 3.40  # entry - $0.20
        assert signal.target_price == 4.00  # entry + risk * 2:1

    def test_not_triggered_when_price_below_point_b(self):
        signal = evaluate_abcd(_candidate(price=3.30), _perfect_bars())
        assert signal.pattern_found is True
        assert signal.triggered is False
        assert signal.eligible is False
        assert signal.entry_price is None

    def test_ab_move_percent_computed_from_a_to_b(self):
        signal = evaluate_abcd(_candidate(), _perfect_bars())
        # (3.50 - 2.90) / 2.90 * 100 ≈ 20.7%
        assert signal.ab_move_pct == round((3.50 - 2.90) / 2.90 * 100, 2)


class TestPatternAbsent:
    def test_peak_at_first_bar_has_no_room_for_point_a(self):
        bars = [
            {"o": 3.50, "h": 3.60, "l": 3.45, "c": 3.55},
            {"o": 3.55, "h": 3.58, "l": 3.40, "c": 3.42},
            {"o": 3.42, "h": 3.44, "l": 3.35, "c": 3.38},
        ]
        signal = evaluate_abcd(_candidate(), bars)
        assert signal.pattern_found is False

    def test_peak_at_last_bar_has_no_pullback_yet(self):
        bars = [
            {"o": 3.00, "h": 3.05, "l": 2.95, "c": 3.02},
            {"o": 3.02, "h": 3.20, "l": 3.00, "c": 3.15},
            {"o": 3.15, "h": 3.50, "l": 3.10, "c": 3.48},
        ]
        signal = evaluate_abcd(_candidate(), bars)
        assert signal.pattern_found is False

    def test_too_few_bars_returns_pattern_not_found(self):
        signal = evaluate_abcd(_candidate(), [{"o": 1, "h": 1, "l": 1, "c": 1}])
        assert signal.pattern_found is False


class TestPatternInvalidation:
    def test_small_ab_move_fails_minimum_threshold(self):
        # A flat, choppy tape where the A-to-B move is well under 5%.
        bars = [
            {"o": 3.01, "h": 3.02, "l": 3.00, "c": 3.02},  # point A, low=3.00
            {"o": 3.02, "h": 3.10, "l": 3.01, "c": 3.08},
            {"o": 3.08, "h": 3.12, "l": 3.05, "c": 3.10},  # point B, high=3.12
            {"o": 3.10, "h": 3.09, "l": 3.06, "c": 3.07},
            {"o": 3.07, "h": 3.08, "l": 3.04, "c": 3.05},  # point C
        ]
        signal = evaluate_abcd(_candidate(), bars)
        assert signal.ab_move_pct is not None and signal.ab_move_pct < 5.0
        assert signal.pattern_found is False

    def test_deep_retrace_invalidates(self):
        bars = _perfect_bars()
        bars[-1] = {**bars[-1], "l": 2.92, "c": 2.95}  # C retraces almost the whole A-B move
        signal = evaluate_abcd(_candidate(price=3.60), bars)
        assert signal.retrace_pct is not None and signal.retrace_pct >= 0.50
        assert signal.pattern_found is False

    def test_failing_five_pillars_is_never_eligible(self):
        signal = evaluate_abcd(_candidate(has_news=False), _perfect_bars())
        assert signal.five_pillars.all_pass is False
        assert signal.eligible is False
