"""The history route's answer for a day Nova kept no HOD Momo record of: the rebuilt alerts, or where the rebuild is.

A ready, current build's alerts are read once per file (held by its modification time) and served as the history
route serves recorded ones; anything else serves no alerts and says why in ``rebuild``.
"""
from __future__ import annotations

import threading
from typing import Any

from constants_hod_momo import HOD_MOMO_REBUILD_FLOAT_BASIS
from constants_leaderboard import LEADERBOARD_SECONDS_READY
from hod_momo_rebuild import job, store

_lock = threading.Lock()
_held: dict[str, tuple[float, dict[str, Any]]] = {}     # day -> (file mtime, data)

_JOB_KEYS = ("status", "reason", "stage", "done", "total", "error", "summary")


def _data(day: str) -> dict[str, Any] | None:
    path = store.data_path(day)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return None
    with _lock:
        held = _held.get(day)
        if held is not None and held[0] == mtime:
            return held[1]
    data = store.read_data(day)
    if data is not None:
        with _lock:
            _held.clear()                       # one day at a time is what the desk plays
            _held[day] = (mtime, data)
    return data


def answer(day: str) -> dict[str, Any]:
    """``{source, alerts, rebuild}`` for a day with no HOD Momo record."""
    state = job.status(day)
    rebuild = {key: state.get(key) for key in _JOB_KEYS}
    rebuild["float_basis"] = HOD_MOMO_REBUILD_FLOAT_BASIS
    if state.get("status") == LEADERBOARD_SECONDS_READY:
        data = _data(day)
        if data is not None and data.get("fingerprint") == state.get("fingerprint"):
            return {"source": "rebuilt", "alerts": list(data.get("alerts") or []), "rebuild": rebuild}
    return {"source": None, "alerts": [], "rebuild": rebuild}


def reset_for_tests() -> None:
    with _lock:
        _held.clear()
