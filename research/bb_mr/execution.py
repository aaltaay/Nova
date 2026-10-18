"""Honest stock execution model: IBKR fees, bid/ask spreads, extended-hours collars,
volume participation limits, partial fills, and halt handling.

Reuses Nova's `backend/practice/fees.py` for IBKR Pro Fixed commissions and SEC/FINRA/CAT fees.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from practice.fees import Fees, for_fill  # noqa: E402
from research.bb_mr.config import ExecutionParams  # noqa: E402


@dataclass(frozen=True)
class BarQuote:
    """Executable quote & liquidity derived from a 1-minute bar (or actual NBBO in Tier 2)."""

    session_date: str
    minute_close: int       # minutes after midnight ET when this 1m bar completed (e.g. 571 for 09:30 bar)
    open: float
    high: float
    low: float
    close: float
    volume: float
    bid: float              # executable bid price at the bar's open
    ask: float              # executable ask price at the bar's open
    close_bid: float        # executable bid price at the bar's close (for mark/exit evaluation)
    close_ask: float        # executable ask price at the bar's close
    half_spread: float
    halted: bool = False


def is_regular_hours(minute_close: int) -> bool:
    """True when the 1-minute bar falls inside regular trading hours (09:30-16:00 ET -> close 571..960)."""
    return 571 <= minute_close <= 960


def make_bar_quote(
    session_date: str,
    minute_close: int,
    open_px: float,
    high_px: float,
    low_px: float,
    close_px: float,
    volume: float,
    exec_params: ExecutionParams,
) -> BarQuote:
    """Construct executable bid/ask prices for a 1-minute bar without inventing depth."""
    if volume <= 0 or open_px <= 0 or close_px <= 0:
        return BarQuote(
            session_date=session_date,
            minute_close=minute_close,
            open=open_px,
            high=high_px,
            low=low_px,
            close=close_px,
            volume=0.0,
            bid=0.0,
            ask=0.0,
            close_bid=0.0,
            close_ask=0.0,
            half_spread=0.0,
            halted=True,
        )
    rth = is_regular_hours(minute_close)
    frac = exec_params.rth_range_spread_frac if rth else exec_params.ext_range_spread_frac
    bar_range = max(0.0, high_px - low_px)
    half_spread = max(exec_params.half_spread_min, frac * bar_range)
    # Cap modeled half-spread at 5% of price so a wide 1m range bar does not invent an absurd 20% spread
    half_spread = min(half_spread, 0.05 * open_px)

    ask_open = round(open_px + half_spread + exec_params.slippage_per_share, 4)
    bid_open = round(max(0.01, open_px - half_spread - exec_params.slippage_per_share), 4)
    ask_close = round(close_px + half_spread + exec_params.slippage_per_share, 4)
    bid_close = round(max(0.01, close_px - half_spread - exec_params.slippage_per_share), 4)
    return BarQuote(
        session_date=session_date,
        minute_close=minute_close,
        open=open_px,
        high=high_px,
        low=low_px,
        close=close_px,
        volume=volume,
        bid=bid_open,
        ask=ask_open,
        close_bid=bid_close,
        close_ask=ask_close,
        half_spread=round(half_spread, 4),
        halted=False,
    )


def compute_fill_fees(
    side: str,
    shares: int,
    price: float,
    exec_params: ExecutionParams,
    ts: float | None = None,
) -> Fees:
    """Compute IBKR Pro Fixed commission + SEC/FINRA/CAT fees, scaled by `commission_mult` for stress tests."""
    if shares <= 0 or price <= 0:
        return Fees(0.0, 0.0, 0.0, 0.0)
    raw = for_fill(side, float(shares), float(price), ts=ts)
    if exec_params.commission_mult == 1.0:
        return raw
    return Fees(
        commission=round(raw.commission * exec_params.commission_mult, 6),
        sec_fee=raw.sec_fee,
        finra_taf=raw.finra_taf,
        finra_cat=raw.finra_cat,
    )


def max_shares_for_budget(
    budget_usd: float,
    ask_price: float,
    exec_params: ExecutionParams,
    trailing_avg_vol: float | None = None,
) -> tuple[int, str | None]:
    """Compute whole shares affordable within `budget_usd` after opening fees and participation cap.

    Returns `(shares, rejection_reason_if_zero)`.
    """
    if ask_price <= 0 or budget_usd < ask_price:
        return 0, "insufficient_budget_for_one_share"
    raw_shares = int(budget_usd // ask_price)
    while raw_shares > 0:
        fee = compute_fill_fees("BUY", raw_shares, ask_price, exec_params).total
        if raw_shares * ask_price + fee <= budget_usd + 1e-9:
            break
        raw_shares -= 1
    if raw_shares < 1:
        return 0, "insufficient_budget_after_fees"

    if trailing_avg_vol is not None and exec_params.max_order_vol_share > 0:
        vol_cap = int(trailing_avg_vol * exec_params.max_order_vol_share)
        if vol_cap < 1:
            return 0, "participation_cap_zero_liquidity"
        raw_shares = min(raw_shares, vol_cap)
    return raw_shares, None


@dataclass(frozen=True)
class FillResult:
    filled_shares: int
    remaining_shares: int
    fill_price: float
    fees: Fees
    status: str             # "filled", "partial", "halted_waiting", "collar_expired"
    reason: str | None = None


def execute_order_on_bar(
    side: str,
    requested_shares: int,
    bar: BarQuote,
    exec_params: ExecutionParams,
    *,
    limit_collar_price: float | None = None,
) -> FillResult:
    """Execute a pending BUY (entry) or SELL (liquidation) order against a subsequent 1m BarQuote.

    Models:
    - Halts / zero-volume minutes: 0 shares filled; SELL liquidations remain open ("halted_waiting"),
      BUY entries in extended hours expire after their 1-bar TTL ("collar_expired").
    - Extended-hours marketable-limit collar: if `limit_collar_price` is set on a BUY outside RTH and
      the bar's executable ask exceeds `limit_collar_price`, the entry expires unfilled ("collar_expired").
    - Volume participation limit: at most `max_bar_participation * bar.volume` shares can fill in one bar.
      If `requested_shares` exceeds capacity, a partial fill occurs.
    """
    if requested_shares <= 0:
        return FillResult(0, 0, 0.0, Fees(0.0), "filled")
    if bar.halted or bar.volume <= 0:
        status = "collar_expired" if side.upper() == "BUY" else "halted_waiting"
        return FillResult(0, requested_shares, 0.0, Fees(0.0), status, reason="no_executable_volume")

    side_u = side.upper()
    exec_px = bar.ask if side_u == "BUY" else bar.bid
    if side_u == "BUY" and limit_collar_price is not None and exec_px > limit_collar_price + 1e-9:
        return FillResult(0, 0, 0.0, Fees(0.0), "collar_expired", reason="ask_above_extended_hours_collar")

    if exec_params.max_bar_participation > 0:
        capacity = max(1, int(bar.volume * exec_params.max_bar_participation))
    else:
        capacity = requested_shares

    filled = min(requested_shares, capacity)
    remaining = requested_shares - filled
    # For a BUY entry that only partially fills in its 1-bar window, we take the partial fill and cancel the rest
    # so stale entry remainders do not chase later bars; for a SELL liquidation, remaining shares stay pending!
    if side_u == "BUY":
        remaining = 0
        status = "filled" if filled == requested_shares else "partial"
    else:
        status = "filled" if remaining == 0 else "partial"

    fees = compute_fill_fees(side_u, filled, exec_px, exec_params)
    return FillResult(
        filled_shares=filled,
        remaining_shares=remaining,
        fill_price=exec_px,
        fees=fees,
        status=status,
    )
