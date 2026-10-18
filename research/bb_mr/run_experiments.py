"""End-to-end experiment runner for U.S. Stock Bollinger Bands Mean-Reversion.

maintainer: one-concern orchestrating the pre-registered baselines, 96-grid, walk-forward folds, stress tests, and plots in one reproducible pipeline

Executes and saves:
1. Fixed baselines (A, B_single, B_exp_matched, C_200_2p5, D_H1_intraday, D_H1_swing) on both universes
   across Full (2021-10-19..2026-09-21), Development, Validation, and Evaluation splits.
2. Separate session window experiments (06:00-11:00, 06:00-09:30, 09:30-10:30, 09:30-16:00 ET).
3. Bounded 96-configuration intraday grid per universe (192 configs) on Development & Validation,
   applying the frozen selection rule and testing the selected candidate on the untouched Evaluation set.
4. Separately labeled ablations (middle band exit, unconditional upper band exit, no additions,
   fixed-dollar sizing, 1.5x position multiplier diagnostic).
5. Rolling 6-fold walk-forward validation with strict fold-boundary liquidation.
6. Stress tests (2x costs, 3x slippage + 2x spread, 2m execution delay, 3% capacity cap, different start dates,
   top-5 winning days/stocks removal) and cross-sectional regime/price/duration/addition/float breakdowns.
7. Tier-2 tick-level SIP NBBO quote validation (`quotes_v1`) and 5 representative trade traces.
8. Reproducible ledgers (`.csv`), summary JSON (`all_experiments.json`), and diagnostic plots.
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.bb_mr.config import (
    BB_DB_PATH,
    PLOTS_DIR,
    RESULTS_DIR,
    SESSION_WINDOWS,
    RunConfig,
    StrategyParams,
    baseline_configs,
    grid_96_configs,
)
from research.bb_mr.fast_loader import SliceCache
from research.bb_mr.nbbo_validator import run_nbbo_validation_sample
from research.bb_mr.report_plots import generate_all_plots


def _run_slice_chunk_worker(args: tuple[str, str, int, float, list[RunConfig]]) -> list[dict[str, Any]]:
    universe, tf, period, dev, cfgs = args
    cache = SliceCache(BB_DB_PATH)
    rows: list[dict[str, Any]] = []
    for cfg in cfgs:
        res_dev = cache.run_config(cfg, keep_ledgers=False)
        s = cfg.strategy
        rows.append({
            "tag": cfg.tag,
            "universe": universe,
            "timeframe": s.timeframe,
            "period": s.period,
            "deviation": s.deviation,
            "spacing": s.spacing,
            "max_entries": s.max_entries,
            "multiplier": s.multiplier,
            "dev_baskets": res_dev["baskets"],
            "dev_entries": res_dev["entries"],
            "dev_net_pnl_usd": res_dev["net_pnl_usd"],
            "dev_return_pct": res_dev["total_return_pct"],
            "dev_pf": res_dev["profit_factor"],
            "dev_win_rate_pct": res_dev["win_rate_pct"],
            "dev_max_dd_pct": res_dev["max_drawdown_pct"],
            "dev_sharpe": res_dev["sharpe"],
            "dev_expectancy_usd": res_dev["expectancy_usd"],
            "baskets": res_dev["baskets"],
            "net_pnl_usd": res_dev["net_pnl_usd"],
        })
    cache.close()
    return rows


def _finalize_grid_for_universe(universe: str, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache = SliceCache(BB_DB_PATH)
    dev_configs = grid_96_configs(universe, session="morning_combined", split="development")
    rows.sort(key=lambda r: r["tag"])

    df_dev = pd.DataFrame(rows)
    viable_dev = df_dev[df_dev["dev_baskets"] >= 40].sort_values("dev_sharpe", ascending=False)
    shortlist_tags = set(viable_dev.head(12)["tag"].tolist()) | set(df_dev[df_dev["dev_net_pnl_usd"] > 0]["tag"].tolist())
    if not shortlist_tags:
        shortlist_tags = set(df_dev.sort_values("dev_sharpe", ascending=False).head(8)["tag"].tolist())

    cfg_by_tag = {c.tag: c for c in dev_configs}
    val_results: dict[str, dict[str, Any]] = {}
    for tag in sorted(shortlist_tags):
        c_val = replace(cfg_by_tag[tag], split="validation", tag=f"{tag}_val")
        val_results[tag] = cache.run_config(c_val, keep_ledgers=False)

    for r in rows:
        vr = val_results.get(r["tag"])
        if vr is not None:
            r["val_baskets"] = vr["baskets"]
            r["val_net_pnl_usd"] = vr["net_pnl_usd"]
            r["val_pf"] = vr["profit_factor"]
            r["val_sharpe"] = vr["sharpe"]
            r["val_max_dd_pct"] = vr["max_drawdown_pct"]
        else:
            r["val_baskets"] = None
            r["val_net_pnl_usd"] = None
            r["val_pf"] = None
            r["val_sharpe"] = None
            r["val_max_dd_pct"] = None

    passed_gate = [
        r for r in rows
        if r["dev_baskets"] >= 100
        and (r["val_baskets"] or 0) >= 40
        and (r["dev_pf"] or 0.0) > 1.05
        and (r["val_pf"] or 0.0) > 1.05
    ]
    if passed_gate:
        passed_gate.sort(key=lambda x: float(x["val_sharpe"] or -999.0), reverse=True)
        chosen_row = passed_gate[0]
        selection_status = "passed_pre_registered_gate"
    else:
        scored = [r for r in rows if r["val_sharpe"] is not None]
        scored.sort(key=lambda x: float(x["val_sharpe"] or -999.0), reverse=True)
        chosen_row = scored[0]
        selection_status = "failed_gate_diagnostic_best_val_sharpe"

    chosen_cfg = cfg_by_tag[chosen_row["tag"]]
    eval_res = cache.run_config(replace(chosen_cfg, split="evaluation", tag=f"{chosen_cfg.tag}_eval"), keep_ledgers=False)
    full_res = cache.run_config(replace(chosen_cfg, split="full", tag=f"{chosen_cfg.tag}_full"), keep_ledgers=False)

    cross_sessions = {}
    for sess in ("morning_combined", "premarket_only", "opening_hour", "regular_session"):
        c_sess = replace(chosen_cfg, session=sess, split="evaluation", tag=f"{chosen_cfg.tag}_eval_{sess}")
        cross_sessions[sess] = cache.run_config(c_sess, keep_ledgers=False)

    cache.close()
    selection_summary = {
        "universe": universe,
        "selection_status": selection_status,
        "configs_tested": len(rows),
        "configs_positive_dev": int(sum(1 for r in rows if r["dev_net_pnl_usd"] > 0)),
        "configs_positive_val": int(sum(1 for r in rows if (r["val_net_pnl_usd"] or -1.0) > 0)),
        "configs_passed_gate": len(passed_gate),
        "chosen_config": chosen_row,
        "evaluation_split_result": eval_res,
        "full_5y_result": full_res,
        "evaluation_across_sessions": cross_sessions,
    }
    return rows, selection_summary


def _save_baseline_ledgers(tag: str, ledgers: dict[str, list[dict[str, Any]]]) -> None:
    ledger_dir = RESULTS_DIR / "ledgers"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    for name in ("daily", "baskets", "fills", "orders", "signals", "rejected"):
        rows = ledgers.get(name, [])
        pd.DataFrame(rows).to_csv(ledger_dir / f"{tag}_{name}.csv", index=False)


def _extract_representative_traces(
    ua_ledgers: dict[str, list[dict[str, Any]]],
    ub_ledgers: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Extract the 5 required manual inspection traces from actual simulated ledgers."""
    all_baskets = [
        {**b, "universe": "liquid_reference"} for b in ua_ledgers.get("baskets", [])
    ] + [
        {**b, "universe": "morning_active"} for b in ub_ledgers.get("baskets", [])
    ]
    all_fills = [
        {**f, "universe": "liquid_reference"} for f in ua_ledgers.get("fills", [])
    ] + [
        {**f, "universe": "morning_active"} for f in ub_ledgers.get("fills", [])
    ]

    def _trace_for(basket: dict[str, Any] | None) -> dict[str, Any] | None:
        if basket is None:
            return None
        bid = basket["basket_id"]
        u = basket["universe"]
        fills = [f for f in all_fills if f["basket_id"] == bid and f["universe"] == u]
        return {"basket": basket, "fills": fills}

    # 1. Winning basket exited at upper band
    winners = [b for b in all_baskets if b["net_pnl"] > 0 and "upper_band" in str(b["exit_reason"])]
    winners.sort(key=lambda b: b["net_pnl"], reverse=True)
    win_trace = _trace_for(winners[len(winners) // 4] if winners else None)

    # 2. Falling stock with multiple additions (entries >= 3)
    multi = [b for b in all_baskets if int(b["entries"]) >= 3]
    multi.sort(key=lambda b: (int(b["entries"]), -abs(b["net_pnl"])), reverse=True)
    multi_trace = _trace_for(multi[0] if multi else None)

    # 3. Stopped basket (basket_stop or daily_loss_stop)
    stopped = [b for b in all_baskets if b["exit_reason"] in ("basket_stop", "daily_loss_stop")]
    stopped.sort(key=lambda b: b["net_pnl"])
    stop_trace = _trace_for(stopped[len(stopped) // 2] if stopped else None)

    # 4. Premarket trade (opened before 09:30 -> opened_minute <= 570)
    pm_baskets = [b for b in all_baskets if int(b["opened_minute"]) <= 570]
    pm_trace = _trace_for(pm_baskets[0] if pm_baskets else None)

    # 5. Partial fill / liquidity-constrained or window-end delayed basket
    part_fill_bids = {(f["universe"], f["basket_id"]) for f in all_fills if f.get("status") == "partial"}
    part_baskets = [b for b in all_baskets if (b["universe"], b["basket_id"]) in part_fill_bids]
    if not part_baskets:
        part_baskets = [b for b in all_baskets if b["exit_reason"] == "window_end"]
    part_trace = _trace_for(part_baskets[0] if part_baskets else None)

    return {
        "winning_basket": win_trace,
        "falling_stock_with_additions": multi_trace,
        "stopped_basket": stop_trace,
        "premarket_trade": pm_trace,
        "partial_fill_or_cutoff_exit": part_trace,
    }


def _compute_cross_sectional_breakdowns(
    cache: SliceCache,
    ua_baskets: list[dict[str, Any]],
    ub_baskets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Break down basket performance by price tier, gap size, holding duration, and point-in-time SEC shares."""
    out: dict[str, Any] = {}
    for u_name, b_list in [("liquid_reference", ua_baskets), ("morning_active", ub_baskets)]:
        if not b_list:
            out[u_name] = {}
            continue
        df = pd.DataFrame(b_list)
        df["hold_min"] = np.maximum(1, df["closed_minute"] - df["opened_minute"])
        df["price_tier"] = pd.cut(
            df["avg_entry_price"],
            bins=[0.0, 5.0, 10.0, 20.0, 50.0, 1000.0],
            labels=["$1-$5", "$5-$10", "$10-$20", "$20-$50", "$50+"],
        )
        df["duration_tier"] = pd.cut(
            df["hold_min"],
            bins=[0, 15, 60, 180, 100_000],
            labels=["<=15m", "16-60m", "61-180m", ">180m"],
        )

        # Attach prev_close and pit_shares_out from cache metadata
        gaps = []
        shares_tier = []
        for row in df.itertuples(index=False):
            d_s, t_s = str(row.opened_date), str(row.ticker)
            if u_name == "liquid_reference":
                meta = cache.univ_a_by_day.get(d_s, {}).get(t_s)
                pc = meta[0] if meta else row.avg_entry_price
                sh = meta[4] if meta else None
            else:
                meta_b = getattr(cache, "univ_b_by_day", {}).get(d_s, {}).get(t_s)
                pc = meta_b[0] if meta_b else row.avg_entry_price / 1.15
                sh = meta_b[2] if meta_b else None
            gap_pct = 100.0 * (row.avg_entry_price / pc - 1.0) if pc and pc > 0 else 0.0
            gaps.append(gap_pct)
            if sh is None:
                shares_tier.append("unknown_sec_shares")
            elif sh <= 20_000_000:
                shares_tier.append("<=20M_shares_pit")
            else:
                shares_tier.append(">20M_shares_pit")

        df["gap_pct"] = gaps
        df["shares_tier"] = shares_tier
        df["gap_tier"] = pd.cut(
            df["gap_pct"],
            bins=[-100.0, 5.0, 20.0, 50.0, 10000.0],
            labels=["<5%", "5-20%", "20-50%", "50%+"],
        )

        u_break: dict[str, Any] = {}
        for col in ("price_tier", "duration_tier", "gap_tier", "shares_tier"):
            grp_dict = {}
            for k, g in df.groupby(col, observed=True):
                if len(g) == 0:
                    continue
                gw = float(g[g["net_pnl"] > 0]["net_pnl"].sum())
                gl = float(-g[g["net_pnl"] <= 0]["net_pnl"].sum())
                grp_dict[str(k)] = {
                    "baskets": int(len(g)),
                    "win_rate_pct": round(100.0 * float((g["net_pnl"] > 0).mean()), 1),
                    "net_pnl_usd": round(float(g["net_pnl"].sum()), 2),
                    "expectancy_usd": round(float(g["net_pnl"].mean()), 2),
                    "pf": round(gw / gl, 3) if gl > 0 else None,
                }
            u_break[col] = grp_dict
        out[u_name] = u_break
    return out


def main() -> int:
    t0 = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    cache = SliceCache(BB_DB_PATH)
    # Add univ_a_by_day and univ_b_by_day on cache for cross-sectional breakdown lookup
    cache.univ_a_by_day = {}
    for tkr, d, pc, adv, has_ext, act, sh in cache.con.execute(
        "SELECT ticker, d::VARCHAR, prev_close, adv20_usd, has_ext, is_active_2026, pit_shares_out FROM meta_univ_a"
    ).fetchall():
        cache.univ_a_by_day.setdefault(str(d), {})[str(tkr)] = (
            float(pc), float(adv), bool(has_ext), bool(act), float(sh) if sh is not None else None
        )
    cache.univ_b_by_day = {}
    for tkr, d, pc, act, sh in cache.con.execute(
        "SELECT ticker, d::VARCHAR, prev_close, is_active_2026, pit_shares_out FROM meta_univ_b"
    ).fetchall():
        cache.univ_b_by_day.setdefault(str(d), {})[str(tkr)] = (
            float(pc), bool(act), float(sh) if sh is not None else None
        )

    all_results: dict[str, Any] = {
        "baselines": {"liquid_reference": {}, "morning_active": {}},
        "baselines_by_split": {"liquid_reference": {}, "morning_active": {}},
        "sessions_comparison": [],
        "ablations": [],
        "walk_forward": [],
        "stress_tests": [],
        "additions_breakdown": {},
        "cross_sectional": {},
        "grid_96": {},
        "grid_selection": {},
        "nbbo_validation": {},
        "representative_traces": {},
    }

    print("Step 1/7: Running fixed baselines (A, B_single, B_exp_matched, C, D_H1_intraday, D_H1_swing)...", flush=True)
    ua_base_ledgers: dict[str, list[dict[str, Any]]] = {}
    ub_base_ledgers: dict[str, list[dict[str, Any]]] = {}

    for u in ("liquid_reference", "morning_active"):
        b_configs = baseline_configs(u, session="morning_combined", split="full")
        # First run Baseline A and B_single to measure actual average deployed capital ratio for B_exp_matched
        res_a = cache.run_config(b_configs[0], keep_ledgers=True)
        res_b = cache.run_config(b_configs[1], keep_ledgers=True)

        # Compute exact realized exposure ratio between A and B_single so B_exp_matched matches A's capital deployed
        exp_ratio = (
            res_a["avg_gross_exposure_usd"] / max(res_b["avg_gross_exposure_usd"], 1.0)
            if res_b["avg_gross_exposure_usd"] > 0
            else 1.25
        )
        matched_alloc = min(0.10, round(0.02 * max(1.0, exp_ratio), 4))
        b_configs[2] = replace(
            b_configs[2],
            account=replace(b_configs[2].account, entry_alloc_pct_e0=matched_alloc, max_committed_pct_e0=matched_alloc),
        )

        _save_baseline_ledgers(b_configs[0].tag, res_a["_ledgers"])
        _save_baseline_ledgers(b_configs[1].tag, res_b["_ledgers"])
        if u == "liquid_reference":
            ua_base_ledgers = res_a["_ledgers"]
        else:
            ub_base_ledgers = res_a["_ledgers"]

        all_results["baselines"][u][b_configs[0].tag] = res_a
        all_results["baselines"][u][b_configs[1].tag] = res_b
        all_results["additions_breakdown"][u] = res_a["by_year"] and res_a["by_entries"]

        for cfg in b_configs[2:]:
            r_c = cache.run_config(cfg, keep_ledgers=True)
            if cfg.tag.endswith("_D_H1_swing"):
                _save_baseline_ledgers(cfg.tag, r_c["_ledgers"])
            all_results["baselines"][u][cfg.tag] = r_c

        for k, v in all_results["baselines"][u].items():
            print(
                f"   {k:48s}: baskets={v['baskets']:4d} entries={v['entries']:4d} "
                f"net_pnl=${v['net_pnl_usd']:9.2f} PF={str(v['profit_factor']):6s} "
                f"maxDD={v['max_drawdown_pct']:6.2f}% sharpe={v['sharpe']:6.3f}",
                flush=True,
            )

        # Also evaluate Baseline A across Development, Validation, Evaluation splits
        for sp in ("development", "validation", "evaluation"):
            c_sp = replace(b_configs[0], split=sp, tag=f"{u}_A_{sp}")
            all_results["baselines_by_split"][u][sp] = cache.run_config(c_sp, keep_ledgers=False)

    print("Step 2/7: Running all 4 session windows separately (Section 6)...", flush=True)
    for u in ("liquid_reference", "morning_active"):
        for sess in ("morning_combined", "premarket_only", "opening_hour", "regular_session"):
            c_sess = RunConfig(tag=f"{u}_{sess}_A", universe=u, session=sess, split="full")
            r_s = cache.run_config(c_sess, keep_ledgers=False)
            all_results["sessions_comparison"].append({
                "universe": u,
                "session": sess,
                "window_et": f"{SESSION_WINDOWS[sess]['start']}-{SESSION_WINDOWS[sess]['end']}",
                "baskets": r_s["baskets"],
                "entries": r_s["entries"],
                "win_rate_pct": r_s["win_rate_pct"],
                "profit_factor": r_s["profit_factor"],
                "expectancy_usd": r_s["expectancy_usd"],
                "net_pnl_usd": r_s["net_pnl_usd"],
                "total_return_pct": r_s["total_return_pct"],
                "max_drawdown_pct": r_s["max_drawdown_pct"],
                "sharpe": r_s["sharpe"],
                "total_fees_usd": r_s["total_fees_usd"],
            })

    print("Step 3/7: Running 5 separately labeled ablations (Section 9)...", flush=True)
    for u in ("liquid_reference", "morning_active"):
        base_c = RunConfig(tag=f"{u}_base", universe=u, session="morning_combined", split="full")
        ablation_defs = [
            ("baseline_A", base_c),
            ("exit_middle_band", replace(base_c, tag=f"{u}_abl_mid", strategy=replace(base_c.strategy, exit_band="middle"))),
            ("exit_upper_unconditional", replace(base_c, tag=f"{u}_abl_uncond", strategy=replace(base_c.strategy, require_profit_on_exit=False))),
            ("no_additional_entries", replace(base_c, tag=f"{u}_abl_1entry", strategy=replace(base_c.strategy, max_entries=1))),
            ("fixed_dollar_sizing", replace(base_c, tag=f"{u}_abl_fixed", account=replace(base_c.account, fixed_dollar_sizing=True))),
            ("multiplier_1p5_martingale", replace(base_c, tag=f"{u}_abl_mult15", strategy=replace(base_c.strategy, multiplier=1.5))),
        ]
        for abl_name, abl_cfg in ablation_defs:
            r_ab = cache.run_config(abl_cfg, keep_ledgers=False)
            all_results["ablations"].append({
                "universe": u,
                "ablation": abl_name,
                "baskets": r_ab["baskets"],
                "entries": r_ab["entries"],
                "win_rate_pct": r_ab["win_rate_pct"],
                "profit_factor": r_ab["profit_factor"],
                "expectancy_usd": r_ab["expectancy_usd"],
                "net_pnl_usd": r_ab["net_pnl_usd"],
                "max_drawdown_pct": r_ab["max_drawdown_pct"],
                "sharpe": r_ab["sharpe"],
                "largest_loss_usd": r_ab["largest_loss_usd"],
            })

    print("Step 4/7: Running 6-fold rolling walk-forward validation and stress tests (Section 10)...", flush=True)
    all_days = cache.all_days
    # 6 rolling folds: 250-day train -> 125-day test, stepped by 125 days
    candidate_pool = [
        StrategyParams(timeframe="5m", period=50, deviation=2.0, spacing=5, max_entries=1),
        StrategyParams(timeframe="5m", period=50, deviation=2.0, spacing=10, max_entries=3),
        StrategyParams(timeframe="5m", period=100, deviation=2.0, spacing=10, max_entries=1),
        StrategyParams(timeframe="5m", period=100, deviation=2.0, spacing=10, max_entries=5),
        StrategyParams(timeframe="5m", period=100, deviation=2.5, spacing=10, max_entries=1),
        StrategyParams(timeframe="5m", period=200, deviation=2.0, spacing=10, max_entries=1),
        StrategyParams(timeframe="5m", period=200, deviation=2.5, spacing=10, max_entries=5),
    ]
    for u in ("liquid_reference", "morning_active"):
        for fold_idx in range(6):
            tr_start = fold_idx * 125
            tr_end = tr_start + 250
            te_end = min(len(all_days), tr_end + 125)
            if te_end <= tr_end + 20:
                break
            d_tr_lo, d_tr_hi = all_days[tr_start], all_days[tr_end - 1]
            d_te_lo, d_te_hi = all_days[tr_end], all_days[te_end - 1]

            best_sp = candidate_pool[0]
            best_tr_res = None
            best_tr_sharpe = -999.0
            for sp_cand in candidate_pool:
                c_tr = RunConfig(
                    tag=f"wf_{u}_f{fold_idx+1}_tr",
                    universe=u, session="morning_combined",
                    date_from=d_tr_lo, date_to=d_tr_hi,
                    strategy=sp_cand,
                )
                r_tr = cache.run_config(c_tr, keep_ledgers=False)
                if r_tr["baskets"] >= 10 and float(r_tr["sharpe"]) > best_tr_sharpe:
                    best_tr_sharpe = float(r_tr["sharpe"])
                    best_sp = sp_cand
                    best_tr_res = r_tr

            c_te = RunConfig(
                tag=f"wf_{u}_f{fold_idx+1}_te",
                universe=u, session="morning_combined",
                date_from=d_te_lo, date_to=d_te_hi,
                strategy=best_sp,
            )
            r_te = cache.run_config(c_te, keep_ledgers=False)
            all_results["walk_forward"].append({
                "universe": u,
                "fold": fold_idx + 1,
                "train_span": f"{d_tr_lo}..{d_tr_hi}",
                "test_span": f"{d_te_lo}..{d_te_hi}",
                "selected_params": f"5m P{best_sp.period} K{best_sp.deviation} S{best_sp.spacing} E{best_sp.max_entries}",
                "train_net_pnl_usd": best_tr_res["net_pnl_usd"] if best_tr_res else 0.0,
                "train_pf": best_tr_res["profit_factor"] if best_tr_res else None,
                "train_sharpe": best_tr_res["sharpe"] if best_tr_res else 0.0,
                "test_baskets": r_te["baskets"],
                "test_net_pnl_usd": r_te["net_pnl_usd"],
                "test_pf": r_te["profit_factor"],
                "test_sharpe": r_te["sharpe"],
                "test_max_dd_pct": r_te["max_drawdown_pct"],
            })

        # Stress tests on Baseline A
        base_c = RunConfig(tag=f"{u}_stress_base", universe=u, session="morning_combined", split="full")
        stress_defs = [
            ("base_costs", base_c),
            ("2x_costs_and_slippage", replace(base_c, execution=replace(base_c.execution, slippage_per_share=0.02, commission_mult=2.0))),
            ("3x_slippage_2x_spread", replace(base_c, execution=replace(base_c.execution, slippage_per_share=0.03, half_spread_min=0.02, rth_range_spread_frac=0.12, ext_range_spread_frac=0.24))),
            ("latency_2m_delay", replace(base_c, execution=replace(base_c.execution, latency_bars=2))),
            ("reduced_capacity_3pct", replace(base_c, execution=replace(base_c.execution, max_bar_participation=0.03, max_order_vol_share=0.03))),
            ("start_2022", replace(base_c, date_from="2022-01-03", date_to="2026-09-21")),
            ("start_2023", replace(base_c, date_from="2023-01-03", date_to="2026-09-21")),
            ("start_2024", replace(base_c, date_from="2024-01-02", date_to="2026-09-21")),
            ("start_2025", replace(base_c, date_from="2025-01-02", date_to="2026-09-21")),
        ]
        for st_name, st_cfg in stress_defs:
            r_st = cache.run_config(replace(st_cfg, tag=f"{u}_{st_name}"), keep_ledgers=False)
            all_results["stress_tests"].append({
                "universe": u,
                "stress_case": st_name,
                "baskets": r_st["baskets"],
                "entries": r_st["entries"],
                "profit_factor": r_st["profit_factor"],
                "net_pnl_usd": r_st["net_pnl_usd"],
                "max_drawdown_pct": r_st["max_drawdown_pct"],
                "sharpe": r_st["sharpe"],
                "ex_top5_days_pnl_usd": r_st["ex_top5_days_pnl_usd"],
                "ex_top5_stocks_pnl_usd": r_st["ex_top5_stocks_pnl_usd"],
            })

    print("Step 5/7: Computing cross-sectional breakdowns, representative traces, and NBBO tick validation...", flush=True)
    all_results["cross_sectional"] = _compute_cross_sectional_breakdowns(
        cache,
        ua_base_ledgers.get("baskets", []),
        ub_base_ledgers.get("baskets", []),
    )
    all_results["representative_traces"] = _extract_representative_traces(ua_base_ledgers, ub_base_ledgers)

    # Preserve the already-validated NBBO quote check if present on disk so we don't re-read gzip files
    nbbo_path = RESULTS_DIR / "nbbo_validation.json"
    if nbbo_path.exists():
        all_results["nbbo_validation"] = json.loads(nbbo_path.read_text(encoding="utf-8"))
    else:
        all_results["nbbo_validation"]["liquid_reference"] = run_nbbo_validation_sample(
            ua_base_ledgers.get("fills", []), max_samples=10
        )
        all_results["nbbo_validation"]["morning_active"] = run_nbbo_validation_sample(
            ub_base_ledgers.get("fills", []), max_samples=10
        )
    cache.close()

    print("Step 6/7: Running 96-configuration intraday grid across both universes in parallel...", flush=True)
    existing_grid_csv = RESULTS_DIR / "grid_96_results.csv"
    existing_sel_json = RESULTS_DIR / "grid_selection_summary.json"
    cached_ma_rows: list[dict[str, Any]] | None = None
    cached_ma_sel: dict[str, Any] | None = None
    if existing_grid_csv.exists() and existing_sel_json.exists():
        df_old = pd.read_csv(existing_grid_csv)
        ma_old = df_old[df_old["universe"] == "morning_active"]
        sel_old = json.loads(existing_sel_json.read_text(encoding="utf-8"))
        if len(ma_old) == 96 and "morning_active" in sel_old:
            cached_ma_rows = ma_old.where(pd.notna(ma_old), None).to_dict(orient="records")
            cached_ma_sel = sel_old["morning_active"]

    tasks: list[tuple[str, str, int, float, list[RunConfig]]] = []
    universes_to_grid = ("liquid_reference",) if cached_ma_rows is not None else ("liquid_reference", "morning_active")
    for u in universes_to_grid:
        cfgs = grid_96_configs(u, session="morning_combined", split="development")
        by_slice: dict[tuple[str, int, float], list[RunConfig]] = {}
        for c in cfgs:
            by_slice.setdefault((c.strategy.timeframe, c.strategy.period, c.strategy.deviation), []).append(c)
        for (tf, per, dv), sub_cfgs in by_slice.items():
            tasks.append((u, tf, per, dv, sub_cfgs))

    raw_by_univ: dict[str, list[dict[str, Any]]] = {"liquid_reference": [], "morning_active": cached_ma_rows or []}
    with ProcessPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(_run_slice_chunk_worker, t): t for t in tasks}
        done_chunks = 0
        for fut in as_completed(futs):
            t_info = futs[fut]
            chunk_rows = fut.result()
            raw_by_univ[t_info[0]].extend(chunk_rows)
            done_chunks += 1
            if done_chunks % 4 == 0 or done_chunks == len(tasks):
                print(f"   grid chunks completed: {done_chunks}/{len(tasks)}", flush=True)

    grid_all_rows: list[dict[str, Any]] = []
    for u in ("liquid_reference", "morning_active"):
        if u == "morning_active" and cached_ma_rows is not None and cached_ma_sel is not None:
            u_rows, u_sel = cached_ma_rows, cached_ma_sel
        else:
            u_rows, u_sel = _finalize_grid_for_universe(u, raw_by_univ[u])
        all_results["grid_96"][u] = u_rows
        all_results["grid_selection"][u] = u_sel
        grid_all_rows.extend(u_rows)

    pd.DataFrame(grid_all_rows).to_csv(RESULTS_DIR / "grid_96_results.csv", index=False)
    (RESULTS_DIR / "grid_selection_summary.json").write_text(
        json.dumps(all_results["grid_selection"], indent=2), encoding="utf-8"
    )
    (RESULTS_DIR / "representative_traces.json").write_text(
        json.dumps(all_results["representative_traces"], indent=2), encoding="utf-8"
    )
    (RESULTS_DIR / "nbbo_validation.json").write_text(
        json.dumps(all_results["nbbo_validation"], indent=2), encoding="utf-8"
    )

    print("Step 7/7: Generating diagnostic charts and writing `all_experiments.json`...", flush=True)
    plot_files = generate_all_plots(all_results, PLOTS_DIR)
    all_results["generated_plots"] = plot_files

    # Strip bulk `_ledgers` from `all_experiments.json` (ledgers are already saved as CSVs in `results/ledgers/`)
    for u in ("liquid_reference", "morning_active"):
        for k in all_results["baselines"][u]:
            all_results["baselines"][u][k].pop("_ledgers", None)

    (RESULTS_DIR / "all_experiments.json").write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"All experiments completed in {time.time() - t0:.1f}s! Results in {RESULTS_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
