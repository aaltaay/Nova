"""When a queued HOD Momo alert is due: a burst's first trigger at once, its repeats at the burst's end.

One rule for the live flush loop (``hod_momo_alerts``) and the replay (``hod_momo_replay``): ``queue_alert`` sets
when each ``pending_consolidation`` entry is due, ``take_due`` hands both of them the rows whose time has come. The repeats still fold into one row per strategy
("N in Xs"); the desk adds that row to the first one (``collapseAlertsBySymbol``), so the count is unchanged.
"""
from __future__ import annotations

from typing import Any


def queue_alert(state: Any, symbol: str, alert: Any, now_ts: float, due: float | None = None) -> float:
    """Queue ``alert`` and return when it is due (unix seconds).

    A trigger outside the symbol's open burst starts one and is due now; a trigger inside it waits for the
    burst's end, the first trigger plus ``master.consolidation_sec``. The other strategies of one evaluation
    pass the first one's ``due`` and go out with it. (Equal clock readings are not one evaluation: a replay's
    clock is the print's second, which many prints share.)
    """
    if due is None:
        window = max(0.0, float(state.master.consolidation_sec or 0.0))
        burst = state.consolidation_bursts.get(symbol)
        if burst is None or now_ts >= burst[1]:
            state.consolidation_bursts[symbol] = (now_ts, now_ts + window)
            due = now_ts
        else:
            due = burst[1]
    state.pending_consolidation.setdefault(symbol, []).append((due, alert))
    return due


def take_due(state: Any, now_ts: float) -> list[Any]:
    """Remove the queued alerts due by ``now_ts`` and return one row per symbol and strategy, oldest symbol first.

    A strategy's due alerts fold into its last one: ``consolidation_count`` alerts over ``consolidation_span_sec``
    ("N in Xs"), the earlier ones' ids in ``consolidated_ids``. A lone alert goes out as it is.
    """
    out: list[Any] = []
    for symbol in list(state.pending_consolidation.keys()):
        bucket = state.pending_consolidation[symbol]
        ready = [alert for due, alert in bucket if now_ts >= due]
        state.pending_consolidation[symbol] = [(due, alert) for due, alert in bucket if now_ts < due]
        by_strategy: dict[int, list[Any]] = {}
        for alert in ready:
            by_strategy.setdefault(int(alert.strategy_id), []).append(alert)
        for group in by_strategy.values():
            primary = group[-1]
            if len(group) > 1:
                primary.consolidation_count = len(group)
                primary.consolidated_ids = [alert.id for alert in group[:-1]]
                first_ts = min((alert.created_ts or 0.0) for alert in group) or now_ts
                last_ts = max((alert.created_ts or 0.0) for alert in group) or now_ts
                span = int(round(max(0.0, last_ts - first_ts)))
                primary.consolidation_span_sec = max(1, span) if span > 0 else 1
            out.append(primary)
    return out
