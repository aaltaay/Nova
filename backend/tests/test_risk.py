"""Unit tests for the risk / discipline state machine — no network, no orders."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy.risk import RiskState, validate_trade_plan


class TestPositionSizing:
    def test_starts_at_quarter_size(self):
        state = RiskState()
        assert state.position_size_shares() == 25

    def test_full_size_after_profit_cushion(self):
        state = RiskState()
        state.record_trade_result(150.0)  # 1/4 of $500 daily goal
        assert state.position_size_shares() == 100

    def test_cut_size_after_meaningful_loss(self):
        state = RiskState()
        state.record_trade_result(-60.0)  # > 10% of $500 daily goal
        assert state.position_size_shares() == 12  # 25 * 0.5, floored

    def test_sizing_reacts_to_current_pnl_not_historical_peak(self):
        """Size tracks the CURRENT daily P&L, not the best point of the day —
        giving back a profit cushion drops you back to quarter size, and a
        big enough net loss still applies the size-cut multiplier."""
        state = RiskState()
        state.record_trade_result(150.0)   # cushion reached -> full size
        assert state.position_size_shares() == 100
        state.record_trade_result(-250.0)  # net pnl now -100 (> 10% of goal in losses)
        assert state.daily_realized_pnl == -100.0
        assert state.position_size_shares() == 12  # back to quarter size, then cut in half


class TestWalkAwayGuardrails:
    def test_not_halted_initially(self):
        state = RiskState()
        can_trade, reason = state.can_trade()
        assert can_trade is True
        assert reason == "OK"

    def test_daily_max_loss_halts(self):
        state = RiskState()
        state.record_trade_result(-500.0)
        can_trade, reason = state.can_trade()
        assert can_trade is False
        assert "max loss" in reason.lower()

    def test_three_losses_in_a_row_halts(self):
        state = RiskState()
        state.record_trade_result(-10.0)
        state.record_trade_result(-10.0)
        assert state.can_trade()[0] is True
        state.record_trade_result(-10.0)
        can_trade, reason = state.can_trade()
        assert can_trade is False
        assert "losses in a row" in reason.lower()

    def test_a_win_resets_the_losing_streak(self):
        state = RiskState()
        state.record_trade_result(-10.0)
        state.record_trade_result(-10.0)
        state.record_trade_result(20.0)  # win breaks the streak
        state.record_trade_result(-10.0)
        state.record_trade_result(-10.0)
        assert state.can_trade()[0] is True  # only 2 in a row since the win

    def test_giving_back_half_of_peak_profit_halts(self):
        state = RiskState()
        state.record_trade_result(100.0)  # peak = 100
        state.record_trade_result(-50.0)  # gave back 50% of peak
        can_trade, reason = state.can_trade()
        assert can_trade is False
        assert "gave back" in reason.lower()

    def test_halt_is_sticky_until_reset_day(self):
        state = RiskState()
        state.record_trade_result(-500.0)
        assert state.can_trade()[0] is False
        state.record_trade_result(500.0)  # big win — should NOT un-halt
        assert state.can_trade()[0] is False
        state.reset_day()
        assert state.can_trade()[0] is True

    def test_reset_day_clears_all_state(self):
        state = RiskState()
        state.record_trade_result(-500.0)
        state.reset_day()
        assert state.daily_realized_pnl == 0.0
        assert state.peak_daily_pnl == 0.0
        assert state.consecutive_losses == 0
        assert state.trades_today == 0
        assert state.halted is False
        assert state.halt_reason is None


class TestValidateTradePlan:
    def test_perfect_plan_passes(self):
        ok, issues = validate_trade_plan(entry_price=5.00, stop_price=4.90, target_price=5.20)
        assert ok is True
        assert issues == []

    def test_stop_too_wide_blocks(self):
        ok, issues = validate_trade_plan(entry_price=5.00, stop_price=4.50, target_price=6.00)
        assert ok is False
        assert any("exceeds" in i for i in issues)

    def test_ratio_below_floor_blocks(self):
        ok, issues = validate_trade_plan(entry_price=5.00, stop_price=4.90, target_price=5.05)
        assert ok is False
        assert any("ratio" in i for i in issues)

    def test_zero_stop_distance_blocks(self):
        ok, issues = validate_trade_plan(entry_price=5.00, stop_price=5.00, target_price=5.20)
        assert ok is False
