"""
Journal metrics: win rate, avg win/loss, profit/loss ratio, and the
go/no-go bar from the automation plan's Phase 4 live-money gate
(see knowledge/obsidian/03-Nova-Decisions/Automation-Strategy-Backbone.md #5).

Reports "insufficient data" honestly when the trades table is empty or below
the minimum sample size, rather than fabricating a rate from zero trades.
Phase D (paper execution) is what populates the trades table this reads from.
"""
from __future__ import annotations

from constants import (
    JOURNAL_MIN_ADHERENCE_PCT_FOR_GO_LIVE,
    JOURNAL_MIN_TRADES_FOR_GO_LIVE,
    RISK_TARGET_PROFIT_LOSS_RATIO,
)
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
        "go_no_go": _go_no_go(total, profit_loss_ratio, adherence_pct),
    }


def _go_no_go(total: int, profit_loss_ratio: float | None, adherence_pct: float | None) -> dict:
    """Three criteria from the plan's live-money gate. Each is `met: None`
    (pending, not failing) until there's enough data to judge it."""
    sample_met = total >= JOURNAL_MIN_TRADES_FOR_GO_LIVE
    ratio_met = None if profit_loss_ratio is None else profit_loss_ratio >= RISK_TARGET_PROFIT_LOSS_RATIO
    adherence_met = (
        None if adherence_pct is None
        else adherence_pct >= JOURNAL_MIN_ADHERENCE_PCT_FOR_GO_LIVE
    )

    criteria = {
        "min_sample_size": {
            "met": sample_met,
            "label": f">= {JOURNAL_MIN_TRADES_FOR_GO_LIVE} closed trades",
            "value": total,
        },
        "profit_loss_ratio": {
            "met": ratio_met,
            "label": f">= {RISK_TARGET_PROFIT_LOSS_RATIO:.0f}:1 profit/loss ratio",
            "value": profit_loss_ratio,
        },
        "adherence": {
            "met": adherence_met,
            "label": (
                f">= {JOURNAL_MIN_ADHERENCE_PCT_FOR_GO_LIVE:.0f}% of trades "
                "within risk rules (adherent)"
            ),
            "value": adherence_pct,
        },
    }
    overall = sample_met and ratio_met is True and adherence_met is True
    return {"overall_go": overall, "criteria": criteria}
