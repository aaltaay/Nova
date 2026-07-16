"""
Pure metrics from a list of closed synthetic trades.

No I/O, no vectorbt — used by Phase E backtest engine and routes.
"""
from __future__ import annotations

from typing import Any, TypedDict


class EquityPoint(TypedDict):
    trade_index: int
    cumulative_pnl: float
    cumulative_r: float


class TradeMetrics(TypedDict):
    trade_count: int
    win_rate: float | None
    profit_factor: float | None
    avg_win: float | None
    avg_loss: float | None
    max_drawdown_pct: float | None
    total_pnl_dollars: float
    total_pnl_r: float
    equity_curve: list[EquityPoint]


def _pnl_dollars(trade: dict[str, Any]) -> float:
    return float(trade.get("pnl_dollars") or 0.0)


def _pnl_r(trade: dict[str, Any]) -> float:
    return float(trade.get("pnl_r") or 0.0)


def _max_drawdown_pct(equity: list[float]) -> float | None:
    if len(equity) < 2:
        return 0.0 if equity else None
    peak = equity[0]
    max_dd = 0.0
    for val in equity:
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak * 100.0
            max_dd = max(max_dd, dd)
        elif peak < 0 and val < peak:
            max_dd = max(max_dd, abs(val - peak))
    return round(max_dd, 4)


def score_trades(trades: list[dict[str, Any]]) -> TradeMetrics:
    """Compute win rate, profit factor, averages, max drawdown, equity curve."""
    if not trades:
        return {
            "trade_count": 0,
            "win_rate": None,
            "profit_factor": None,
            "avg_win": None,
            "avg_loss": None,
            "max_drawdown_pct": None,
            "total_pnl_dollars": 0.0,
            "total_pnl_r": 0.0,
            "equity_curve": [],
        }

    pnls = [_pnl_dollars(t) for t in trades]
    rs = [_pnl_r(t) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    equity_dollars: list[float] = []
    equity_rs: list[float] = []
    curve: list[EquityPoint] = []
    cum_d = 0.0
    cum_r = 0.0
    for i, trade in enumerate(trades):
        cum_d += _pnl_dollars(trade)
        cum_r += _pnl_r(trade)
        equity_dollars.append(cum_d)
        equity_rs.append(cum_r)
        curve.append({
            "trade_index": i,
            "cumulative_pnl": round(cum_d, 4),
            "cumulative_r": round(cum_r, 4),
        })

    return {
        "trade_count": len(trades),
        "win_rate": round(len(wins) / len(trades), 4) if trades else None,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss > 0 else None,
        "avg_win": round(sum(wins) / len(wins), 4) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 4) if losses else None,
        "max_drawdown_pct": _max_drawdown_pct(equity_dollars),
        "total_pnl_dollars": round(sum(pnls), 4),
        "total_pnl_r": round(sum(rs), 4),
        "equity_curve": curve,
    }
