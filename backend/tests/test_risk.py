"""Unit tests for the risk / discipline state machine — no network, no orders."""
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import journal.db as journal_db
import nova_os.events_db as events_db
import strategy.risk as risk_mod
from journal.store import record_trade
from strategy.risk import RiskState, validate_trade_plan

_ET = ZoneInfo("America/New_York")


@pytest.fixture(autouse=True)
def isolated_events_db(tmp_path, monkeypatch):
    """RiskState._halt() journals a risk_halt system event — isolate so
    walk-away-guardrail tests never touch the real nova_os_events.db."""
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    events_db.init_db()
    yield


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

    def test_halt_journals_a_risk_halt_system_event(self):
        """The frontend attention strip has nothing to key off of unless a
        halt writes an append-only receipt the instant it trips."""
        from nova_os.events import KIND_SYSTEM, get_events

        state = RiskState()
        state.record_trade_result(-500.0)
        rows = get_events(kind=KIND_SYSTEM)
        halts = [r for r in rows if r["payload"].get("event") == "risk_halt"]
        assert len(halts) == 1
        assert "max loss" in halts[0]["payload"]["reason"].lower()

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
        assert state.losses_today == 0
        assert state.trades_today == 0
        assert state.halted is False
        assert state.halt_reason is None


class TestLossesTodayIsNotConsecutive:
    def test_losses_today_survives_an_intervening_win(self):
        """losses_today is the daily-loss-policy counter Nova OS uses
        (codes.loss_policy_mode) — unlike consecutive_losses, a win in
        between must NOT reset it."""
        state = RiskState()
        state.record_trade_result(-10.0)
        state.record_trade_result(20.0)  # win — resets consecutive_losses
        state.record_trade_result(-10.0)
        assert state.consecutive_losses == 1
        assert state.losses_today == 2


@pytest.fixture(autouse=True)
def isolated_journal(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_db, "cache_dir", lambda: tmp_path)
    journal_db.init_db()
    risk_mod._state = RiskState()
    yield
    risk_mod._state = RiskState()


class TestReconstructFromJournal:
    def _session_start(self) -> float:
        now_et = datetime.now(_ET)
        start = now_et.replace(hour=4, minute=0, second=0, microsecond=0)
        if now_et.hour < 4:
            from datetime import timedelta

            start -= timedelta(days=1)
        return start.timestamp()

    def test_replays_todays_closed_trades(self):
        session_start = self._session_start()
        record_trade(
            symbol="AAPL", setup="gap_and_go", side="long", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            exit_price=4.9, pnl=-10.0, adherent=True,
            opened_ts=session_start + 60, closed_ts=session_start + 120,
        )
        record_trade(
            symbol="TSLA", setup="gap_and_go", side="long", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            exit_price=5.2, pnl=20.0, adherent=True,
            opened_ts=session_start + 200, closed_ts=session_start + 260,
        )
        summary = risk_mod.reconstruct_from_journal()
        assert summary["trades_today"] == 2
        assert summary["losses_today"] == 1
        assert summary["daily_realized_pnl"] == pytest.approx(10.0)

    def test_ignores_trades_before_session_start(self):
        session_start = self._session_start()
        record_trade(
            symbol="OLD", setup="gap_and_go", side="long", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            exit_price=4.9, pnl=-10.0, adherent=True,
            opened_ts=session_start - 3600, closed_ts=session_start - 3000,
        )
        summary = risk_mod.reconstruct_from_journal()
        assert summary["trades_today"] == 0
        assert summary["daily_realized_pnl"] == 0.0

    def test_reconstructed_halt_blocks_can_trade(self):
        """A restart must not silently forget a halt that already fired —
        replaying the day's trades must re-derive the same halted state."""
        session_start = self._session_start()
        for i in range(3):
            record_trade(
                symbol=f"SYM{i}", setup="gap_and_go", side="long", qty=100,
                entry_price=5.0, stop_price=4.9, target_price=5.2,
                exit_price=4.9, pnl=-10.0, adherent=True,
                opened_ts=session_start + i * 60, closed_ts=session_start + i * 60 + 30,
            )
        risk_mod.reconstruct_from_journal()
        can_trade, reason = risk_mod.can_trade()
        assert can_trade is False
        assert "losses in a row" in reason.lower()

    def test_ignores_mock_trades(self):
        session_start = self._session_start()
        record_trade(
            symbol="MOCK", setup="gap_and_go", side="long", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            exit_price=4.9, pnl=-10.0, adherent=True,
            opened_ts=session_start + 60, closed_ts=session_start + 120,
            is_mock=True,
        )
        summary = risk_mod.reconstruct_from_journal()
        assert summary["trades_today"] == 0


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
        assert any("zero" in i.lower() for i in issues)

    def test_stop_above_entry_blocks_long(self):
        ok, issues = validate_trade_plan(entry_price=5.00, stop_price=5.10, target_price=5.30)
        assert ok is False
        assert any("below entry" in i for i in issues)

    def test_target_below_entry_blocks_long(self):
        ok, issues = validate_trade_plan(entry_price=5.00, stop_price=4.90, target_price=4.80)
        assert ok is False
        assert any("above entry" in i for i in issues)

    def test_exact_max_stop_with_2_to_1_passes(self):
        ok, issues = validate_trade_plan(entry_price=5.00, stop_price=4.80, target_price=5.40)
        assert ok is True
        assert issues == []
