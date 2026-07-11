"""
Joins recorded L2 snapshots (l2/store.py) against journal trade outcomes
(journal/store.py) to build the "what did good tape look like vs bad tape"
dataset described in the plan. Read-only -- computes labels in memory, never
writes back to either table. This is the dataset a future rules-based
heuristic or learned model would need before it could ever be trusted; see
Automation-Strategy-Backbone.md section 3 for why tape-based exits stay out
of the executor until then.
"""
from __future__ import annotations

from constants import L2_LABEL_MATCH_TOLERANCE_SEC
from journal.store import get_closed_trades
from l2.features import compute_feature_series
from l2.store import get_recording_ids, get_snapshots


def _find_matching_trade(recording: dict, trades: list[dict]) -> dict | None:
    """Closest closed trade for the same symbol+setup within
    L2_LABEL_MATCH_TOLERANCE_SEC of the recording's signal_ts."""
    candidates = [
        t for t in trades
        if t["symbol"] == recording["symbol"]
        and (t.get("setup") or "") == recording["setup"]
        and abs(t["opened_ts"] - recording["signal_ts"]) <= L2_LABEL_MATCH_TOLERANCE_SEC
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda t: abs(t["opened_ts"] - recording["signal_ts"]))


def label_recordings(include_mock: bool = False) -> list[dict]:
    """One entry per recording: {recording_id, symbol, setup, signal_ts,
    snapshot_count, outcome, pnl, feature_series}. outcome is
    "win" | "loss" | "unlabeled" (no matching closed trade found yet)."""
    trades = get_closed_trades(include_mock=include_mock)
    out = []
    for recording in get_recording_ids():
        match = _find_matching_trade(recording, trades)
        snapshots = get_snapshots(recording["recording_id"])
        if match is None:
            outcome, pnl = "unlabeled", None
        else:
            pnl = match["pnl"]
            outcome = "win" if pnl is not None and pnl > 0 else "loss"
        out.append({
            **recording,
            "outcome": outcome,
            "pnl": pnl,
            "feature_series": compute_feature_series(snapshots),
        })
    return out
