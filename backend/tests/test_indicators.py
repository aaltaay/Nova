"""Unit tests for shared pure indicator helpers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy.indicators import closes, ema, is_green, is_red


class TestEma:
    def test_too_few_values_returns_all_none(self):
        assert ema([1.0, 2.0], 9) == [None, None]

    def test_seeds_with_sma_at_period_index(self):
        values = [1.0, 2.0, 3.0]
        result = ema(values, 3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] == 2.0  # SMA(1,2,3)

    def test_length_matches_input(self):
        values = list(range(20))
        result = ema([float(v) for v in values], 9)
        assert len(result) == len(values)

    def test_trend_up_ema_increases(self):
        values = [float(v) for v in range(1, 15)]
        result = ema(values, 9)
        non_none = [v for v in result if v is not None]
        assert non_none == sorted(non_none)

    def test_zero_period_returns_all_none(self):
        assert ema([1.0, 2.0], 0) == [None, None]


class TestCandleColor:
    def test_close_above_open_is_green(self):
        assert is_green({"o": 1.0, "c": 1.5}) is True
        assert is_red({"o": 1.0, "c": 1.5}) is False

    def test_close_below_open_is_red(self):
        assert is_green({"o": 1.5, "c": 1.0}) is False
        assert is_red({"o": 1.5, "c": 1.0}) is True

    def test_equal_open_close_counts_as_green(self):
        assert is_green({"o": 1.0, "c": 1.0}) is True

    def test_missing_data_is_not_green(self):
        assert is_green({"o": None, "c": 1.0}) is False
        assert is_green({}) is False


class TestCloses:
    def test_extracts_close_values_in_order(self):
        bars = [{"c": 1.0}, {"c": 2.0}, {"c": 3.0}]
        assert closes(bars) == [1.0, 2.0, 3.0]

    def test_missing_close_defaults_to_zero(self):
        assert closes([{"c": None}]) == [0.0]
