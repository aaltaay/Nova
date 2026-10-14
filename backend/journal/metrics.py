"""Journal statistics for the operator to interpret, never a trading-readiness verdict (#791)."""
from __future__ import annotations

from journal.store import get_closed_trades


def compute_metrics(include_mock: bool = False) -> dict:
    trades = get_closed_trades(include_mock=include_mock)
    total = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]

    win_rate = (len(wins) / total * 100.0) if total else None
    avg_win = (sum(t["pnl"] for t in wins) / len(wins)) if wins else None
    avg_loss = (sum(-t["pnl"] for t in losses) / len(losses)) if losses else None
    profit_loss_ratio = (avg_win / avg_loss) if (avg_win and avg_loss) else None
    total_pnl = sum(t["pnl"] for t in trades) if trades else None

    adherent_flags = [t["adherent"] for t in trades if t["adherent"] is not None]
    adherence_pct = (sum(adherent_flags) / len(adherent_flags) * 100.0) if adherent_flags else None

    return {
        "includes_mock_data": include_mock,
        "total_closed_trades": total,
        "win_rate_pct": None if win_rate is None else round(win_rate, 1),
        "avg_win_dollars": None if avg_win is None else round(avg_win, 2),
        "avg_loss_dollars": None if avg_loss is None else round(avg_loss, 2),
        "profit_loss_ratio": None if profit_loss_ratio is None else round(profit_loss_ratio, 2),
        "total_pnl_dollars": None if total_pnl is None else round(total_pnl, 2),
        "adherence_pct": None if adherence_pct is None else round(adherence_pct, 1),
    }
