"""Event-driven chronological backtest engine and statistical evaluation for Bollinger Bands mean-reversion.

Steps minute-by-minute across trading sessions:
1. Marks open holdings and processes pending orders at each 1-minute bar.
2. Evaluates account daily loss threshold and per-basket loss budget at every replay event.
3. Evaluates normal upper-band (or middle-band) basket exits once per completed minute.
4. Evaluates new lower-band rejection entries once per completed signal candle (never re-triggering
   the same signal candle across subsequent minutes), ordered by deterministic contemporaneous priority.
5. Requests end-of-window liquidation at session cutoff; retains halted positions across cutoffs until
   the next executable print/quote becomes available.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from research.bb_mr.config import SESSION_WINDOWS, RunConfig, parse_hhmm
from research.bb_mr.execution import BarQuote, make_bar_quote
from research.bb_mr.indicators import SignalBar, build_signal_bars_from_1m, minute_of_day
from research.bb_mr.portfolio import PortfolioAccount
from research.bb_mr.universe import (
    LIQUID_ADV20_MIN,
    LIQUID_PRICE_MAX,
    LIQUID_PRICE_MIN,
    rank_liquid_universe_at_minute,
    rank_morning_active_scanner_at_minute,
)


@dataclass
class PreparedSymbolDay:
    ticker: str
    session_date: str
    prev_close: float
    adv20_usd: float
    bars_by_min: dict[int, BarQuote]                    # minute_close -> BarQuote
    cum_dvol_by_min: dict[int, float]                   # minute_close -> cumulative dollar vol since 04:00
    trail5_vol_by_min: dict[int, float]                 # minute_close -> trailing 5-bar mean volume
    signal_completed_at_min: dict[int, SignalBar]       # minute_close -> SignalBar that just completed at this minute
    latest_signal_by_min: dict[int, SignalBar]          # minute_close -> latest completed SignalBar at or before minute


def prepare_symbol_day(
    ticker: str,
    session_date: str,
    prev_close: float,
    adv20_usd: float,
    df_1m_with_warmup: pd.DataFrame,
    cfg: RunConfig,
) -> PreparedSymbolDay | None:
    """Build 1m BarQuotes, trailing volume, cumulative dollar volume, and completed SignalBars for `session_date`."""
    win = SESSION_WINDOWS[cfg.session]
    regular_only = win["warmup_session"] == "regular"
    sig_bars = build_signal_bars_from_1m(
        df_1m_with_warmup,
        cfg.strategy.timeframe,
        cfg.strategy.period,
        cfg.strategy.deviation,
        regular_only=regular_only,
    )
    if not sig_bars:
        return None

    today_1m = df_1m_with_warmup[df_1m_with_warmup["d"] == session_date]
    if today_1m.empty:
        return None

    bars_by_min: dict[int, BarQuote] = {}
    cum_dvol_by_min: dict[int, float] = {}
    trail5_vol_by_min: dict[int, float] = {}

    omin_arr = today_1m["open_min"].to_numpy(dtype=np.int64)
    o_arr = today_1m["open"].to_numpy(dtype=np.float64)
    h_arr = today_1m["high"].to_numpy(dtype=np.float64)
    l_arr = today_1m["low"].to_numpy(dtype=np.float64)
    c_arr = today_1m["close"].to_numpy(dtype=np.float64)
    v_arr = today_1m["volume"].to_numpy(dtype=np.float64)

    cum_dvol = 0.0
    recent_vols: list[float] = []
    for i in range(len(omin_arr)):
        m_close = int(omin_arr[i]) + 1
        vol = float(v_arr[i])
        bq = make_bar_quote(
            session_date, m_close, float(o_arr[i]), float(h_arr[i]), float(l_arr[i]), float(c_arr[i]), vol, cfg.execution
        )
        bars_by_min[m_close] = bq
        if vol > 0:
            cum_dvol += float(c_arr[i]) * vol
            recent_vols.append(vol)
            if len(recent_vols) > 5:
                recent_vols.pop(0)
        cum_dvol_by_min[m_close] = cum_dvol
        trail5_vol_by_min[m_close] = float(np.mean(recent_vols)) if recent_vols else 0.0

    signal_completed_at_min: dict[int, SignalBar] = {}
    today_sigs: list[SignalBar] = []
    prior_latest: SignalBar | None = None
    for sb in sig_bars:
        if sb.session_date < session_date:
            if sb.middle is not None:
                prior_latest = sb
        elif sb.session_date == session_date:
            if sb.middle is not None:
                signal_completed_at_min[sb.close_min] = sb
                today_sigs.append(sb)

    latest_signal_by_min: dict[int, SignalBar] = {}
    cur_sig = prior_latest
    for m_close in range(241, 961):
        if m_close in signal_completed_at_min:
            cur_sig = signal_completed_at_min[m_close]
        if cur_sig is not None:
            latest_signal_by_min[m_close] = cur_sig

    return PreparedSymbolDay(
        ticker=ticker,
        session_date=session_date,
        prev_close=prev_close,
        adv20_usd=adv20_usd,
        bars_by_min=bars_by_min,
        cum_dvol_by_min=cum_dvol_by_min,
        trail5_vol_by_min=trail5_vol_by_min,
        signal_completed_at_min=signal_completed_at_min,
        latest_signal_by_min=latest_signal_by_min,
    )


def run_simulation(
    days_data: dict[str, list[PreparedSymbolDay]],
    cfg: RunConfig,
    *,
    overnight_splits: dict[tuple[str, str], tuple[float, float]] | None = None,
    overnight_dividends: dict[tuple[str, str], float] | None = None,
    force_close_at_end: bool = True,
) -> dict[str, Any]:
    """Run the event-driven simulation across ordered trading days `days_data`."""
    account = PortfolioAccount(cfg.account, cfg.strategy, cfg.execution)
    win = SESSION_WINDOWS[cfg.session]
    start_min = minute_of_day(parse_hhmm(win["start"])) + 1
    end_min = minute_of_day(parse_hhmm(win["end"]))
    cutoff_min = minute_of_day(parse_hhmm(win["entry_cutoff"]))

    sorted_days = sorted(days_data.keys())
    for d_idx, session_date in enumerate(sorted_days):
        # 1) Apply overnight corporate actions (splits and cash dividends) before session start
        if cfg.strategy.overnight_hold and account.baskets:
            if overnight_splits:
                for tkr in list(account.baskets.keys()):
                    sp = overnight_splits.get((tkr, session_date))
                    if sp is not None:
                        account.apply_overnight_split(tkr, sp[0], sp[1], session_date)
            if overnight_dividends:
                for tkr in list(account.baskets.keys()):
                    div = overnight_dividends.get((tkr, session_date))
                    if div is not None:
                        account.apply_overnight_dividend(tkr, div, session_date)

        account.start_trading_day(session_date)
        sym_list = days_data[session_date]
        by_ticker = {sd.ticker: sd for sd in sym_list}

        # Track latest known price and cumulative dollar volume as of minute m
        last_close_by_tkr: dict[str, float] = {}
        last_ask_by_tkr: dict[str, float] = {}
        last_cum_dvol_by_tkr: dict[str, float] = {}

        # Step minute by minute across the session (from 04:01 through 16:00 ET so pending liquidations after cutoff can fill)
        first_loop_min = 241 if start_min < 571 else 571
        for m in range(first_loop_min, 961):
            # a) Mark open positions & fill pending orders on observed bars at minute m
            for sd in sym_list:
                bq = sd.bars_by_min.get(m)
                if bq is not None and not bq.halted and bq.volume > 0:
                    last_close_by_tkr[sd.ticker] = bq.close
                    last_ask_by_tkr[sd.ticker] = bq.close_ask
                    last_cum_dvol_by_tkr[sd.ticker] = sd.cum_dvol_by_min.get(m, 0.0)
                    account.mark_symbol(sd.ticker, bq)
                    account.process_pending_orders_for_bar(sd.ticker, bq)

            # b) Risk monitoring at every replay minute inside or after window start
            if m >= start_min:
                account.check_risk_triggers(session_date, m)

            # c) Session-end liquidation request at `end_min` (for intraday strategies)
            if not cfg.strategy.overnight_hold and m == end_min:
                for tkr in list(account.baskets.keys()):
                    account.request_liquidation(tkr, session_date, m, "window_end")
                # Cancel any unfilled pending BUY entry orders at window end
                account.pending_orders = [o for o in account.pending_orders if o.side != "BUY"]

            if m < start_min or m > end_min:
                continue

            # d) Normal basket exit evaluation once per completed minute
            for tkr in list(account.baskets.keys()):
                sd = by_ticker.get(tkr)
                if sd is None:
                    continue
                latest_sig = sd.latest_signal_by_min.get(m)
                if latest_sig is not None:
                    account.check_normal_exit(tkr, session_date, m, latest_sig.upper, latest_sig.middle)

            # e) Entry evaluation before entry_cutoff
            if m <= cutoff_min and not account.daily_loss_halted:
                # Determine causal active universe at minute m
                if cfg.universe == "liquid_reference":
                    cands_raw = [
                        (sd.ticker, sd.prev_close, sd.adv20_usd, last_close_by_tkr.get(sd.ticker, 0.0))
                        for sd in sym_list
                        if last_close_by_tkr.get(sd.ticker, 0.0) > 0
                    ]
                    active_univ = rank_liquid_universe_at_minute(cands_raw)
                else:
                    cands_raw = [
                        (sd.ticker, sd.prev_close, last_cum_dvol_by_tkr.get(sd.ticker, 0.0), last_close_by_tkr.get(sd.ticker, 0.0))
                        for sd in sym_list
                        if last_close_by_tkr.get(sd.ticker, 0.0) > 0
                    ]
                    active_univ = rank_morning_active_scanner_at_minute(cands_raw)

                # Collect all symbols whose signal candle JUST completed at minute m and qualified
                signaling: list[tuple[float, str, SignalBar, PreparedSymbolDay]] = []
                for sd in sym_list:
                    sb = sd.signal_completed_at_min.get(m)
                    if sb is None or not sb.qualifies_long:
                        continue
                    # A stock already held in a basket remains managed even if it dropped out of top-20,
                    # or must be in active_univ for a new basket
                    in_univ = sd.ticker in active_univ
                    already_held = sd.ticker in account.baskets and account.baskets[sd.ticker].total_shares > 0
                    if not in_univ and not already_held:
                        # Only log as rejected if it at least met basic price/move activity
                        continue
                    prio = (
                        active_univ[sd.ticker].priority_metric
                        if in_univ
                        else (sd.adv20_usd if cfg.universe == "liquid_reference" else last_cum_dvol_by_tkr.get(sd.ticker, 0.0))
                    )
                    signaling.append((prio, sd.ticker, sb, sd))

                # Sort deterministically by (-priority_metric, ticker ASC)
                signaling.sort(key=lambda item: (-item[0], item[1]))
                for prio, tkr, sb, sd in signaling:
                    ref_ask = last_ask_by_tkr.get(tkr, sb.close)
                    trail_vol = sd.trail5_vol_by_min.get(m, sb.volume)
                    in_univ = (
                        tkr in active_univ
                        or (tkr in account.baskets and account.baskets[tkr].total_shares > 0 and (
                            LIQUID_PRICE_MIN <= sb.close <= LIQUID_PRICE_MAX and sd.adv20_usd >= LIQUID_ADV20_MIN
                            if cfg.universe == "liquid_reference"
                            else True
                        ))
                    )
                    account.evaluate_entry_signal(
                        ticker=tkr,
                        session_date=session_date,
                        minute_close=m,
                        signal_bar_index=sb.bar_index,
                        ref_ask_price=ref_ask,
                        trailing_avg_vol=trail_vol,
                        universe_eligible=in_univ,
                        priority_metric=prio,
                    )

        # At dataset / fold boundary, optionally close any remaining open positions at last known bid
        if force_close_at_end and d_idx == len(sorted_days) - 1 and account.baskets:
            for tkr, b in list(account.baskets.items()):
                if b.total_shares > 0:
                    bid = b.last_mark_bid if b.last_mark_bid > 0 else b.last_mark_mid
                    fake_bar = BarQuote(
                        session_date=session_date, minute_close=960, open=bid, high=bid, low=bid, close=bid,
                        volume=1e9, bid=bid, ask=bid, close_bid=bid, close_ask=bid, half_spread=0.0, halted=False,
                    )
                    if not b.liquidation_pending:
                        account.request_liquidation(tkr, session_date, 959, "dataset_boundary_close")
                    account.process_pending_orders_for_bar(tkr, fake_bar)

        eq_end = account.marked_equity(use_bid=True)
        bal_end = account.account_balance()
        account.daily_ledger.append({
            "date": session_date,
            "balance": round(bal_end, 2),
            "equity": round(eq_end, 2),
            "cash": round(account.cash, 2),
            "gross_exposure": round(account.gross_position_value(use_bid=True), 2),
            "floating_pnl": round(eq_end - bal_end, 2),
            "day_pnl": round(eq_end - account.day_start_equity, 2),
            "open_baskets": len(account.baskets),
            "daily_loss_halted": account.daily_loss_halted,
        })

    return summarize_run(cfg, account)


def block_bootstrap_sharpe_ci(daily_returns: np.ndarray, block_size: int = 10, n_boot: int = 500, seed: int = 42) -> tuple[float, float]:
    """Moving-block bootstrap 95% confidence interval for annualized Sharpe ratio preserving time correlation."""
    n = len(daily_returns)
    if n < block_size * 2 or float(np.std(daily_returns)) == 0.0:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block_size))
    max_start = n - block_size
    sharpes = np.empty(n_boot, dtype=np.float64)
    for b in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block_size) for s in starts])[:n]
        sample = daily_returns[idx]
        sd = float(np.std(sample, ddof=1))
        sharpes[b] = float(np.mean(sample) / sd * math.sqrt(252.0)) if sd > 0 else 0.0
    return (round(float(np.percentile(sharpes, 2.5)), 3), round(float(np.percentile(sharpes, 97.5)), 3))


def summarize_run(cfg: RunConfig, account: PortfolioAccount) -> dict[str, Any]:
    """Compute comprehensive portfolio, basket, entry, risk, regime, and concentration metrics."""
    daily_df = pd.DataFrame(account.daily_ledger)
    basket_df = pd.DataFrame(account.basket_ledger)
    fill_df = pd.DataFrame(account.fill_ledger)
    reject_df = pd.DataFrame(account.rejected_ledger)

    start_eq = cfg.account.start_equity
    if daily_df.empty:
        return {
            "tag": cfg.tag, "config": cfg.to_dict(), "days": 0, "baskets": 0, "entries": 0,
            "net_pnl_usd": 0.0, "total_return_pct": 0.0, "reconciliation": account.reconcile(),
        }

    end_eq = float(daily_df["equity"].iloc[-1])
    end_bal = float(daily_df["balance"].iloc[-1])
    net_pnl = end_eq - start_eq
    tot_ret_pct = 100.0 * (end_eq / start_eq - 1.0)

    eq_series = daily_df["equity"].to_numpy(dtype=np.float64)
    prev_eq = np.r_[start_eq, eq_series[:-1]]
    daily_ret = (eq_series - prev_eq) / np.maximum(prev_eq, 1.0)
    daily_df["ret"] = daily_ret

    peak = np.maximum.accumulate(np.r_[start_eq, eq_series])[1:]
    dd = (eq_series - peak) / peak
    max_dd_pct = 100.0 * float(np.min(dd)) if len(dd) else 0.0
    underwater_days = int(np.sum(eq_series < peak - 1e-6))
    underwater_pct = 100.0 * underwater_days / len(eq_series)

    ret_std = float(np.std(daily_ret, ddof=1)) if len(daily_ret) > 1 else 0.0
    sharpe = float(np.mean(daily_ret) / ret_std * math.sqrt(252.0)) if ret_std > 0 else 0.0
    ci_lo, ci_hi = block_bootstrap_sharpe_ci(daily_ret)

    n_baskets = len(basket_df)
    n_entries = int(basket_df["entries"].sum()) if n_baskets > 0 else 0
    total_turnover = float(basket_df["committed_cost"].sum() + basket_df["exit_proceeds"].sum()) if n_baskets > 0 else 0.0
    if n_baskets > 0:
        hold_mins = np.maximum(1.0, (basket_df["closed_minute"] - basket_df["opened_minute"]).to_numpy(dtype=np.float64))
        intraday_dollar_mins = float(np.sum(basket_df["committed_cost"].to_numpy(dtype=np.float64) * hold_mins))
        avg_intraday_exposure = round(intraday_dollar_mins / max(1.0, len(daily_df) * 300.0), 2)
        max_day_committed = round(float(basket_df.groupby("opened_date")["committed_cost"].sum().max()), 2)
    else:
        avg_intraday_exposure = 0.0
        max_day_committed = 0.0

    if n_baskets > 0:
        wins = basket_df[basket_df["net_pnl"] > 0]
        losses = basket_df[basket_df["net_pnl"] <= 0]
        gross_win = float(wins["net_pnl"].sum()) if len(wins) else 0.0
        gross_loss = float(-losses["net_pnl"].sum()) if len(losses) else 0.0
        pf = round(gross_win / gross_loss, 3) if gross_loss > 0 else None
        win_rate = round(100.0 * len(wins) / n_baskets, 2)
        avg_win = round(float(wins["net_pnl"].mean()), 2) if len(wins) else 0.0
        avg_loss = round(float(losses["net_pnl"].mean()), 2) if len(losses) else 0.0
        largest_loss = round(float(basket_df["net_pnl"].min()), 2)
        largest_win = round(float(basket_df["net_pnl"].max()), 2)
        expectancy_usd = round(float(basket_df["net_pnl"].mean()), 2)
        total_fees = round(float(basket_df["total_fees"].sum()), 2)

        # Breakdown by number of basket additions (entries = 1..5)
        by_entries = {}
        for k, grp in basket_df.groupby("entries"):
            gw = float(grp[grp["net_pnl"] > 0]["net_pnl"].sum())
            gl = float(-grp[grp["net_pnl"] <= 0]["net_pnl"].sum())
            by_entries[int(k)] = {
                "baskets": int(len(grp)),
                "win_rate_pct": round(100.0 * float((grp["net_pnl"] > 0).mean()), 1),
                "net_pnl_usd": round(float(grp["net_pnl"].sum()), 2),
                "expectancy_usd": round(float(grp["net_pnl"].mean()), 2),
                "pf": round(gw / gl, 3) if gl > 0 else None,
            }

        # Breakdown by year
        basket_df["year"] = basket_df["opened_date"].str[:4]
        by_year = {}
        for y, grp in basket_df.groupby("year"):
            gw = float(grp[grp["net_pnl"] > 0]["net_pnl"].sum())
            gl = float(-grp[grp["net_pnl"] <= 0]["net_pnl"].sum())
            by_year[str(y)] = {
                "baskets": int(len(grp)),
                "entries": int(grp["entries"].sum()),
                "win_rate_pct": round(100.0 * float((grp["net_pnl"] > 0).mean()), 1),
                "net_pnl_usd": round(float(grp["net_pnl"].sum()), 2),
                "pf": round(gw / gl, 3) if gl > 0 else None,
            }

        # Breakdown by exit reason
        by_exit_reason = {
            str(r): {"baskets": int(len(g)), "net_pnl_usd": round(float(g["net_pnl"].sum()), 2)}
            for r, g in basket_df.groupby("exit_reason")
        }

        # Concentration diagnostics: remove top 5 winning days and top 5 winning stocks
        top5_days_pnl = float(daily_df.nlargest(5, "day_pnl")["day_pnl"].sum())
        pnl_by_stock = basket_df.groupby("ticker")["net_pnl"].sum()
        top5_stocks_pnl = float(pnl_by_stock.nlargest(5).sum())
        ex_top5_days_pnl = round(net_pnl - top5_days_pnl, 2)
        ex_top5_stocks_pnl = round(net_pnl - top5_stocks_pnl, 2)
    else:
        pf, win_rate, avg_win, avg_loss, largest_loss, largest_win, expectancy_usd, total_fees = (
            None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        )
        by_entries, by_year, by_exit_reason = {}, {}, {}
        top5_days_pnl, top5_stocks_pnl, ex_top5_days_pnl, ex_top5_stocks_pnl = 0.0, 0.0, 0.0, 0.0

    rejected_by_reason = (
        {str(r): int(len(g)) for r, g in reject_df.groupby("reason")} if not reject_df.empty else {}
    )
    partial_fills = int((fill_df["status"] == "partial").sum()) if not fill_df.empty else 0

    return {
        "tag": cfg.tag,
        "universe": cfg.universe,
        "session": cfg.session,
        "split": cfg.split,
        "config": cfg.to_dict(),
        "days": int(len(daily_df)),
        "baskets": int(n_baskets),
        "entries": int(n_entries),
        "signals_total": int(len(account.signal_ledger)),
        "signals_rejected": int(len(account.rejected_ledger)),
        "rejected_by_reason": rejected_by_reason,
        "partial_fills": partial_fills,
        "start_equity": start_eq,
        "end_balance": round(end_bal, 2),
        "end_equity": round(end_eq, 2),
        "net_pnl_usd": round(net_pnl, 2),
        "total_return_pct": round(tot_ret_pct, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "underwater_days": underwater_days,
        "underwater_pct": round(underwater_pct, 1),
        "sharpe": round(sharpe, 3),
        "sharpe_95ci": [ci_lo, ci_hi],
        "daily_ret_mean_pct": round(100.0 * float(np.mean(daily_ret)), 4),
        "daily_ret_std_pct": round(100.0 * ret_std, 4),
        "daily_ret_skew": round(float(pd.Series(daily_ret).skew()), 3) if len(daily_ret) > 2 else 0.0,
        "daily_ret_p05_pct": round(100.0 * float(np.percentile(daily_ret, 5)), 3),
        "daily_ret_p95_pct": round(100.0 * float(np.percentile(daily_ret, 95)), 3),
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "expectancy_usd": expectancy_usd,
        "avg_win_usd": avg_win,
        "avg_loss_usd": avg_loss,
        "largest_win_usd": largest_win,
        "largest_loss_usd": largest_loss,
        "total_fees_usd": total_fees,
        "total_turnover_usd": round(total_turnover, 2),
        "avg_gross_exposure_usd": round(max(float(daily_df["gross_exposure"].mean()), avg_intraday_exposure), 2),
        "max_gross_exposure_usd": round(max(float(daily_df["gross_exposure"].max()), max_day_committed), 2),
        "top5_days_pnl_usd": round(top5_days_pnl, 2),
        "ex_top5_days_pnl_usd": ex_top5_days_pnl,
        "top5_stocks_pnl_usd": round(top5_stocks_pnl, 2),
        "ex_top5_stocks_pnl_usd": ex_top5_stocks_pnl,
        "by_entries": by_entries,
        "by_year": by_year,
        "by_exit_reason": by_exit_reason,
        "reconciliation": account.reconcile(),
        "_ledgers": {
            "daily": account.daily_ledger,
            "baskets": account.basket_ledger,
            "fills": account.fill_ledger,
            "orders": account.order_ledger,
            "signals": account.signal_ledger,
            "rejected": account.rejected_ledger,
        },
    }
