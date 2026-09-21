"""
Point-in-time recall: "what did L2 / tape look like for symbol at second T?"

Pure read helpers used by GET /api/l2/at and GET /api/l2/range. No UI.
Future backtests should call these (or the same store range queries) rather
than inventing a second reader.
"""
from __future__ import annotations

from constants import L2_RECALL_DEFAULT_WINDOW_SEC
from l2 import sessions as _sessions
from l2 import tape as _tape
from l2.store import get_nearest_snapshot, get_snapshot_before, get_snapshots_in_range


def recall_at(
    symbol: str,
    ts: float,
    window_sec: float | None = None,
) -> dict:
    """Nearest L2 snapshot + tape prints in ±window around ts."""
    window = L2_RECALL_DEFAULT_WINDOW_SEC if window_sec is None else window_sec
    sym = symbol.upper()
    start_ts = ts - window
    end_ts = ts + window
    nearest = get_nearest_snapshot(sym, ts, window)
    trades = _tape.get_trades_in_range(sym, start_ts, end_ts)
    session = _sessions.session_covering(sym, ts)
    return {
        "symbol": sym,
        "ts": ts,
        "window_sec": window,
        "l2": nearest,
        "tape": trades,
        "tape_count": len(trades),
        "session": session,
    }


def book_before(
    symbol: str,
    ts: float,
    max_age_sec: float | None = None,
) -> dict | None:
    """The recorded book as of ``ts``, or ``None`` when none covers it.

    ``recall_at`` answers "what was around second T" with a symmetric window,
    which is the right shape for feature work and the wrong shape for replay:
    a ±window can return a book recorded after the playhead. This is the
    no-lookahead sibling, used by the Sim historical replay depth feeder
    (``sim/history_depth.py``, #309). Tape and session metadata are left out
    on purpose -- the replay owns its own tape.
    """
    window = L2_RECALL_DEFAULT_WINDOW_SEC if max_age_sec is None else max_age_sec
    row = get_snapshot_before(symbol, ts, window)
    if row is None:
        return None
    return {
        "symbol": row["symbol"],
        "ts": row["ts"],
        "bids": row["bids"],
        "asks": row["asks"],
        "l1_fallback": row["l1_fallback"],
        "session_id": row.get("session_id"),
    }


def recall_range(symbol: str, start_ts: float, end_ts: float) -> dict:
    """All L2 snapshots + tape prints in [start_ts, end_ts]."""
    sym = symbol.upper()
    snapshots = get_snapshots_in_range(sym, start_ts, end_ts)
    trades = _tape.get_trades_in_range(sym, start_ts, end_ts)
    return {
        "symbol": sym,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "l2": snapshots,
        "l2_count": len(snapshots),
        "tape": trades,
        "tape_count": len(trades),
    }
