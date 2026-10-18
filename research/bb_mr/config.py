"""Configuration, session windows, and pre-registered grids for Bollinger Bands mean-reversion."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, replace
from datetime import time as dtime
from pathlib import Path
from typing import Any

DATA_ROOT = Path(os.environ.get("NOVA_MARKET_DATA_DIR") or r"E:\Nova\massive")
STORE_DIR = DATA_ROOT / "store"
ORB_DB_PATH = STORE_DIR / "orb.duckdb"
BB_DB_PATH = STORE_DIR / "bb_mr.duckdb"
MOVERS_DB_PATH = DATA_ROOT / "movers" / "day_movers.sqlite3"
REF_DIR = STORE_DIR / "reference"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
PLOTS_DIR = Path(__file__).resolve().parent / "plots"
TZ_ET = "America/New_York"

SESSION_WINDOWS: dict[str, dict[str, str]] = {
    "morning_combined": {"start": "06:00", "end": "11:00", "entry_cutoff": "10:55", "warmup_session": "extended"},
    "premarket_only": {"start": "06:00", "end": "09:30", "entry_cutoff": "09:25", "warmup_session": "extended"},
    "opening_hour": {"start": "09:30", "end": "10:30", "entry_cutoff": "10:25", "warmup_session": "regular"},
    "regular_session": {"start": "09:30", "end": "16:00", "entry_cutoff": "15:50", "warmup_session": "regular"},
}

DATA_SPLITS: dict[str, tuple[str, str]] = {
    "development": ("2021-10-19", "2024-06-28"),
    "validation": ("2024-07-01", "2025-06-30"),
    "evaluation": ("2025-07-01", "2026-09-21"),
    "full": ("2021-10-19", "2026-09-21"),
}


def parse_hhmm(hhmm: str) -> dtime:
    h, m = (int(x) for x in hhmm.split(":"))
    return dtime(h, m)


@dataclass(frozen=True)
class StrategyParams:
    timeframe: str = "5m"                  # "1m", "5m", "1h"
    period: int = 100                      # 20, 50, 100, 200
    deviation: float = 2.0                 # 2.0, 2.5
    spacing: int = 10                      # minimum completed signal candles between same-stock entries
    max_entries: int = 5                   # 1, 3, 5
    multiplier: float = 1.0                # position size multiplier per additional entry
    exit_band: str = "upper"               # "upper" or "middle" (ablation)
    require_profit_on_exit: bool = True    # False for unconditional upper-band exit ablation
    overnight_hold: bool = False           # True only for the separate H1 swing experiment


@dataclass(frozen=True)
class AccountParams:
    start_equity: float = 25_000.0
    entry_alloc_pct_e0: float = 0.02       # 2% of frozen basket creation equity E0
    max_committed_pct_e0: float = 0.10     # 10% of E0 per basket
    max_simultaneous_stocks: int = 5
    max_gross_exposure_pct: float = 0.50   # 50% of current account equity for new purchases
    basket_loss_pct_e0: float = 0.005      # 0.5% of E0 basket loss budget
    daily_loss_pct: float = 0.03           # 3.0% of start-of-day account equity
    fixed_dollar_sizing: bool = False      # True for fixed-$25k non-compounding ablation


@dataclass(frozen=True)
class ExecutionParams:
    slippage_per_share: float = 0.01       # base adverse slippage ($/share)
    half_spread_min: float = 0.01          # minimum half-spread ($/share) from mid/open
    rth_range_spread_frac: float = 0.06    # additional half-spread as fraction of bar range in RTH
    ext_range_spread_frac: float = 0.12    # additional half-spread as fraction of bar range in premarket
    ext_limit_collar_pct: float = 0.01     # +1.0% marketable limit collar outside RTH
    max_bar_participation: float = 0.10    # max 10% of observed bar volume per fill
    max_order_vol_share: float = 0.10      # max 10% of trailing 5-bar average volume at order sizing
    latency_bars: int = 1                  # 1 = next 1m bar open; 2 = 2-bar delay stress test
    commission_mult: float = 1.0           # 1.0 = standard IBKR Fixed; 2.0 = 2x cost stress test


@dataclass(frozen=True)
class RunConfig:
    tag: str
    universe: str = "morning_active"       # "liquid_reference" or "morning_active"
    session: str = "morning_combined"      # key in SESSION_WINDOWS
    split: str = "full"                    # key in DATA_SPLITS or custom
    date_from: str | None = None
    date_to: str | None = None
    strategy: StrategyParams = field(default_factory=StrategyParams)
    account: AccountParams = field(default_factory=AccountParams)
    execution: ExecutionParams = field(default_factory=ExecutionParams)

    def window_dates(self) -> tuple[str, str]:
        lo, hi = DATA_SPLITS.get(self.split, DATA_SPLITS["full"])
        return self.date_from or lo, self.date_to or hi

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def baseline_configs(universe: str, session: str = "morning_combined", split: str = "full") -> list[RunConfig]:
    """Fixed baselines A, B, B_exp_matched, C, D_intraday, D_swing before any grid search."""
    base = RunConfig(tag=f"{universe}_{session}_A", universe=universe, session=session, split=split)
    b_single = replace(
        base,
        tag=f"{universe}_{session}_B_single",
        strategy=replace(base.strategy, max_entries=1),
    )
    # Exposure-matched single-entry baseline: 1 entry at 4% E0 (~matching mean deployed capital of multi-entry)
    b_exp = replace(
        base,
        tag=f"{universe}_{session}_B_exp_matched",
        strategy=replace(base.strategy, max_entries=1),
        account=replace(base.account, entry_alloc_pct_e0=0.04, max_committed_pct_e0=0.04),
    )
    c_200 = replace(
        base,
        tag=f"{universe}_{session}_C_200_2p5",
        strategy=replace(base.strategy, period=200, deviation=2.5),
    )
    d_intra = replace(
        base,
        tag=f"{universe}_{session}_D_H1_intraday",
        strategy=replace(base.strategy, timeframe="1h", period=100, deviation=2.0, spacing=10, overnight_hold=False),
    )
    d_swing = replace(
        base,
        tag=f"{universe}_regular_session_D_H1_swing",
        session="regular_session",
        strategy=replace(base.strategy, timeframe="1h", period=100, deviation=2.0, spacing=10, overnight_hold=True),
    )
    return [base, b_single, b_exp, c_200, d_intra, d_swing]


def grid_96_configs(universe: str, session: str = "morning_combined", split: str = "development") -> list[RunConfig]:
    """The 96 pre-registered configurations per universe on the primary morning window."""
    out: list[RunConfig] = []
    idx = 0
    for tf in ("1m", "5m"):
        for period in (20, 50, 100, 200):
            for dev in (2.0, 2.5):
                for spacing in (5, 10):
                    for max_entries in (1, 3, 5):
                        idx += 1
                        strat = StrategyParams(
                            timeframe=tf,
                            period=period,
                            deviation=dev,
                            spacing=spacing,
                            max_entries=max_entries,
                            multiplier=1.0,
                        )
                        tag = f"grid_{universe}_{idx:02d}_{tf}_p{period}_d{dev}_s{spacing}_e{max_entries}"
                        out.append(RunConfig(tag=tag, universe=universe, session=session, split=split, strategy=strat))
    return out
