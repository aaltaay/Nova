"""The operator's focus (ADR 031): each desk window's report, joined into one answer.

Owner: this module's in-memory state -- the newest report per renderer window
(keyed by its ``instance_id``, one per page load) and the Electron main
process's report (which window Windows has in front, and each window's
monitor). Invalidation: a report older than ``FOCUS_STALE_SEC`` is ignored and
one older than ``FOCUS_FORGET_SEC`` dropped; a restart forgets everything. Not
persisted; the wire's schema_version is ``FOCUS_SCHEMA_VERSION``.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from constants_sensors import FOCUS_FORGET_SEC, FOCUS_RECENT_KEEP, FOCUS_STALE_SEC

_lock = threading.Lock()
_windows: dict[str, dict[str, Any]] = {}
_electron: dict[str, Any] | None = None
_recent: deque[dict[str, Any]] = deque(maxlen=FOCUS_RECENT_KEEP)


def reset_for_tests() -> None:
    global _electron
    with _lock:
        _windows.clear()
        _electron = None
        _recent.clear()


def _view(report: dict[str, Any]) -> tuple:
    return report.get("page"), report.get("tab"), report.get("symbol")


def record_window(report: dict[str, Any], *, now: float | None = None) -> None:
    """One renderer window's report (already validated)."""
    now = time.time() if now is None else now
    key = str(report["instance_id"])
    with _lock:
        prev = _windows.get(key)
        changed = prev is None or _view(prev) != _view(report) or prev.get("window_id") != report.get("window_id")
        flipped = prev is None or bool(prev.get("focused")) != bool(report.get("focused"))
        row = dict(report)
        row["received_ts"] = now
        row["since"] = now if changed else prev["since"]
        row["last_focused_ts"] = now if report.get("focused") else (prev or {}).get("last_focused_ts")
        _windows[key] = row
        if changed or (flipped and report.get("focused")):
            _recent.appendleft({"ts": now, "window_id": row.get("window_id"), "page": row.get("page"),
                                "tab": row.get("tab"), "symbol": row.get("symbol"),
                                "focused": bool(row.get("focused")), "reason": row.get("reason")})
        for other, old in list(_windows.items()):
            if now - old["received_ts"] > FOCUS_FORGET_SEC:
                del _windows[other]


def record_electron(report: dict[str, Any], *, now: float | None = None) -> None:
    """The Electron main process's report: OS focus and each window's monitor."""
    global _electron
    now = time.time() if now is None else now
    with _lock:
        _electron = dict(report, received_ts=now)


def _fresh(row: dict[str, Any] | None, now: float) -> bool:
    return row is not None and now - float(row["received_ts"]) <= FOCUS_STALE_SEC


def _pick(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(rows, key=lambda r: r["received_ts"]) if rows else None


def resolve(now: float | None = None) -> dict[str, Any]:
    """The answer to "what is the operator looking at?" -- stated, never guessed."""
    now = time.time() if now is None else now
    with _lock:
        windows = [dict(w) for w in _windows.values() if _fresh(w, now)]
        electron = dict(_electron) if _fresh(_electron, now) else None
        recent = list(_recent)
    by_id = {r["window_id"]: r for r in (electron or {}).get("windows") or []}
    for w in windows:
        os_row = by_id.get(w.get("window_id")) or {}
        w["display"] = os_row.get("display")
        w["minimized"] = os_row.get("minimized")
        if electron is not None and w.get("window_id") in by_id:
            w["focused"] = bool(os_row.get("focused"))
    if electron is not None:
        source = "electron"
        in_front = bool(electron.get("app_focused"))
        current = _pick([w for w in windows if w.get("window_id") == electron.get("focused_window_id")])
    elif windows:
        source = "window"
        focused = [w for w in windows if w.get("focused")]
        in_front = bool(focused)
        current = _pick(focused)
    else:
        source, in_front, current = None, None, None
    if current is None and windows:
        # Nova is not in front: the window the operator was in last.
        current = max(windows, key=lambda w: (w.get("last_focused_ts") or 0.0, w["received_ts"]))
    last_input = (current or {}).get("last_input_ts")
    return {
        "nova_in_front": in_front,
        "focus_source": source,
        "symbol": (current or {}).get("symbol"),
        "page": (current or {}).get("page"),
        "tab": (current or {}).get("tab"),
        "symbol_source": (current or {}).get("symbol_source"),
        "window_id": (current or {}).get("window_id"),
        "role": (current or {}).get("role"),
        "display": (current or {}).get("display"),
        "since": (current or {}).get("since"),
        "last_input_ts": last_input,
        "last_input_age_sec": None if last_input is None else round(max(0.0, now - float(last_input)), 1),
        "windows": [_public(w, now) for w in sorted(windows, key=lambda w: str(w.get("window_id")))],
        "recent": recent,
    }


def _public(w: dict[str, Any], now: float) -> dict[str, Any]:
    keys = ("window_id", "instance_id", "role", "focused", "visible", "minimized", "page", "tab", "symbol",
            "symbol_source", "trader_tabs", "display", "last_input_ts", "ui_tag")
    row = {k: w.get(k) for k in keys}
    row["reported_ts"] = w["received_ts"]
    row["age_sec"] = round(now - w["received_ts"], 1)
    return row
