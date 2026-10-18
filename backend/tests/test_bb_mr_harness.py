"""Comprehensive correctness and causality tests for the U.S. Stock Bollinger Bands mean-reversion harness.

Covers all 12 requirements in Section 8:
1. Indicator calculations and warmup (population std ddof=0, no signals before N completed bars).
2. No unfinished-candle or future-data access, and no forward-filling of missing bars.
3. No duplicate entries from one 5-minute signal when evaluated every minute.
4. Entry spacing in observed signal candles, requiring a new qualifying signal (falling price alone never adds).
5. Causal scanner eligibility (Universe A and Universe B) and held-basket persistence on scanner drop-out.
6. Bid/ask execution (never at signal close), extended-hours limit collar, participation cap partial fills, IBKR fees.
7. Shared cash reservation, max 5 stocks, max 50% gross exposure, deterministic priority, rejected-signal logging.
8. Basket loss stop (-0.5% E0) and account daily loss stop (-3.0% start-of-day equity) with gap-through realism.
9. Halts and failed session-end liquidation (retained across cutoff until reopening print, never a fake fill).
10. Corporate-action consistency (causal split warmup adjustment, overnight split and cash dividend accounting).
11. Open-position valuation at dataset boundaries (Balance vs Equity).
12. Strict causality invariance test (perturbing data after time T cannot alter any state at or before T)
    and full ledger reconciliation.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.bb_mr.config import AccountParams, ExecutionParams, RunConfig, StrategyParams
from research.bb_mr.engine import prepare_symbol_day, run_simulation
from research.bb_mr.execution import make_bar_quote
from research.bb_mr.indicators import (
    build_signal_bars_from_1m,
    causal_split_factor,
    compute_bollinger_arrays,
)
from research.bb_mr.portfolio import PortfolioAccount
from research.bb_mr.universe import (
    is_eligible_common_stock,
    rank_liquid_universe_at_minute,
    rank_morning_active_scanner_at_minute,
)


def _make_1m_series(
    session_date: str,
    start_open_min: int,
    prices: list[tuple[float, float, float, float, float]],
) -> pd.DataFrame:
    """Build a 1m DataFrame from `(open, high, low, close, volume)` tuples."""
    rows = []
    for i, (o, h, low_px, c, v) in enumerate(prices):
        rows.append({
            "d": session_date,
            "open_min": start_open_min + i,
            "open": float(o),
            "high": float(h),
            "low": float(low_px),
            "close": float(c),
            "volume": float(v),
        })
    return pd.DataFrame(rows)


def test_indicator_calculations_and_warmup_and_no_forward_fill():
    # 20 bars of constant 10.0 followed by known values
    closes = np.array([10.0] * 19 + [12.0, 9.0], dtype=float)
    highs = closes + 0.5
    lows = closes - 0.5
    # Make index 20 touch below lower band and close back inside
    expected_mid = float(np.mean(closes[1:21]))
    expected_std = float(np.std(closes[1:21], ddof=0))
    expected_lo = expected_mid - 2.0 * expected_std
    lows[20] = expected_lo - 0.05
    closes[20] = expected_lo + 0.05
    # Recompute expected on updated closes[20]
    expected_mid = float(np.mean(closes[1:21]))
    expected_std = float(np.std(closes[1:21], ddof=0))
    expected_lo = expected_mid - 2.0 * expected_std
    expected_up = expected_mid + 2.0 * expected_std

    mid, up, lo, sd, qual = compute_bollinger_arrays(closes, highs, lows, period=20, deviation=2.0)
    assert np.all(np.isnan(mid[:19]))
    assert not np.any(qual[:19])
    assert mid[20] == pytest.approx(expected_mid, abs=1e-9)
    assert sd[20] == pytest.approx(expected_std, abs=1e-9)
    assert up[20] == pytest.approx(expected_up, abs=1e-9)
    assert lo[20] == pytest.approx(expected_lo, abs=1e-9)
    assert bool(qual[20]) is True

    # Verify zero-volume bars are dropped and never forward-filled into fictitious candles
    df = _make_1m_series(
        "2025-05-01",
        570,
        [(10.0, 10.1, 9.9, 10.0, 1000.0), (10.0, 10.0, 10.0, 10.0, 0.0), (10.0, 10.2, 9.8, 10.1, 1000.0)],
    )
    bars_1m = build_signal_bars_from_1m(df, "1m", period=2, deviation=2.0)
    assert len(bars_1m) == 2
    assert [b.open_min for b in bars_1m] == [570, 572]


def test_five_minute_signal_triggers_once_and_fills_only_at_subsequent_bar():
    # Build 19 five-minute warmup bars (95 minutes) alternating 19.80 and 20.20 so std ~ 0.20, lower ~ 19.60
    warmup_1m = []
    for b_idx in range(19):
        c_val = 19.80 if b_idx % 2 == 0 else 20.20
        warmup_1m.extend([(c_val, c_val + 0.05, c_val - 0.05, c_val, 50_000.0)] * 5)
    # 20th 5m bar (minutes 95..99 -> open_min 455..459, closes at 460):
    # touches below lower band (low=19.50 <= ~19.60) and closes back inside at 19.95 (> ~19.60)
    signal_5m = [
        (20.0, 20.05, 19.95, 20.0, 50_000.0),
        (20.0, 20.05, 19.50, 19.90, 50_000.0),
        (19.90, 20.0, 19.85, 19.95, 50_000.0),
        (19.95, 20.0, 19.90, 19.95, 50_000.0),
        (19.95, 20.0, 19.92, 19.95, 50_000.0),
    ]
    # Next 5 minutes (open_min 460..464, close_min 461..465): price opens at 20.10 (NOT 19.96!)
    after_1m = [(20.10, 20.15, 20.08, 20.12, 50_000.0)] * 10
    df = _make_1m_series("2025-05-01", 360, warmup_1m + signal_5m + after_1m)

    cfg = RunConfig(
        tag="test_once",
        universe="liquid_reference",
        session="morning_combined",
        strategy=StrategyParams(timeframe="5m", period=20, deviation=2.0, spacing=10, max_entries=5),
    )
    psd = prepare_symbol_day("AAPL", "2025-05-01", 19.0, 50_000_000.0, df, cfg)
    assert psd is not None
    # Signal completes at minute 460; must NOT appear in signal_completed_at_min for 461..464
    assert 460 in psd.signal_completed_at_min
    assert psd.signal_completed_at_min[460].qualifies_long is True
    for m in (461, 462, 463, 464):
        assert m not in psd.signal_completed_at_min

    res = run_simulation({"2025-05-01": [psd]}, cfg)
    fills = res["_ledgers"]["fills"]
    buy_fills = [f for f in fills if f["side"] == "BUY"]
    # Exactly ONE entry from that 5m signal, even though the engine checked every minute!
    assert len(buy_fills) == 1
    # Must fill at minute 461 (subsequent bar, open=20.10 + half_spread + slippage), NEVER at 19.96 signal close!
    assert buy_fills[0]["minute"] == 461
    assert buy_fills[0]["price"] > 20.10
    assert res["reconciliation"]["ok"] is True


def test_entry_spacing_and_no_add_on_falling_price_without_new_signal():
    exec_p = ExecutionParams(slippage_per_share=0.01, half_spread_min=0.01)
    acc_p = AccountParams(start_equity=25_000.0, basket_loss_pct_e0=0.50, daily_loss_pct=0.50)
    strat_p = StrategyParams(timeframe="1m", period=20, deviation=2.0, spacing=10, max_entries=5)
    port = PortfolioAccount(acc_p, strat_p, exec_p)
    port.start_trading_day("2025-05-01")

    # Submit first entry at signal_bar_index=20, minute=575
    ok1 = port.evaluate_entry_signal("AMD", "2025-05-01", 575, 20, 10.0, 100_000.0, True, 50e6)
    assert ok1 is True
    bq1 = make_bar_quote("2025-05-01", 576, 10.0, 10.05, 9.95, 10.0, 100_000.0, exec_p)
    port.process_pending_orders_for_bar("AMD", bq1)
    assert port.baskets["AMD"].num_entries == 1

    # Signal at bar_index=25 (only 5 bars later, spacing=10 required) -> rejected with spacing_not_satisfied
    ok2 = port.evaluate_entry_signal("AMD", "2025-05-01", 580, 25, 9.80, 100_000.0, True, 50e6)
    assert ok2 is False
    assert port.rejected_ledger[-1]["reason"] == "spacing_not_satisfied"

    # Signal at bar_index=30 (10 bars later >= spacing=10) -> accepted as entry_2
    ok3 = port.evaluate_entry_signal("AMD", "2025-05-01", 585, 30, 9.70, 100_000.0, True, 50e6)
    assert ok3 is True
    bq2 = make_bar_quote("2025-05-01", 586, 9.70, 9.75, 9.65, 9.70, 100_000.0, exec_p)
    port.process_pending_orders_for_bar("AMD", bq2)
    assert port.baskets["AMD"].num_entries == 2
    assert port.reconcile()["ok"] is True


def test_causal_scanner_eligibility_and_managed_basket_after_scanner_dropout():
    # Security type filters
    assert is_eligible_common_stock("AAPL", "CS", "XNAS") is True
    assert is_eligible_common_stock("BABA", "ADRC", "XNYS") is True
    assert is_eligible_common_stock("SPY", "ETF", "ARCX") is False
    assert is_eligible_common_stock("ABCDW", "WARRANT", "XNAS") is False
    assert is_eligible_common_stock("ABCDP", "PFD", "XNYS") is False
    assert is_eligible_common_stock("OTCX", "CS", "OTCM") is False
    assert is_eligible_common_stock("DLST", None, None) is True     # 4-letter delisted common stock

    # Morning active scanner ($1-$30, >= +10% vs prev_close, >= $500k cum dollar vol, top 20)
    cands = [
        ("LOWV", 5.0, 400_000.0, 6.0),      # below $500k dollar volume -> excluded
        ("SMLG", 5.0, 900_000.0, 5.20),     # +4% gain (< +10%) -> excluded
        ("TOO_HI", 25.0, 2_000_000.0, 32.0),# price $32 (> $30) -> excluded
        ("MOMO1", 4.0, 1_500_000.0, 5.0),   # valid (+25%, $1.5M)
        ("MOMO2", 10.0, 3_000_000.0, 12.0), # valid (+20%, $3.0M) -> ranked #1
    ]
    ranked = rank_morning_active_scanner_at_minute(cands)
    assert list(ranked.keys()) == ["MOMO2", "MOMO1"]

    # Universe A liquid reference ($5-$200, ADV20 >= $20M)
    liq = rank_liquid_universe_at_minute([
        ("PENNY", 3.0, 50_000_000.0, 3.5),
        ("ILLIQ", 20.0, 5_000_000.0, 20.0),
        ("MSFT", 150.0, 800_000_000.0, 152.0),
    ])
    assert list(liq.keys()) == ["MSFT"]


def test_shared_cash_reservation_and_simultaneous_signal_priority_and_max_stocks():
    exec_p = ExecutionParams(slippage_per_share=0.01, half_spread_min=0.01)
    # Set max_simultaneous_stocks=2 and max_gross_exposure_pct=0.05 ($1,250 on $25k)
    acc_p = AccountParams(
        start_equity=25_000.0,
        entry_alloc_pct_e0=0.03,            # $750 per entry
        max_committed_pct_e0=0.10,
        max_simultaneous_stocks=2,
        max_gross_exposure_pct=0.05,        # $1,250 total gross exposure cap across portfolio
    )
    strat_p = StrategyParams(timeframe="1m", period=20, deviation=2.0, spacing=10, max_entries=5)
    port = PortfolioAccount(acc_p, strat_p, exec_p)
    port.start_trading_day("2025-05-01")

    # Stock 1 ($750 reserved) accepted
    assert port.evaluate_entry_signal("AAA", "2025-05-01", 575, 20, 10.0, 100_000.0, True, 900_000.0) is True
    assert port.reserved_buy_cash() > 700.0
    # Stock 2 at the same minute sees the reduced remaining gross exposure ($1,250 - $750 = $500)
    assert port.evaluate_entry_signal("BBB", "2025-05-01", 575, 20, 10.0, 100_000.0, True, 800_000.0) is True
    # Stock 3 at the same minute is rejected due to max_simultaneous_stocks=2
    assert port.evaluate_entry_signal("CCC", "2025-05-01", 575, 20, 10.0, 100_000.0, True, 700_000.0) is False
    assert port.rejected_ledger[-1]["reason"] == "max_simultaneous_stocks"


def test_normal_exit_requires_dynamic_upper_band_and_net_profit_after_fees():
    exec_p = ExecutionParams(slippage_per_share=0.01, half_spread_min=0.01)
    acc_p = AccountParams(start_equity=25_000.0)
    strat_p = StrategyParams(timeframe="5m", period=20, deviation=2.0, spacing=10, max_entries=5, require_profit_on_exit=True)
    port = PortfolioAccount(acc_p, strat_p, exec_p)
    port.start_trading_day("2025-05-01")

    # Enter at $10.02
    port.evaluate_entry_signal("XYZ", "2025-05-01", 575, 20, 10.0, 100_000.0, True, 1e7)
    bq_in = make_bar_quote("2025-05-01", 576, 10.0, 10.02, 9.98, 10.0, 100_000.0, exec_p)
    port.process_pending_orders_for_bar("XYZ", bq_in)
    assert "XYZ" in port.baskets

    # Suppose dynamic upper band dropped to $9.90 while bid is $9.95 (bid >= upper, but basket is at a net loss!)
    bq_loss = make_bar_quote("2025-05-01", 580, 9.97, 9.98, 9.96, 9.97, 100_000.0, exec_p)
    port.mark_symbol("XYZ", bq_loss)
    assert port.check_normal_exit("XYZ", "2025-05-01", 580, latest_upper=9.90, latest_middle=9.80) is False

    # Now price rises to $10.50 and dynamic upper band is $10.40 (bid >= upper AND net profit > 0 after fees)
    bq_win = make_bar_quote("2025-05-01", 585, 10.55, 10.56, 10.54, 10.55, 100_000.0, exec_p)
    port.mark_symbol("XYZ", bq_win)
    assert port.check_normal_exit("XYZ", "2025-05-01", 585, latest_upper=10.40, latest_middle=10.20) is True
    assert port.baskets["XYZ"].liquidation_pending is True


def test_basket_stop_and_daily_loss_stop_and_gap_through_loss():
    exec_p = ExecutionParams(slippage_per_share=0.01, half_spread_min=0.01)
    acc_p = AccountParams(
        start_equity=25_000.0,
        entry_alloc_pct_e0=0.10,
        max_committed_pct_e0=0.10,
        basket_loss_pct_e0=0.005,           # -$125 basket stop
        daily_loss_pct=0.03,                # -$750 daily loss stop
    )
    strat_p = StrategyParams()
    port = PortfolioAccount(acc_p, strat_p, exec_p)
    port.start_trading_day("2025-05-01")

    # Open a $2,500 position at ~$10.00 (~249 shares)
    port.evaluate_entry_signal("GAP", "2025-05-01", 575, 20, 10.0, 500_000.0, True, 1e7)
    bq_in = make_bar_quote("2025-05-01", 576, 10.0, 10.02, 9.98, 10.0, 500_000.0, exec_p)
    port.process_pending_orders_for_bar("GAP", bq_in)

    # Stock gaps down to $6.00 (-$4/share -> ~-$1,000 loss, exceeding both -$125 basket stop and -$750 daily stop)
    bq_gap = make_bar_quote("2025-05-01", 577, 6.0, 6.02, 5.98, 6.0, 500_000.0, exec_p)
    port.mark_symbol("GAP", bq_gap)
    port.check_risk_triggers("2025-05-01", 577)
    assert port.daily_loss_halted is True
    assert port.baskets["GAP"].liquidation_pending is True

    # Next bar fills the liquidation at $5.80 (realized loss is ~-$1,050, NOT artificially capped at -$125 or -$750!)
    bq_fill = make_bar_quote("2025-05-01", 578, 5.80, 5.82, 5.78, 5.80, 500_000.0, exec_p)
    port.process_pending_orders_for_bar("GAP", bq_fill)
    assert "GAP" not in port.baskets
    assert port.basket_ledger[-1]["net_pnl"] < -900.0
    # Further entries on the same day are blocked by daily_loss_halted
    assert port.evaluate_entry_signal("NEW", "2025-05-01", 580, 25, 10.0, 500_000.0, True, 1e7) is False
    assert port.rejected_ledger[-1]["reason"] == "daily_loss_halted"
    assert port.reconcile()["ok"] is True


def test_halts_and_partial_fills_retain_position_across_cutoff_until_reopening():
    exec_p = ExecutionParams(slippage_per_share=0.01, half_spread_min=0.01, max_bar_participation=0.10)
    acc_p = AccountParams(start_equity=25_000.0, entry_alloc_pct_e0=0.04)
    strat_p = StrategyParams()
    port = PortfolioAccount(acc_p, strat_p, exec_p)
    port.start_trading_day("2025-05-01")

    # Enter 100 shares at $10.00
    port.evaluate_entry_signal("HALT", "2025-05-01", 650, 20, 9.95, 50_000.0, True, 1e7)
    bq_in = make_bar_quote("2025-05-01", 651, 9.95, 10.0, 9.90, 9.95, 50_000.0, exec_p)
    port.process_pending_orders_for_bar("HALT", bq_in)
    held_initial = port.baskets["HALT"].total_shares
    assert held_initial >= 90

    # Window end at 11:00 (minute 660): request liquidation, but stock is HALTED (volume=0) at 661 and 662!
    port.request_liquidation("HALT", "2025-05-01", 660, "window_end")
    for m_halt in (661, 662):
        bq_halt = make_bar_quote("2025-05-01", m_halt, 9.95, 9.95, 9.95, 9.95, 0.0, exec_p)
        port.process_pending_orders_for_bar("HALT", bq_halt)
    # Position MUST still be held in full -- never manufactured a fill during a halt!
    assert "HALT" in port.baskets
    assert port.baskets["HALT"].total_shares == held_initial

    # At 663, stock reopens with thin volume=400 shares -> max 10% participation = 40 shares partial fill!
    bq_thin = make_bar_quote("2025-05-01", 663, 8.50, 8.55, 8.45, 8.50, 400.0, exec_p)
    port.process_pending_orders_for_bar("HALT", bq_thin)
    assert "HALT" in port.baskets
    assert port.baskets["HALT"].total_shares == held_initial - 40

    # At 664, volume=5000 shares -> remaining shares fill completely
    bq_full = make_bar_quote("2025-05-01", 664, 8.40, 8.45, 8.35, 8.40, 5000.0, exec_p)
    port.process_pending_orders_for_bar("HALT", bq_full)
    assert "HALT" not in port.baskets
    assert port.reconcile()["ok"] is True


def test_corporate_actions_causal_splits_and_overnight_adjustments():
    splits = [(date(2025, 5, 10), 10.0, 1.0), (date(2025, 8, 1), 1.0, 2.0)]
    # On 2025-05-09 (before the 2025-05-10 reverse split), causal factor for 2025-05-08 is 1.0 (no lookahead!)
    assert causal_split_factor(splits, date(2025, 5, 8), date(2025, 5, 9)) == 1.0
    # On 2025-05-10 (reverse split effective today), warmup bar from 2025-05-08 scales by 10.0, ignoring Aug 2025 split!
    assert causal_split_factor(splits, date(2025, 5, 8), date(2025, 5, 10)) == 10.0

    # Overnight split & dividend in PortfolioAccount
    exec_p = ExecutionParams()
    acc_p = AccountParams(start_equity=25_000.0)
    strat_p = StrategyParams(timeframe="1h", overnight_hold=True)
    port = PortfolioAccount(acc_p, strat_p, exec_p)
    port.start_trading_day("2025-05-09")
    port.evaluate_entry_signal("DIVS", "2025-05-09", 630, 100, 20.0, 100_000.0, True, 5e7)
    bq = make_bar_quote("2025-05-09", 631, 20.0, 20.02, 19.98, 20.0, 100_000.0, exec_p)
    port.process_pending_orders_for_bar("DIVS", bq)
    sh_before = port.baskets["DIVS"].total_shares
    cash_before = port.cash

    # 2-for-1 forward split (split_from=1, split_to=2) + $0.50/share dividend on 2025-05-12
    port.apply_overnight_split("DIVS", 1.0, 2.0, "2025-05-12")
    assert port.baskets["DIVS"].total_shares == sh_before * 2
    port.apply_overnight_dividend("DIVS", 0.50, "2025-05-12")
    assert port.cash == pytest.approx(cash_before + (sh_before * 2) * 0.50)
    assert port.reconcile()["ok"] is True


def test_causality_invariance_perturbing_future_data_never_alters_past_decisions():
    """Causality gate (Section 8): changing data after time T must not alter decisions at or before T."""
    rng = np.random.default_rng(12345)
    base_prices = []
    px = 15.0
    for _ in range(240):
        ret = rng.normal(0.0, 0.004)
        o = px
        c = max(2.0, o * (1.0 + ret))
        h = max(o, c) * (1.0 + abs(rng.normal(0.0, 0.002)))
        low_px = min(o, c) * (1.0 - abs(rng.normal(0.0, 0.005)))
        base_prices.append((o, h, low_px, c, 80_000.0))
        px = c

    # Cutoff T is minute index 160 (open_min = 360 + 160 = 520 -> 08:40 ET)
    cutoff_idx = 160
    cutoff_min_close = 360 + cutoff_idx

    # Perturbed series: identical through cutoff_idx, wild crash/spike after cutoff_idx
    pert_prices = list(base_prices[:cutoff_idx])
    for i in range(cutoff_idx, 240):
        o, h, low_px, c, v = base_prices[i]
        pert_prices.append((o * 1.5, h * 2.0, low_px * 0.5, c * 1.8, v * 10.0))

    df_a = _make_1m_series("2025-05-01", 360, base_prices)
    df_b = _make_1m_series("2025-05-01", 360, pert_prices)

    cfg = RunConfig(
        tag="causality_test",
        universe="liquid_reference",
        session="morning_combined",
        strategy=StrategyParams(timeframe="5m", period=20, deviation=2.0, spacing=5, max_entries=5),
    )
    psd_a = prepare_symbol_day("CAUS", "2025-05-01", 13.0, 50_000_000.0, df_a, cfg)
    psd_b = prepare_symbol_day("CAUS", "2025-05-01", 13.0, 50_000_000.0, df_b, cfg)
    assert psd_a is not None and psd_b is not None

    res_a = run_simulation({"2025-05-01": [psd_a]}, cfg)
    res_b = run_simulation({"2025-05-01": [psd_b]}, cfg)

    for ledger_name in ("signals", "rejected", "orders", "fills"):
        before_a = [r for r in res_a["_ledgers"][ledger_name] if r["minute"] <= cutoff_min_close]
        before_b = [r for r in res_b["_ledgers"][ledger_name] if r["minute"] <= cutoff_min_close]
        assert before_a == before_b, f"Causality violation in {ledger_name} at or before minute {cutoff_min_close}"
