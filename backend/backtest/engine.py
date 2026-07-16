"""
Backtest engine — walk archived 1m bars with no-hindsight setup evaluation.

Uses ``archive.replay.bars_by_symbol_for_day`` + ``slice_bars_as_of`` and the
existing signal-only setup evaluators. Simulates a simple long bracket: enter
on the bar AFTER eligibility at that bar's open; exit at stop, target, or EOD.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from archive.compact import cold_root
from archive.replay import bars_by_symbol_for_day, slice_bars_as_of
from backtest.scorer import score_trades
from constants import (
    ARCHIVE_SCHEMA_VERSION,
    BACKTEST_CANDIDATE_FLOAT,
    BACKTEST_CANDIDATE_HAS_NEWS,
    BACKTEST_CANDIDATE_REL_VOLUME,
    BACKTEST_DEFAULT_RISK_DOLLARS,
    BACKTEST_DEFAULT_SETUP,
    BACKTEST_MARKET_CLOSE_HOUR_ET,
    BACKTEST_MARKET_CLOSE_MINUTE_ET,
    BACKTEST_MAX_SYMBOLS,
    BACKTEST_MAX_TRADES_PER_DAY,
    BACKTEST_MIN_QTY,
    BACKTEST_SETUP_NAMES,
)
from strategy.abcd import evaluate_abcd
from strategy.bull_flag import evaluate_bull_flag
from strategy.gap_and_go import evaluate_gap_and_go
from strategy.setups import SETUP_NAMES

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

HONESTY = {
    "bar_resolution": "1m",
    "spread_modeled": False,
    "hindsight": False,
    "candidate_source": "synthesized_from_bars",
    "fill_model": "next_bar_open",
    "exit_model": "stop_target_or_eod",
}


@dataclass
class _PendingEntry:
    symbol: str
    setup: str
    stop_price: float
    target_price: float
    signal_ts: float


@dataclass
class _OpenPosition:
    symbol: str
    setup: str
    entry_ts: float
    entry_price: float
    stop_price: float
    target_price: float
    qty: int
    risk_dollars: float


@dataclass
class _SymbolState:
    pending: _PendingEntry | None = None
    open_pos: _OpenPosition | None = None
    last_eligible: dict[str, float] = field(default_factory=dict)


def _bar_now_et(bar: dict[str, Any]) -> datetime:
    ts = float(bar.get("ts") or 0)
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(_ET)


def _is_eod_bar(bar: dict[str, Any]) -> bool:
    now = _bar_now_et(bar)
    close = dtime(BACKTEST_MARKET_CLOSE_HOUR_ET, BACKTEST_MARKET_CLOSE_MINUTE_ET)
    t = now.timetz().replace(tzinfo=None)
    return t >= close


def _candidate_from_bars(symbol: str, bars: list[dict[str, Any]], session_date: str) -> dict[str, Any]:
    if not bars:
        return {
            "symbol": symbol,
            "price": None,
            "change_pct": None,
            "rel_volume": BACKTEST_CANDIDATE_REL_VOLUME,
            "has_news": BACKTEST_CANDIDATE_HAS_NEWS,
            "float": BACKTEST_CANDIDATE_FLOAT,
            "session_date": session_date,
            "source": "backtest",
        }
    last = bars[-1]
    first = bars[0]
    price = float(last.get("c") or 0)
    open_px = float(first.get("o") or price) or price
    change_pct = ((price - open_px) / open_px * 100.0) if open_px else 0.0
    vol = sum(float(b.get("v") or 0) for b in bars)
    return {
        "symbol": symbol,
        "price": price,
        "last": price,
        "current_price": price,
        "change_pct": change_pct,
        "gap_percent": change_pct,
        "rel_volume": BACKTEST_CANDIDATE_REL_VOLUME,
        "has_news": BACKTEST_CANDIDATE_HAS_NEWS,
        "float": BACKTEST_CANDIDATE_FLOAT,
        "volume": vol,
        "session_date": session_date,
        "source": "backtest",
    }


def _setups_to_run(setup: str) -> tuple[str, ...]:
    if setup == "all":
        return SETUP_NAMES
    if setup in SETUP_NAMES:
        return (setup,)
    raise ValueError(f"setup must be one of {BACKTEST_SETUP_NAMES}, got {setup!r}")


def _evaluate_one(
    setup: str,
    candidate: dict[str, Any],
    bars: list[dict[str, Any]],
    now_et: datetime,
):
    if setup == "gap_and_go":
        return evaluate_gap_and_go(candidate, bars, now_et=now_et)
    if setup == "bull_flag":
        return evaluate_bull_flag(candidate, bars)
    if setup == "abcd":
        return evaluate_abcd(candidate, bars)
    raise ValueError(f"unknown setup: {setup}")


def _first_eligible(
    setups: tuple[str, ...],
    candidate: dict[str, Any],
    bars: list[dict[str, Any]],
    now_et: datetime,
) -> tuple[str, Any] | None:
    for name in setups:
        signal = _evaluate_one(name, candidate, bars, now_et)
        if signal.eligible and signal.entry_price and signal.stop_price and signal.target_price:
            return name, signal
    return None


def _qty_for_entry(entry: float, stop: float) -> tuple[int, float]:
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return BACKTEST_MIN_QTY, BACKTEST_DEFAULT_RISK_DOLLARS
    qty = max(BACKTEST_MIN_QTY, int(BACKTEST_DEFAULT_RISK_DOLLARS / risk_per_share))
    return qty, BACKTEST_DEFAULT_RISK_DOLLARS


def _close_trade(
    pos: _OpenPosition,
    exit_ts: float,
    exit_price: float,
    exit_reason: str,
) -> dict[str, Any]:
    pnl_dollars = (exit_price - pos.entry_price) * pos.qty
    pnl_r = pnl_dollars / pos.risk_dollars if pos.risk_dollars else 0.0
    return {
        "symbol": pos.symbol,
        "setup": pos.setup,
        "entry_ts": pos.entry_ts,
        "exit_ts": exit_ts,
        "entry_price": round(pos.entry_price, 4),
        "exit_price": round(exit_price, 4),
        "stop_price": round(pos.stop_price, 4),
        "target_price": round(pos.target_price, 4),
        "qty": pos.qty,
        "pnl_dollars": round(pnl_dollars, 4),
        "pnl_r": round(pnl_r, 4),
        "exit_reason": exit_reason,
    }


def _try_exit_on_bar(pos: _OpenPosition, bar: dict[str, Any]) -> dict[str, Any] | None:
    low = float(bar.get("l") or 0)
    high = float(bar.get("h") or 0)
    ts = float(bar.get("ts") or 0)
    if low <= pos.stop_price:
        return _close_trade(pos, ts, pos.stop_price, "stop")
    if high >= pos.target_price:
        return _close_trade(pos, ts, pos.target_price, "target")
    if _is_eod_bar(bar):
        close = float(bar.get("c") or pos.entry_price)
        return _close_trade(pos, ts, close, "eod")
    return None


def _simulate_symbol(
    symbol: str,
    all_bars: list[dict[str, Any]],
    session_date: str,
    setups: tuple[str, ...],
    max_trades: int,
    trades_out: list[dict[str, Any]],
) -> None:
    if not all_bars:
        return
    state = _SymbolState()
    trades_for_symbol = 0

    for i, bar in enumerate(all_bars):
        ts = float(bar.get("ts") or 0)

        if state.open_pos is not None:
            closed = _try_exit_on_bar(state.open_pos, bar)
            if closed:
                trades_out.append(closed)
                state.open_pos = None
                trades_for_symbol += 1
            if state.open_pos is not None:
                continue

        if state.pending is not None:
            entry_px = float(bar.get("o") or bar.get("c") or 0)
            if entry_px > 0:
                qty, risk = _qty_for_entry(entry_px, state.pending.stop_price)
                state.open_pos = _OpenPosition(
                    symbol=symbol,
                    setup=state.pending.setup,
                    entry_ts=ts,
                    entry_price=entry_px,
                    stop_price=state.pending.stop_price,
                    target_price=state.pending.target_price,
                    qty=qty,
                    risk_dollars=risk,
                )
            state.pending = None
            closed = _try_exit_on_bar(state.open_pos, bar) if state.open_pos else None
            if closed:
                trades_out.append(closed)
                state.open_pos = None
                trades_for_symbol += 1
            if state.open_pos is not None or trades_for_symbol >= max_trades:
                continue

        if trades_for_symbol >= max_trades or state.open_pos or state.pending:
            continue

        visible = slice_bars_as_of(all_bars, ts)
        candidate = _candidate_from_bars(symbol, visible, session_date)
        now_et = _bar_now_et(bar)
        hit = _first_eligible(setups, candidate, visible, now_et)
        if not hit:
            continue
        setup_name, signal = hit
        last_ts = state.last_eligible.get(setup_name)
        if last_ts == ts:
            continue
        state.last_eligible[setup_name] = ts
        if i + 1 >= len(all_bars):
            continue
        state.pending = _PendingEntry(
            symbol=symbol,
            setup=setup_name,
            stop_price=float(signal.stop_price),
            target_price=float(signal.target_price),
            signal_ts=ts,
        )

    if state.open_pos is not None and trades_for_symbol < max_trades:
        last = all_bars[-1]
        close = float(last.get("c") or state.open_pos.entry_price)
        trades_out.append(_close_trade(
            state.open_pos,
            float(last.get("ts") or 0),
            close,
            "eod",
        ))


def run_backtest(
    session_date: str,
    *,
    setup: str = BACKTEST_DEFAULT_SETUP,
    symbols: list[str] | None = None,
    cold_dir: Path | None = None,
    max_symbols: int = BACKTEST_MAX_SYMBOLS,
    max_trades_per_day: int = BACKTEST_MAX_TRADES_PER_DAY,
) -> dict[str, Any]:
    """
    Run a no-hindsight backtest for one archived session day.

    Returns metrics, trades, honesty labels, and session metadata.
    """
    root = cold_dir or cold_root()
    day_dir = root / session_date / ARCHIVE_SCHEMA_VERSION
    if not day_dir.is_dir():
        return {
            "ok": False,
            "session_date": session_date,
            "error": f"missing cold day: {day_dir}",
            "trades": [],
            "metrics": score_trades([]),
            "honesty": HONESTY,
        }

    setups = _setups_to_run(setup)
    by_symbol = bars_by_symbol_for_day(session_date, cold_dir=root)
    target = [s.upper() for s in (symbols or sorted(by_symbol.keys()))][: max(1, int(max_symbols))]
    if not target:
        target = sorted(by_symbol.keys())[: max(1, int(max_symbols))]

    trades: list[dict[str, Any]] = []
    global_cap = max_trades_per_day
    for sym in target:
        remaining = max(0, global_cap - len(trades))
        if remaining <= 0:
            break
        before = len(trades)
        _simulate_symbol(sym, by_symbol.get(sym, []), session_date, setups, remaining, trades)
        logger.debug(
            "backtest %s %s: +%d trades",
            session_date, sym, len(trades) - before,
        )

    metrics = score_trades(trades)
    return {
        "ok": True,
        "session_date": session_date,
        "setup": setup,
        "symbols": target,
        "trade_count": len(trades),
        "trades": trades,
        "metrics": metrics,
        "honesty": HONESTY,
        "note": (
            "Nova-native backtest on archived 1m bars. Signals evaluated with "
            "slice_bars_as_of (no lookahead). Entries fill at next bar open; "
            "exits at stop/target/EOD. No spread/slippage modeled."
        ),
    }
