"""
Setup aggregator — evaluates all three setup patterns for one candidate and
reports which (if any) are eligible right now. Signal-only, no orders.

Used by:
  - GET /api/strategy/setups/{symbol}  (on-demand, one symbol)
  - setups_stream.py's background scan loop (periodic, whole watchlist)
"""

from __future__ import annotations

from strategy.abcd import evaluate_abcd
from strategy.bull_flag import evaluate_bull_flag
from strategy.gap_and_go import evaluate_gap_and_go

SETUP_NAMES: tuple[str, ...] = ("gap_and_go", "bull_flag", "abcd")


def evaluate_setups(candidate: dict, bars: list[dict]) -> dict:
    """Evaluate Gap and Go, Bull Flag, and ABCD for one candidate.

    Returns a dict keyed by setup name plus an `eligible_setups` list of the
    names currently eligible (all pillars pass + pattern present + triggered).
    """
    signals = {
        "gap_and_go": evaluate_gap_and_go(candidate, bars),
        "bull_flag": evaluate_bull_flag(candidate, bars),
        "abcd": evaluate_abcd(candidate, bars),
    }
    eligible_setups = [name for name, signal in signals.items() if signal.eligible]
    return {
        "symbol": candidate.get("symbol", "?"),
        "eligible_setups": eligible_setups,
        "any_eligible": bool(eligible_setups),
        **{name: signal.to_dict() for name, signal in signals.items()},
    }
