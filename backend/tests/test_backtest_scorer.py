"""Unit tests for backtest.scorer — pure metrics, no I/O."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest.scorer import score_trades


def _trade(pnl: float, pnl_r: float | None = None) -> dict:
    return {
        "pnl_dollars": pnl,
        "pnl_r": pnl_r if pnl_r is not None else pnl / 20.0,
    }


class TestScoreTradesEmpty:
    def test_empty_returns_none_metrics(self):
        m = score_trades([])
        assert m["trade_count"] == 0
        assert m["win_rate"] is None
        assert m["profit_factor"] is None
        assert m["avg_win"] is None
        assert m["avg_loss"] is None
        assert m["max_drawdown_pct"] is None
        assert m["equity_curve"] == []


class TestScoreTradesMetrics:
    def test_win_rate_and_profit_factor(self):
        trades = [_trade(20), _trade(-10), _trade(30), _trade(-10)]
        m = score_trades(trades)
        assert m["trade_count"] == 4
        assert m["win_rate"] == 0.5
        assert m["profit_factor"] == 2.5  # 50 gross / 20 loss
        assert m["avg_win"] == 25.0
        assert m["avg_loss"] == -10.0
        assert m["total_pnl_dollars"] == 30.0

    def test_equity_curve_length(self):
        trades = [_trade(10), _trade(-5), _trade(15)]
        m = score_trades(trades)
        assert len(m["equity_curve"]) == 3
        assert m["equity_curve"][-1]["cumulative_pnl"] == 20.0

    def test_max_drawdown_positive_equity(self):
        trades = [_trade(100), _trade(-50), _trade(25)]
        m = score_trades(trades)
        assert m["max_drawdown_pct"] is not None
        assert m["max_drawdown_pct"] > 0
