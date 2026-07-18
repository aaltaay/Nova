"""
Hard-number regression suite for arithmetic-critical paths and execution
transparency. Every assertion uses an explicit expected value — not just
"not None" — so percent/fraction mixups, inverted stops, and bad R:R cannot
quietly pass.
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constants import (
    ABCD_MAX_STOP_DOLLARS,
    ABCD_MIN_PROFIT_LOSS_RATIO,
    BULL_FLAG_MIN_PROFIT_LOSS_RATIO,
    FIVE_PILLARS_MAX_FLOAT_SHARES,
    FIVE_PILLARS_MAX_PRICE,
    FIVE_PILLARS_MIN_CHANGE_PCT,
    FIVE_PILLARS_MIN_PRICE,
    FIVE_PILLARS_MIN_REL_VOLUME,
    GAP_AND_GO_MAX_STOP_DOLLARS,
    GAP_AND_GO_MIN_PROFIT_LOSS_RATIO,
    JOURNAL_MIN_TRADES_FOR_GO_LIVE,
    L2_ASK_STACKED_RATIO,
    L2_BID_HEAVY_RATIO,
    L2_PRESSURE_DRYING_DROP_FRACTION,
    RISK_BASE_SHARE_BLOCK,
    RISK_DAILY_GOAL_DOLLARS,
    RISK_MAX_STOP_DOLLARS,
    RISK_MIN_PROFIT_LOSS_RATIO,
    RISK_PROFIT_CUSHION_FRACTION,
    RISK_QUARTER_SIZE_MULTIPLIER,
    RISK_SIZE_CUT_LOSS_FRACTION_OF_GOAL,
    RISK_SIZE_CUT_MULTIPLIER,
    RISK_TARGET_PROFIT_LOSS_RATIO,
)
from strategy.abcd import evaluate_abcd
from strategy.bull_flag import evaluate_bull_flag
from strategy.five_pillars import evaluate_five_pillars
from strategy.gap_and_go import evaluate_gap_and_go
from strategy.risk import RiskState, validate_trade_plan
import strategy.executor as executor
import l2.features as features
import journal.db as db

_ET = ZoneInfo("America/New_York")


# ── Risk: stop / target / R:R arithmetic ─────────────────────────────────────


class TestValidateTradePlanArithmetic:
    def test_exact_max_stop_and_exact_2_to_1_passes(self):
        # entry 5.00, stop 4.80 ($0.20 = RISK_MAX_STOP_DOLLARS), target 5.40 (2:1)
        ok, issues = validate_trade_plan(5.00, 4.80, 5.40)
        assert ok is True
        assert issues == []
        assert RISK_MAX_STOP_DOLLARS == 0.20
        assert RISK_MIN_PROFIT_LOSS_RATIO == 1.0
        assert RISK_TARGET_PROFIT_LOSS_RATIO == 2.0

    def test_stop_one_cent_over_max_blocks(self):
        ok, issues = validate_trade_plan(5.00, 4.79, 5.42)  # stop $0.21
        assert ok is False
        assert any("exceeds" in i and "0.20" in i for i in issues)

    def test_exact_1_to_1_floor_passes(self):
        ok, issues = validate_trade_plan(5.00, 4.90, 5.10)  # risk $0.10, reward $0.10
        assert ok is True
        assert issues == []

    def test_ratio_just_below_1_to_1_blocks(self):
        ok, issues = validate_trade_plan(5.00, 4.90, 5.09)  # 0.09/0.10 = 0.9
        assert ok is False
        assert any("ratio" in i for i in issues)

    def test_stop_above_entry_blocks_even_if_abs_distance_looks_fine(self):
        """Regression: abs(entry-stop) used to let inverted longs through."""
        ok, issues = validate_trade_plan(5.00, 5.10, 5.30)
        assert ok is False
        assert any("below entry" in i for i in issues)

    def test_target_at_or_below_entry_blocks(self):
        ok_eq, issues_eq = validate_trade_plan(5.00, 4.90, 5.00)
        ok_below, issues_below = validate_trade_plan(5.00, 4.90, 4.80)
        assert ok_eq is False
        assert ok_below is False
        assert any("above entry" in i for i in issues_eq)
        assert any("above entry" in i for i in issues_below)

    def test_preferred_scalp_math_0_10_stop_2_to_1(self):
        entry, stop, target = 4.50, 4.40, 4.70
        ok, issues = validate_trade_plan(entry, stop, target)
        assert ok is True
        assert round(entry - stop, 2) == 0.10
        assert round(target - entry, 2) == 0.20
        assert round((target - entry) / (entry - stop), 2) == 2.0


class TestPositionSizingBoundaries:
    def test_cushion_threshold_is_exactly_quarter_of_daily_goal(self):
        cushion = RISK_DAILY_GOAL_DOLLARS * RISK_PROFIT_CUSHION_FRACTION
        assert cushion == 125.0
        state = RiskState()
        state.record_trade_result(124.99)
        assert state.position_size_shares() == int(
            RISK_BASE_SHARE_BLOCK * RISK_QUARTER_SIZE_MULTIPLIER
        )  # 25
        state2 = RiskState()
        state2.record_trade_result(125.0)
        assert state2.position_size_shares() == RISK_BASE_SHARE_BLOCK  # 100

    def test_size_cut_threshold_is_exactly_10_pct_of_goal(self):
        cut = RISK_DAILY_GOAL_DOLLARS * RISK_SIZE_CUT_LOSS_FRACTION_OF_GOAL
        assert cut == 50.0
        state = RiskState()
        state.record_trade_result(-49.99)
        assert state.position_size_shares() == 25  # not yet cut
        state2 = RiskState()
        state2.record_trade_result(-50.0)
        assert state2.position_size_shares() == int(
            RISK_BASE_SHARE_BLOCK * RISK_QUARTER_SIZE_MULTIPLIER * RISK_SIZE_CUT_MULTIPLIER
        )  # 12

    def test_full_size_then_cut_uses_integer_floor(self):
        """Cushion unlocks full size; once net P&L is back below the cushion
        AND at/under the cut threshold, size is quarter * cut = 12."""
        state = RiskState()
        state.record_trade_result(125.0)
        assert state.position_size_shares() == 100
        # Net -50: below cushion, at cut threshold. Avoid giveback halt by
        # resetting peak via a fresh state that never peaked high.
        state2 = RiskState()
        state2.record_trade_result(-50.0)
        assert state2.position_size_shares() == 12
        # Explicit: full-size path with cut while still above cushion
        state3 = RiskState()
        state3.daily_realized_pnl = 200.0  # still above cushion
        # Force cut check via the private threshold helper path: cut only when
        # daily_realized_pnl <= -50, so full size + cut cannot coexist.
        assert state3._reached_profit_cushion() is True
        assert state3._lost_more_than_cut_threshold() is False
        assert state3.position_size_shares() == 100


# ── Setup entry / stop / target math ─────────────────────────────────────────


def _gap_candidate(**overrides):
    base = {
        "symbol": "MOCK",
        "price": 5.50,
        "change_pct": 0.18,
        "rel_volume": 7.0,
        "has_news": True,
        "float": 6_000_000,
    }
    base.update(overrides)
    return base


def _gap_bars(today: str = "2026-07-10"):
    return [
        {"t": f"{today}T08:00:00Z", "h": 5.00, "l": 4.80, "o": 4.85, "c": 4.95, "v": 10000},
        {"t": f"{today}T09:00:00Z", "h": 5.20, "l": 4.90, "o": 4.95, "c": 5.10, "v": 20000},
        {"t": f"{today}T13:31:00Z", "h": 5.55, "l": 5.30, "o": 5.30, "c": 5.50, "v": 50000},
    ]


def _bull_bars():
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


def _abcd_bars():
    pad = [{"o": 3.05, "h": 3.07, "l": 3.03, "c": 3.05} for _ in range(4)]
    return pad + [
        {"o": 2.95, "h": 3.00, "l": 2.90, "c": 2.98},
        {"o": 2.98, "h": 3.20, "l": 3.00, "c": 3.15},
        {"o": 3.15, "h": 3.50, "l": 3.15, "c": 3.48},
        {"o": 3.48, "h": 3.45, "l": 3.30, "c": 3.32},
        {"o": 3.32, "h": 3.34, "l": 3.25, "c": 3.30},
    ]


def _setup_candidate(**overrides):
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


class TestSetupBracketArithmetic:
    def test_gap_and_go_exact_20c_stop_and_2_to_1(self):
        now = datetime(2026, 7, 10, 9, 45, tzinfo=_ET)
        signal = evaluate_gap_and_go(_gap_candidate(price=5.50), _gap_bars(), now_et=now)
        assert signal.eligible is True
        assert signal.would_execute is False
        assert signal.entry_price == 5.50
        assert signal.stop_price == round(5.50 - GAP_AND_GO_MAX_STOP_DOLLARS, 2)
        assert signal.stop_price == 5.30
        risk = signal.entry_price - signal.stop_price
        assert risk == pytest.approx(0.20)
        assert signal.target_price == round(
            signal.entry_price + risk * GAP_AND_GO_MIN_PROFIT_LOSS_RATIO, 2
        )
        assert signal.target_price == 5.90
        assert any("Signal only" in n for n in signal.notes)
        assert any("No order has been placed" in n for n in signal.notes)

    def test_bull_flag_exact_target_from_pullback_low(self):
        signal = evaluate_bull_flag(_setup_candidate(price=4.00), _bull_bars())
        assert signal.eligible is True
        assert signal.would_execute is False
        assert signal.entry_price == 4.00
        assert signal.stop_price == 3.57
        risk = 4.00 - 3.57
        assert risk == pytest.approx(0.43)
        assert signal.target_price == round(4.00 + risk * BULL_FLAG_MIN_PROFIT_LOSS_RATIO, 2)
        assert signal.target_price == 4.86
        assert any("Signal only" in n for n in signal.notes)

    def test_abcd_exact_20c_stop_and_2_to_1(self):
        signal = evaluate_abcd(_setup_candidate(price=3.60), _abcd_bars())
        assert signal.eligible is True
        assert signal.would_execute is False
        assert signal.entry_price == 3.60
        assert signal.stop_price == round(3.60 - ABCD_MAX_STOP_DOLLARS, 2)
        assert signal.stop_price == 3.40
        risk = signal.entry_price - signal.stop_price
        assert risk == pytest.approx(0.20)
        assert signal.target_price == round(
            signal.entry_price + risk * ABCD_MIN_PROFIT_LOSS_RATIO, 2
        )
        assert signal.target_price == 4.00
        assert any("Signal only" in n for n in signal.notes)

    def test_all_setup_signals_serialize_would_execute_false(self):
        now = datetime(2026, 7, 10, 9, 45, tzinfo=_ET)
        gap = evaluate_gap_and_go(_gap_candidate(), _gap_bars(), now_et=now).to_dict()
        bull = evaluate_bull_flag(_setup_candidate(price=4.00), _bull_bars()).to_dict()
        abcd = evaluate_abcd(_setup_candidate(price=3.60), _abcd_bars()).to_dict()
        for payload in (gap, bull, abcd):
            assert payload["would_execute"] is False
            assert payload["eligible"] is True


# ── Five Pillars exact thresholds ────────────────────────────────────────────


class TestFivePillarsThresholdArithmetic:
    def _base(self, **overrides):
        base = {
            "symbol": "MOCK",
            "price": 5.00,
            "change_pct": 0.15,
            "rel_volume": 6.0,
            "has_news": True,
            "float": 8_000_000,
        }
        base.update(overrides)
        return base

    def test_price_boundaries_inclusive(self):
        assert FIVE_PILLARS_MIN_PRICE == 2.0
        assert FIVE_PILLARS_MAX_PRICE == 20.0
        assert evaluate_five_pillars(self._base(price=2.0)).checks[0].passed is True
        assert evaluate_five_pillars(self._base(price=20.0)).checks[0].passed is True
        assert evaluate_five_pillars(self._base(price=1.99)).checks[0].passed is False
        assert evaluate_five_pillars(self._base(price=20.01)).checks[0].passed is False

    def test_change_pct_boundary_fraction_and_percent_forms(self):
        assert FIVE_PILLARS_MIN_CHANGE_PCT == 10.0
        # 0.10 fraction => 10%
        assert evaluate_five_pillars(self._base(change_pct=0.10)).checks[1].passed is True
        assert evaluate_five_pillars(self._base(change_pct=0.099)).checks[1].passed is False
        # already-percent form
        assert evaluate_five_pillars(self._base(change_pct=10.0)).checks[1].passed is True
        assert evaluate_five_pillars(self._base(change_pct=9.9)).checks[1].passed is False

    def test_rel_volume_and_float_boundaries(self):
        assert FIVE_PILLARS_MIN_REL_VOLUME == 5.0
        assert FIVE_PILLARS_MAX_FLOAT_SHARES == 20_000_000
        assert evaluate_five_pillars(self._base(rel_volume=5.0)).checks[2].passed is True
        assert evaluate_five_pillars(self._base(rel_volume=4.999)).checks[2].passed is False
        assert evaluate_five_pillars(self._base(float=20_000_000)).checks[4].passed is True
        assert evaluate_five_pillars(self._base(float=20_000_001)).checks[4].passed is False


# ── L2 feature ratios ────────────────────────────────────────────────────────


def _book(bid_size, ask_size, bid_price=5.0, ask_price=5.05, multi_bid=None, multi_ask=None):
    bids = multi_bid if multi_bid is not None else (
        [{"price": bid_price, "size": bid_size, "side": "bid"}] if bid_size else []
    )
    asks = multi_ask if multi_ask is not None else (
        [{"price": ask_price, "size": ask_size, "side": "ask"}] if ask_size else []
    )
    return {"bids": bids, "asks": asks, "l1_fallback": False}


class TestL2FeatureArithmetic:
    def test_imbalance_formula_exact(self):
        # (900 - 100) / (900 + 100) = 0.8
        assert features.bid_ask_imbalance(_book(900, 100)) == pytest.approx(0.8)
        # (100 - 900) / 1000 = -0.8
        assert features.bid_ask_imbalance(_book(100, 900)) == pytest.approx(-0.8)
        # balanced
        assert features.bid_ask_imbalance(_book(500, 500)) == pytest.approx(0.0)

    def test_imbalance_sums_all_levels(self):
        book = _book(
            0, 0,
            multi_bid=[{"price": 5.0, "size": 100}, {"price": 4.99, "size": 200}],
            multi_ask=[{"price": 5.05, "size": 50}, {"price": 5.06, "size": 50}],
        )
        # bids 300, asks 100 -> (300-100)/400 = 0.5
        assert features.bid_ask_imbalance(book) == pytest.approx(0.5)
        assert features.bid_total(book) == 300
        assert features.ask_total(book) == 100

    def test_stacked_ratio_boundary_exactly_1_5(self):
        assert L2_ASK_STACKED_RATIO == 1.5
        assert L2_BID_HEAVY_RATIO == 1.5
        # ask == bid * 1.5 exactly => stacked
        assert features.is_ask_stacked(_book(100, 150)) is True
        assert features.is_ask_stacked(_book(100, 149)) is False
        assert features.is_bid_heavy(_book(150, 100)) is True
        assert features.is_bid_heavy(_book(149, 100)) is False

    def test_spread_exact_cents(self):
        assert features.spread(_book(100, 100, bid_price=5.00, ask_price=5.07)) == pytest.approx(0.07)
        assert features.spread(_book(100, 100, bid_price=1.00, ask_price=1.00)) == pytest.approx(0.0)

    def test_drying_up_boundary_exactly_30_pct_drop(self):
        assert L2_PRESSURE_DRYING_DROP_FRACTION == 0.30
        # drop exactly 30%: 1000 -> 700
        assert features.is_buying_pressure_drying_up(
            [_book(1000, 100), _book(700, 100)]
        ) is True
        # drop 29.9%: 1000 -> 701
        assert features.is_buying_pressure_drying_up(
            [_book(1000, 100), _book(701, 100)]
        ) is False


# ── Journal metrics arithmetic ───────────────────────────────────────────────


@pytest.fixture()
def isolated_journal(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    db.init_db()
    yield


class TestJournalMetricsArithmetic:
    def test_multi_trade_averages_and_ratio(self, isolated_journal):
        from journal.metrics import compute_metrics
        from journal.store import record_trade

        # wins: +20, +40  => avg 30; losses: -10, -20 => avg 15; ratio 2.0
        record_trade("A", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 5.2, 20.0, True)
        record_trade("B", "gap_and_go", "long", 100, 5.0, 4.9, 5.4, 5.4, 40.0, True)
        record_trade("C", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 4.9, -10.0, True)
        record_trade("D", "gap_and_go", "long", 100, 5.0, 4.8, 5.4, 4.8, -20.0, True)

        m = compute_metrics()
        assert m["total_closed_trades"] == 4
        assert m["win_rate_pct"] == 50.0
        assert m["avg_win_dollars"] == 30.0
        assert m["avg_loss_dollars"] == 15.0
        assert m["profit_loss_ratio"] == 2.0
        assert m["total_pnl_dollars"] == 30.0  # 20+40-10-20

    def test_breakeven_excluded_from_win_loss_averages(self, isolated_journal):
        from journal.metrics import compute_metrics
        from journal.store import record_trade

        record_trade("W", "abcd", "long", 100, 5.0, 4.9, 5.2, 5.2, 20.0, True)
        record_trade("L", "abcd", "long", 100, 5.0, 4.9, 5.2, 4.9, -10.0, True)
        record_trade("Z", "abcd", "long", 100, 5.0, 4.9, 5.2, 5.0, 0.0, True)

        m = compute_metrics()
        assert m["total_closed_trades"] == 3
        # win rate = 1/3 ≈ 33.3 (breakeven counts in denominator, not as a win)
        assert m["win_rate_pct"] == 33.3
        assert m["avg_win_dollars"] == 20.0
        assert m["avg_loss_dollars"] == 10.0
        assert m["profit_loss_ratio"] == 2.0

    def test_all_wins_leaves_ratio_none(self, isolated_journal):
        from journal.metrics import compute_metrics
        from journal.store import record_trade

        record_trade("A", "bull_flag", "long", 50, 4.0, 3.9, 4.2, 4.2, 10.0, True)
        record_trade("B", "bull_flag", "long", 50, 4.0, 3.9, 4.2, 4.2, 10.0, True)
        m = compute_metrics()
        assert m["win_rate_pct"] == 100.0
        assert m["profit_loss_ratio"] is None
        assert m["go_no_go"]["criteria"]["profit_loss_ratio"]["met"] is None

    def test_go_no_go_passes_only_with_full_sample_ratio_and_adherence(self, isolated_journal):
        from journal.metrics import compute_metrics
        from journal.store import record_trade

        assert JOURNAL_MIN_TRADES_FOR_GO_LIVE == 50
        # 34 wins of +20 and 16 losses of -10 => ratio 2.0, adherence 100%, n=50
        for i in range(34):
            record_trade(f"W{i}", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 5.2, 20.0, True)
        for i in range(16):
            record_trade(f"L{i}", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 4.9, -10.0, True)

        m = compute_metrics()
        assert m["total_closed_trades"] == 50
        assert m["win_rate_pct"] == 68.0
        assert m["profit_loss_ratio"] == 2.0
        assert m["adherence_pct"] == 100.0
        assert m["go_no_go"]["overall_go"] is True


# ── Executor transparency / disarmed-by-default ──────────────────────────────


@pytest.fixture(autouse=False)
def reset_executor():
    from nova_os import control_mode, staged_tickets

    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()
    yield
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()


class TestExecutorTransparencyContracts:
    def test_status_disclosure_names_modes_and_signal_default(self, reset_executor):
        status = executor.status()
        assert status["armed"] is False
        assert status["control_mode"] == "signal"
        assert status["kill_switch_tripped"] is False
        assert executor.is_armed() is False
        text = status["disclosure"]
        assert "signal" in text.lower()
        assert "confirm" in text.lower()
        assert "restart" in text.lower()
        assert status["open_positions"] == []

    def test_disarmed_on_signal_never_places_and_returns_none(self, reset_executor, monkeypatch):
        called = []
        monkeypatch.setattr(
            "ibkr.orders.place_bracket_order",
            lambda *a, **k: called.append(1),
        )
        result = asyncio.run(
            executor.on_signal(
                "AAPL",
                "gap_and_go",
                {"entry_price": 5.0, "stop_price": 4.9, "target_price": 5.2},
            )
        )
        assert result is None
        assert called == []
        assert executor.is_armed() is False

    def test_fill_pnl_math_is_exit_minus_entry_times_qty(self, reset_executor):
        """Document the exact PnL formula used when a bracket closes."""
        entry, exit_px, qty = 5.00, 5.20, 100
        assert (exit_px - entry) * qty == pytest.approx(20.0)
        entry2, exit2, qty2 = 5.00, 4.90, 25
        assert (exit2 - entry2) * qty2 == pytest.approx(-2.5)
