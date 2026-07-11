"""Unit tests for the setup aggregator — combines Gap and Go, Bull Flag, ABCD."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy.setups import evaluate_setups


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


def _bull_flag_bars() -> list[dict]:
    return [
        {"o": 2.70, "h": 2.85, "l": 2.67, "c": 2.85},
        {"o": 2.85, "h": 3.00, "l": 2.82, "c": 3.00},
        {"o": 3.00, "h": 3.15, "l": 2.97, "c": 3.15},
        {"o": 3.15, "h": 3.30, "l": 3.12, "c": 3.30},
        {"o": 3.30, "h": 3.45, "l": 3.27, "c": 3.45},
        {"o": 3.45, "h": 3.60, "l": 3.42, "c": 3.60},
        {"o": 3.60, "h": 3.90, "l": 3.57, "c": 3.90},
        {"o": 3.84, "h": 3.87, "l": 3.66, "c": 3.72},
        {"o": 3.72, "h": 3.75, "l": 3.57, "c": 3.60},
    ]


class TestEvaluateSetups:
    def test_shape_contains_all_three_setups(self):
        result = evaluate_setups(_candidate(), _bull_flag_bars())
        assert set(result) >= {"symbol", "eligible_setups", "any_eligible", "gap_and_go", "bull_flag", "abcd"}
        assert result["symbol"] == "MOCK"

    def test_bull_flag_eligible_flows_into_eligible_setups(self):
        result = evaluate_setups(_candidate(price=4.00), _bull_flag_bars())
        assert "bull_flag" in result["eligible_setups"]
        assert result["any_eligible"] is True

    def test_no_pattern_no_eligible_setups(self):
        flat_bars = [{"o": 3.0, "h": 3.01, "l": 2.99, "c": 3.0} for _ in range(9)]
        result = evaluate_setups(_candidate(), flat_bars)
        assert result["eligible_setups"] == []
        assert result["any_eligible"] is False

    def test_failing_five_pillars_yields_no_eligible_setups_even_with_pattern(self):
        result = evaluate_setups(_candidate(has_news=False, price=4.00), _bull_flag_bars())
        assert result["eligible_setups"] == []
        assert result["any_eligible"] is False

    def test_never_sets_would_execute_true_anywhere(self):
        result = evaluate_setups(_candidate(price=4.00), _bull_flag_bars())
        for name in ("gap_and_go", "bull_flag", "abcd"):
            assert result[name]["would_execute"] is False
