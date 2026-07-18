"""
HOD Momo debug-payload builders — pure functions, no module state.

Split out of hod_momo.py (backend-modularity rule). These format the live
engine state (ticker snapshots, gate counters, decision history) into the
dicts served by the /api/hod-momo/debug/* endpoints. hod_momo.py's own
get_debug_* wrappers gather the current global state and delegate here.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from hod_momo_models import TickerSnap


def build_debug_counters(
    total_trades_seen: int,
    ticker_snaps: dict[str, TickerSnap],
    gate_counters: dict[str, int],
    session_highs: dict[str, float],
    fundamentals_queue: "deque[str]",
    pending_consolidation: dict[str, list],
    today_alerts: list,
) -> dict:
    snaps_populated = sum(
        1 for s in ticker_snaps.values()
        if s.rvol is not None or s.change_pct is not None
    )
    return {
        "total_trades_seen": total_trades_seen,
        "universe_size": len(ticker_snaps),
        "snaps_populated": snaps_populated,
        "counters": dict(gate_counters),
        "session_highs_tracked": len(session_highs),
        "fundamentals_queue_depth": len(fundamentals_queue),
        "pending_symbols": len(pending_consolidation),
        "alerts_today": len(today_alerts),
    }


def build_debug_symbol(
    symbol: str,
    snap: TickerSnap | None,
    decisions: list[dict],
    session_high: float | None,
    would_fire_now: dict | None,
) -> dict:
    return {
        "symbol": symbol,
        "snap": {
            "price": snap.price if snap else None,
            "rvol": snap.rvol if snap else None,
            "float_shares": snap.float_shares if snap else None,
            "gap_pct": snap.gap_pct if snap else None,
            "change_pct": snap.change_pct if snap else None,
            "volume": snap.volume if snap else None,
            "avg_volume": snap.avg_volume if snap else None,
            "fifty_two_week_high": snap.fifty_two_week_high if snap else None,
            "rvol_source": snap.rvol_source if snap else None,
            "last_enriched": snap.last_enriched if snap else 0.0,
        },
        "session_high": session_high,
        "decisions": decisions,
        "would_fire_now": would_fire_now,
    }


def build_debug_recent(records: list[Any], limit: int = 100) -> list[dict]:
    subset = list(records)[-limit:]
    return [
        {
            "ts": r.ts,
            "symbol": r.symbol,
            "price": r.price,
            "rvol": r.snap.get("rvol"),
            "gap_pct": r.snap.get("gap_pct"),
            "change_pct": r.snap.get("change_pct"),
            "gate_blocked": r.gate_blocked,
            "strategies_fired": [d["id"] for d in r.strategies if d.get("passed")],
            "would_fire": r.would_fire,
        }
        for r in subset
    ]


def build_debug_snaps(ticker_snaps: dict[str, TickerSnap], limit: int = 50) -> list[dict]:
    """Return top-N snapshots sorted by recency of enrichment."""
    enriched = [
        (sym, snap) for sym, snap in ticker_snaps.items()
        if snap.rvol is not None or snap.change_pct is not None
    ]
    enriched.sort(key=lambda x: x[1].last_enriched, reverse=True)
    return [
        {
            "symbol": sym,
            "price": snap.price,
            "rvol": snap.rvol,
            "float_shares": snap.float_shares,
            "gap_pct": snap.gap_pct,
            "change_pct": snap.change_pct,
            "volume": snap.volume,
            "avg_volume": snap.avg_volume,
            "rvol_source": snap.rvol_source,
            "last_enriched": snap.last_enriched,
        }
        for sym, snap in enriched[:limit]
    ]
