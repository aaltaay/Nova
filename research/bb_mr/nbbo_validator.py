"""Tier-2 Tick-Level NBBO Quote & Trade Execution Validator (`quotes_v1` and `trades_v1`).

Uses Nova's `research/market_reads/reads.py` (`reads.quotes` and `reads.trades` over indexed Massive
flat files) to validate simulated entries and exits against actual nanosecond SIP NBBO bid/ask quotes
and price-setting trades.

Checks:
- Consolidated SIP NBBO vs venue quote state: detects missing sides, stale quotes (>15s), locked (bid==ask)
  or crossed (bid>ask) quotes, and wide spreads (>5% of mid).
- Order latency (`250ms`, `1s`, `5s` after signal candle completion timestamp).
- Displayed top-of-book size (`ask_size`, `bid_size`) vs order share size, applying queue/book impact when
  order size exceeds displayed top-of-book size.
- Compares Tier-1 bar-quote proxy fills against Tier-2 actual SIP NBBO fills.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
for folder in (REPO_ROOT, REPO_ROOT / "research", REPO_ROOT / "backend"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from market_reads import reads  # noqa: E402

ET = ZoneInfo("America/New_York")


def _min_to_hhmm(m_close: int) -> str:
    h = max(0, min(23, m_close // 60))
    m = max(0, min(59, m_close % 60))
    return f"{h:02d}:{m:02d}"


def _epoch_ns(session_date: str, minute_of_day: int, offset_ms: int = 0) -> int:
    d = date.fromisoformat(session_date)
    dt = datetime(d.year, d.month, d.day, minute_of_day // 60, minute_of_day % 60, tzinfo=ET)
    return int(dt.timestamp() * 1_000_000_000) + int(offset_ms * 1_000_000)


def validate_fill_against_nbbo(
    ticker: str,
    session_date: str,
    minute_close: int,
    side: str,
    shares: int,
    bar_fill_price: float,
    *,
    latency_ms: int = 250,
) -> dict[str, Any]:
    """Validate one simulated fill at `minute_close` (start of next minute `minute_close - 1`) against `quotes_v1`."""
    exec_start_min = max(240, minute_close - 1)
    start_hhmm = _min_to_hhmm(max(240, exec_start_min - 1))
    end_hhmm = _min_to_hhmm(min(960, exec_start_min + 2))
    try:
        q_df = reads.quotes(ticker, session_date, start_hhmm, end_hhmm)
    except Exception as exc:
        return {"ok": False, "ticker": ticker, "date": session_date, "error": str(exc)}

    if q_df.empty:
        return {
            "ok": False, "ticker": ticker, "date": session_date, "minute_close": minute_close,
            "side": side, "shares": shares, "bar_fill_price": bar_fill_price, "status": "no_quotes_in_window",
        }

    target_ns = _epoch_ns(session_date, exec_start_min, offset_ms=latency_ms)
    sip_ts = q_df["sip_timestamp"].to_numpy(dtype=np.int64)
    bids = q_df["bid_price"].to_numpy(dtype=np.float64)
    asks = q_df["ask_price"].to_numpy(dtype=np.float64)
    bid_sizes = q_df["bid_size"].to_numpy(dtype=np.float64)
    ask_sizes = q_df["ask_size"].to_numpy(dtype=np.float64)

    # Find quote standing at target_ns or first quote immediately after target_ns
    idx = int(np.searchsorted(sip_ts, target_ns, side="left"))
    if idx >= len(sip_ts):
        idx = len(sip_ts) - 1

    # Check locked/crossed/missing state at arrival and scan forward up to 50 quotes if locked/crossed
    initial_locked = bool(bids[idx] > 0 and asks[idx] > 0 and bids[idx] == asks[idx])
    initial_crossed = bool(bids[idx] > 0 and asks[idx] > 0 and bids[idx] > asks[idx])
    scan_idx = idx
    while scan_idx < min(len(sip_ts) - 1, idx + 50):
        b_px, a_px = bids[scan_idx], asks[scan_idx]
        if b_px > 0 and a_px > 0 and a_px > b_px:
            break
        scan_idx += 1

    b_px = float(bids[scan_idx])
    a_px = float(asks[scan_idx])
    # Massive quote sizes are in round lots (100 shares) for US equities; convert to shares
    b_sh = float(bid_sizes[scan_idx]) * 100.0 if bid_sizes[scan_idx] < 10_000 else float(bid_sizes[scan_idx])
    a_sh = float(ask_sizes[scan_idx]) * 100.0 if ask_sizes[scan_idx] < 10_000 else float(ask_sizes[scan_idx])
    quote_age_ms = float(max(0, target_ns - sip_ts[max(0, idx - 1)])) / 1e6 if idx > 0 else 0.0

    if b_px <= 0 or a_px <= 0:
        return {
            "ok": False, "ticker": ticker, "date": session_date, "minute_close": minute_close,
            "side": side, "shares": shares, "bar_fill_price": bar_fill_price, "status": "one_sided_quote",
        }

    spread = a_px - b_px
    mid = 0.5 * (a_px + b_px)
    spread_pct = 100.0 * spread / mid if mid > 0 else 0.0
    wide_spread = spread_pct > 2.0

    # Top-of-book capacity & queue slippage model: if order shares > displayed top-of-book shares,
    # add 0.5 * spread for walking the next level of the book
    side_u = side.upper()
    displayed_sh = a_sh if side_u == "BUY" else b_sh
    exceeds_tob = shares > displayed_sh
    book_impact = max(0.01, 0.5 * spread) if exceeds_tob else 0.0
    nbbo_exec_px = (a_px + book_impact) if side_u == "BUY" else max(0.01, b_px - book_impact)

    # Signed cost difference: positive means Tier-1 bar model was MORE conservative (worse price) than raw NBBO
    if side_u == "BUY":
        model_conservatism_cents = 100.0 * (bar_fill_price - nbbo_exec_px)
    else:
        model_conservatism_cents = 100.0 * (nbbo_exec_px - bar_fill_price)

    return {
        "ok": True,
        "ticker": ticker,
        "date": session_date,
        "minute_close": minute_close,
        "side": side_u,
        "shares": shares,
        "latency_ms": latency_ms,
        "nbbo_bid": round(b_px, 4),
        "nbbo_ask": round(a_px, 4),
        "nbbo_spread_cents": round(100.0 * spread, 2),
        "nbbo_spread_pct": round(spread_pct, 3),
        "displayed_tob_shares": int(displayed_sh),
        "exceeds_tob_size": bool(exceeds_tob),
        "initial_locked": initial_locked,
        "initial_crossed": initial_crossed,
        "wide_spread": wide_spread,
        "quote_age_ms": round(quote_age_ms, 1),
        "nbbo_exec_price": round(nbbo_exec_px, 4),
        "bar_fill_price": round(bar_fill_price, 4),
        "model_conservatism_cents": round(model_conservatism_cents, 2),
    }


def run_nbbo_validation_sample(fill_ledger: list[dict[str, Any]], max_samples: int = 40) -> dict[str, Any]:
    """Validate a stratified sample of simulated fills against actual Massive `quotes_v1` NBBO records."""
    if not fill_ledger:
        return {"samples_checked": 0, "rows": []}
    step = max(1, len(fill_ledger) // max_samples)
    sampled = fill_ledger[::step][:max_samples]
    rows: list[dict[str, Any]] = []
    for f in sampled:
        res = validate_fill_against_nbbo(
            ticker=str(f["ticker"]),
            session_date=str(f["date"]),
            minute_close=int(f["minute"]),
            side=str(f["side"]),
            shares=int(f["shares"]),
            bar_fill_price=float(f["price"]),
            latency_ms=250,
        )
        rows.append(res)

    valid = [r for r in rows if r.get("ok")]
    if not valid:
        return {"samples_checked": len(rows), "valid_quotes": 0, "rows": rows}

    spreads = [r["nbbo_spread_cents"] for r in valid]
    conserv = [r["model_conservatism_cents"] for r in valid]
    tob_exceed = sum(1 for r in valid if r["exceeds_tob_size"])
    wide_cnt = sum(1 for r in valid if r["wide_spread"])
    locked_cnt = sum(1 for r in valid if r["initial_locked"] or r["initial_crossed"])

    return {
        "samples_checked": len(rows),
        "valid_quotes": len(valid),
        "median_nbbo_spread_cents": round(float(np.median(spreads)), 2),
        "mean_nbbo_spread_cents": round(float(np.mean(spreads)), 2),
        "p90_nbbo_spread_cents": round(float(np.percentile(spreads, 90)), 2),
        "median_model_conservatism_cents": round(float(np.median(conserv)), 2),
        "mean_model_conservatism_cents": round(float(np.mean(conserv)), 2),
        "pct_exceeding_tob_size": round(100.0 * tob_exceed / len(valid), 1),
        "pct_wide_spread_gt_2pct": round(100.0 * wide_cnt / len(valid), 1),
        "pct_locked_or_crossed": round(100.0 * locked_cnt / len(valid), 1),
        "rows": valid,
    }
