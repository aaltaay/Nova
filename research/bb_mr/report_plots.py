"""Generate reproducible research charts for the U.S. Stock Bollinger Bands mean-reversion study."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def generate_all_plots(
    results: dict[str, Any],
    plots_dir: Path,
) -> list[str]:
    """Render and save diagnostic charts; returns list of generated file paths."""
    plots_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    plt.rcParams.update({
        "figure.facecolor": "#0f172a",
        "axes.facecolor": "#1e293b",
        "axes.edgecolor": "#475569",
        "axes.labelcolor": "#e2e8f0",
        "text.color": "#f8fafc",
        "xtick.color": "#cbd5e1",
        "ytick.color": "#cbd5e1",
        "grid.color": "#334155",
        "font.size": 10,
    })

    # 1. Baseline Balance vs. Marked Equity Curves (Universe A & Universe B)
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    for ax_idx, (univ_key, univ_title) in enumerate([
        ("liquid_reference", "Universe A: Liquid-Stock Reference ($5-$200, ADV20 >= $20M)"),
        ("morning_active", "Universe B: Morning Active-Stock Universe ($1-$30, >= +10%, CumDVol >= $500k)"),
    ]):
        ax = axes[ax_idx]
        baselines = results.get("baselines", {}).get(univ_key, {})
        colors = {
            "A": ("#38bdf8", "A: 5m P100 K2.0 (Max 5 Entries)"),
            "B_single": ("#a855f7", "B: 5m P100 K2.0 (1 Entry Only)"),
            "B_exp_matched": ("#f59e0b", "B_exp: 1 Entry Exposure-Matched"),
            "C_200_2p5": ("#22c55e", "C: 5m P200 K2.5 (Max 5 Entries)"),
            "D_H1_intraday": ("#ef4444", "D1: H1 P100 K2.0 (Intraday Flat)"),
            "D_H1_swing": ("#ec4899", "D2: H1 P100 K2.0 (Overnight Swing)"),
        }
        for short_k, (color, label) in colors.items():
            full_key = next((k for k in baselines if k.endswith(f"_{short_k}")), None)
            if not full_key:
                continue
            daily = baselines[full_key].get("_ledgers", {}).get("daily", [])
            if not daily:
                continue
            df = pd.DataFrame(daily)
            dates = pd.to_datetime(df["date"])
            ax.plot(dates, df["equity"], label=f"{label} (Equity)", color=color, linewidth=1.6)
            if short_k in ("A", "D_H1_swing"):
                ax.plot(dates, df["balance"], label=f"{label} (Balance)", color=color, linestyle="--", alpha=0.65, linewidth=1.0)
        ax.axhline(25000.0, color="#94a3b8", linestyle=":", linewidth=1.0)
        ax.set_title(f"{univ_title} -- Balance vs. Marked Equity ($25k Start)")
        ax.set_ylabel("Account Value ($)")
        ax.grid(True, alpha=0.4)
        ax.legend(loc="best", fontsize=8, ncol=2, facecolor="#0f172a", edgecolor="#475569")
    axes[-1].set_xlabel("Trading Date")
    fig.tight_layout()
    p1 = plots_dir / "bb_mr_baselines_equity_vs_balance.png"
    fig.savefig(p1, dpi=150)
    plt.close(fig)
    saved.append(str(p1))

    # 2. 96-Configuration Grid Distribution & Parameter Stability (Universe A vs Universe B)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    for ax_idx, (univ_key, univ_title) in enumerate([
        ("liquid_reference", "Universe A (Liquid Reference)"),
        ("morning_active", "Universe B (Morning Active)"),
    ]):
        ax = axes[ax_idx]
        grid_rows = results.get("grid_96", {}).get(univ_key, [])
        if grid_rows:
            df_g = pd.DataFrame(grid_rows)
            for tf, marker, col in [("1m", "o", "#f97316"), ("5m", "s", "#38bdf8")]:
                sub = df_g[df_g["timeframe"] == tf]
                ax.scatter(
                    sub["baskets"],
                    sub["net_pnl_usd"],
                    label=f"TF={tf} (n={len(sub)})",
                    color=col,
                    marker=marker,
                    alpha=0.8,
                    s=45,
                )
            ax.axhline(0.0, color="#ef4444", linestyle="--", linewidth=1.2, label="Breakeven ($0)")
        ax.set_title(f"96-Config Intraday Grid (Dev): {univ_title}")
        ax.set_xlabel("Number of Baskets")
        ax.set_ylabel("Net Dollar P&L ($)")
        ax.grid(True, alpha=0.4)
        ax.legend(facecolor="#0f172a", edgecolor="#475569")
    fig.tight_layout()
    p2 = plots_dir / "bb_mr_grid96_distribution.png"
    fig.savefig(p2, dpi=150)
    plt.close(fig)
    saved.append(str(p2))

    # 3. Breakdown by Session Window & Basket Additions (1..5 Entries)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    ax0 = axes[0]
    sess_rows = results.get("sessions_comparison", [])
    if sess_rows:
        df_s = pd.DataFrame(sess_rows)
        piv = df_s.pivot(index="session", columns="universe", values="net_pnl_usd")
        x = np.arange(len(piv.index))
        w = 0.35
        cols = list(piv.columns)
        for i, c in enumerate(cols):
            ax0.bar(x + (i - 0.5 * (len(cols) - 1)) * w, piv[c], width=w, label=c)
        ax0.set_xticks(x)
        ax0.set_xticklabels(piv.index, rotation=20)
        ax0.axhline(0.0, color="#ef4444", linestyle="--", linewidth=1.0)
        ax0.set_title("Net P&L ($) Across Session Windows (Baseline A)")
        ax0.set_ylabel("Net P&L ($)")
        ax0.grid(True, alpha=0.4)
        ax0.legend(facecolor="#0f172a", edgecolor="#475569")

    ax1 = axes[1]
    add_data = results.get("additions_breakdown", {})
    if add_data:
        entries_k = sorted(int(k) for k in add_data.get("morning_active", {}).keys())
        ua_vals = [add_data.get("liquid_reference", {}).get(str(k), add_data.get("liquid_reference", {}).get(k, {})).get("expectancy_usd", 0.0) for k in entries_k]
        ub_vals = [add_data.get("morning_active", {}).get(str(k), add_data.get("morning_active", {}).get(k, {})).get("expectancy_usd", 0.0) for k in entries_k]
        if entries_k:
            x = np.arange(len(entries_k))
            w = 0.35
            ax1.bar(x - w / 2, ua_vals, width=w, label="liquid_reference", color="#38bdf8")
            ax1.bar(x + w / 2, ub_vals, width=w, label="morning_active", color="#f97316")
            ax1.set_xticks(x)
            ax1.set_xticklabels([f"{k} Entries" for k in entries_k])
            ax1.axhline(0.0, color="#ef4444", linestyle="--", linewidth=1.0)
            ax1.set_title("Basket Expectancy ($/Basket) by Number of Entries")
            ax1.set_ylabel("Expectancy ($ / Basket)")
            ax1.grid(True, alpha=0.4)
            ax1.legend(facecolor="#0f172a", edgecolor="#475569")

    fig.tight_layout()
    p3 = plots_dir / "bb_mr_sessions_and_additions.png"
    fig.savefig(p3, dpi=150)
    plt.close(fig)
    saved.append(str(p3))

    # 4. Walk-Forward & Stress Test Diagnostics
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    ax_wf = axes[0]
    wf_rows = results.get("walk_forward", [])
    if wf_rows:
        df_wf = pd.DataFrame(wf_rows)
        for u_idx, (u_name, col) in enumerate([("liquid_reference", "#38bdf8"), ("morning_active", "#f97316")]):
            sub = df_wf[df_wf["universe"] == u_name]
            if not sub.empty:
                x = np.arange(len(sub))
                ax_wf.bar(x + (u_idx - 0.5) * 0.35, sub["test_net_pnl_usd"], width=0.35, label=u_name, color=col)
                ax_wf.set_xticks(x)
                ax_wf.set_xticklabels([f"Fold {r}" for r in sub["fold"]])
        ax_wf.axhline(0.0, color="#ef4444", linestyle="--", linewidth=1.0)
        ax_wf.set_title("Rolling Walk-Forward Out-of-Sample Net P&L ($)")
        ax_wf.set_ylabel("OOS Net P&L ($)")
        ax_wf.grid(True, alpha=0.4)
        ax_wf.legend(facecolor="#0f172a", edgecolor="#475569")

    ax_st = axes[1]
    st_rows = results.get("stress_tests", [])
    if st_rows:
        df_st = pd.DataFrame(st_rows)
        piv_st = df_st.pivot(index="stress_case", columns="universe", values="net_pnl_usd")
        y = np.arange(len(piv_st.index))
        h = 0.35
        for i, c in enumerate(piv_st.columns):
            ax_st.barh(y + (i - 0.5 * (len(piv_st.columns) - 1)) * h, piv_st[c], height=h, label=c)
        ax_st.set_yticks(y)
        ax_st.set_yticklabels(piv_st.index)
        ax_st.axvline(0.0, color="#ef4444", linestyle="--", linewidth=1.0)
        ax_st.set_title("Stress Test & Concentration Sensitivity (Net P&L $)")
        ax_st.set_xlabel("Net P&L ($)")
        ax_st.grid(True, alpha=0.4)
        ax_st.legend(facecolor="#0f172a", edgecolor="#475569")

    fig.tight_layout()
    p4 = plots_dir / "bb_mr_walkforward_and_stress.png"
    fig.savefig(p4, dpi=150)
    plt.close(fig)
    saved.append(str(p4))

    return saved
