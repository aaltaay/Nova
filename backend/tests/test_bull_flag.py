"""Unit tests for the Bull Flag setup module — mock bars only, no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy.bull_flag import evaluate_bull_flag


def _candidate(**overrides) -> dict:
    base = {
        "symbol": "MOCK",
        "price": 4.00,
        "change_pct": 0.20,
        "rel_volume": 8.0,
        "has_news": True,
        "float": 5_000_000,
    }
    base.update(overrides)
    return base


def _perfect_bars() -> list[dict]:
    """7 green flagpole candles + 2 red pullback candles holding the 9 EMA,
    retracing well under 50% of the pole, not breaking back above its high."""
    return [
        {"o": 2.70, "h": 2.85, "l": 2.67, "c": 2.85},
        {"o": 2.85, "h": 3.00, "l": 2.82, "c": 3.00},
        {"o": 3.00, "h": 3.15, "l": 2.97, "c": 3.15},
        {"o": 3.15, "h": 3.30, "l": 3.12, "c": 3.30},
        {"o": 3.30, "h": 3.45, "l": 3.27, "c": 3.45},
        {"o": 3.45, "h": 3.60, "l": 3.42, "c": 3.60},
        {"o": 3.60, "h": 3.90, "l": 3.57, "c": 3.90},  # flagpole peak, high=3.90
        {"o": 3.84, "h": 3.87, "l": 3.66, "c": 3.72},  # pullback 1 (red)
        {"o": 3.72, "h": 3.75, "l": 3.57, "c": 3.60},  # pullback 2 (red), low=3.57
    ]


class TestPerfectSetup:
    def test_eligible_when_price_triggers_above_flagpole_high(self):
        signal = evaluate_bull_flag(_candidate(price=4.00), _perfect_bars())
        assert signal.pattern_found is True
        assert signal.holds_9ema is True
        assert signal.triggered is True
        assert signal.eligible is True
        assert signal.would_execute is False

    def test_entry_stop_target_math(self):
        signal = evaluate_bull_flag(_candidate(price=4.00), _perfect_bars())
        assert signal.entry_price == 4.00
        assert signal.stop_price == 3.57  # pullback low
        # risk = 0.43; target = 4.00 + 0.43 * 2.0 = 4.86
        assert signal.target_price == 4.86

    def test_not_triggered_when_price_below_flagpole_high(self):
        signal = evaluate_bull_flag(_candidate(price=3.50), _perfect_bars())
        assert signal.pattern_found is True
        assert signal.triggered is False
        assert signal.eligible is False
        assert signal.entry_price is None


class TestPatternAbsent:
    def test_no_pullback_returns_pattern_not_found(self):
        all_green = [
            {"o": 1.0 + i * 0.1, "h": 1.1 + i * 0.1, "l": 0.95 + i * 0.1, "c": 1.08 + i * 0.1}
            for i in range(9)
        ]
        signal = evaluate_bull_flag(_candidate(), all_green)
        assert signal.pattern_found is False
        assert signal.eligible is False

    def test_too_few_flagpole_candles_fails(self):
        bars = [
            {"o": 3.00, "h": 3.10, "l": 2.98, "c": 3.10},  # only 1 green candle
            {"o": 3.10, "h": 3.15, "l": 3.00, "c": 3.05},  # red
            {"o": 3.05, "h": 3.08, "l": 2.95, "c": 2.98},  # red
        ]
        signal = evaluate_bull_flag(_candidate(), bars)
        assert signal.pattern_found is False


class TestPatternInvalidation:
    def test_pullback_breaking_prior_high_invalidates(self):
        bars = _perfect_bars()
        bars[-2] = {**bars[-2], "h": 3.95}  # pullback candle now exceeds flagpole high 3.90
        signal = evaluate_bull_flag(_candidate(price=4.00), bars)
        assert signal.pattern_found is False
        assert signal.eligible is False

    def test_deep_retrace_invalidates(self):
        bars = _perfect_bars()
        bars[-1] = {**bars[-1], "l": 2.90, "c": 2.95}  # pullback retraces almost the whole pole
        signal = evaluate_bull_flag(_candidate(price=4.00), bars)
        assert signal.retrace_pct is not None and signal.retrace_pct >= 0.50
        assert signal.pattern_found is False

    def test_failing_five_pillars_is_never_eligible(self):
        signal = evaluate_bull_flag(_candidate(has_news=False), _perfect_bars())
        assert signal.five_pillars.all_pass is False
        assert signal.eligible is False
