"""
Level 2 recording routes (Phase F) -- READ-ONLY. No route here places,
modifies, or cancels an order, or subscribes/unsubscribes depth. Recordings
start automatically from setups_stream.py when a signal fires; see
backend/l2/recorder.py, features.py, labeling.py.

Endpoints:
  GET /api/l2/recordings -- one row per recording with its win/loss/unlabeled
                             outcome and per-snapshot tape feature series
"""
from __future__ import annotations

from fastapi import APIRouter

from l2.labeling import label_recordings

router = APIRouter(prefix="/api/l2", tags=["l2"])


@router.get("/recordings")
def l2_recordings(include_mock: bool = False) -> dict:
    rows = label_recordings(include_mock=include_mock)
    return {"count": len(rows), "recordings": rows}
