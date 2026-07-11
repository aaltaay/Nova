"""
Level 2 / tape recording routes — READ-ONLY for trading.

Recordings start from:
  - setups_stream.py → l2.recorder.on_signal (signal windows)
  - routes/trading.py depth subscribe → l2.continuous (ticker open)

Endpoints:
  GET /api/l2/recordings          -- labeled Phase F recordings + feature series
  GET /api/l2/sessions            -- recent record_sessions metadata
  GET /api/l2/at                  -- point-in-time L2 + tape around timestamp T
  GET /api/l2/range               -- L2 + tape in [start_ts, end_ts]
  GET /api/l2/status              -- active continuous / signal recorders
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from constants import L2_RECALL_DEFAULT_WINDOW_SEC
from l2 import continuous as _continuous
from l2 import recorder as _recorder
from l2 import sessions as _sessions
from l2 import tape as _tape
from l2.labeling import label_recordings
from l2.recall import recall_at, recall_range

router = APIRouter(prefix="/api/l2", tags=["l2"])


@router.get("/recordings")
def l2_recordings(include_mock: bool = False) -> dict:
    rows = label_recordings(include_mock=include_mock)
    return {"count": len(rows), "recordings": rows}


@router.get("/sessions")
def l2_sessions(symbol: str | None = None, limit: int = 100) -> dict:
    rows = _sessions.get_sessions(symbol=symbol, limit=limit)
    return {"count": len(rows), "sessions": rows}


@router.get("/at")
def l2_at(
    symbol: str = Query(..., min_length=1),
    ts: float = Query(..., description="Unix epoch seconds (wall clock)"),
    window_sec: float = Query(L2_RECALL_DEFAULT_WINDOW_SEC, gt=0),
) -> dict:
    """Answer: with ticker X open, what did L2 / tape look like at second T?"""
    return recall_at(symbol, ts, window_sec=window_sec)


@router.get("/range")
def l2_range(
    symbol: str = Query(..., min_length=1),
    start_ts: float = Query(...),
    end_ts: float = Query(...),
) -> dict:
    return recall_range(symbol, start_ts, end_ts)


@router.get("/status")
def l2_status() -> dict:
    return {
        "continuous_symbols": _continuous.active_symbols(),
        "signal_recording_symbols": sorted(_recorder._active_recordings),
        "tape_watched_symbols": _tape.watched_symbols(),
    }
