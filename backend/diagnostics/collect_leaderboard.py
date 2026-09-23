"""Diagnostics rows for the always-on scanner recorder and auto-record (ADR 022)."""
from __future__ import annotations

from typing import Any

from constants_diagnostics import (
    DIAG_GROUP_RECORDER,
    DIAG_STATE_FAIL,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_WARN,
)
from diagnostics.rows import row


def leaderboard_rows(*, recorder: dict[str, Any], auto: dict[str, Any], store_path: str) -> list[dict[str, Any]]:
    if not recorder.get("ok", True):
        state, detail = DIAG_STATE_FAIL, f"cannot write the scanner board: {recorder.get('error')}"
        cause = "The leaderboard store refused a write; those minutes are lost, and playback shows them as a gap."
        fix = f"Check the drive holding {store_path} (mounted, space, permissions); writes resume on their own."
    elif recorder.get("recording"):
        state, detail = DIAG_STATE_OK, "recording every scanner board once a minute"
        cause, fix = "Always on, 04:00-20:00 ET on exchange days.", "Nothing to do."
    elif recorder.get("run_id"):
        state, detail = DIAG_STATE_OFF, "outside 04:00-20:00 ET or not an exchange day"
        cause, fix = "The recorder is running and waits for the session.", "Nothing to do."
    else:
        state, detail = DIAG_STATE_WARN, "the recorder loop has not started"
        cause, fix = "The backend started without the leaderboard loop.", "Restart the backend."
    rows = [row(
        id="leaderboard_recorder",
        group=DIAG_GROUP_RECORDER,
        title="Scanner board recorder",
        state=state,
        detail=detail,
        cause=cause,
        fix=fix,
        since=recorder.get("since"),
        evidence={**recorder, "store": store_path},
    )]
    symbols = list(auto.get("symbols") or [])
    if auto.get("last_error"):
        a_state, a_detail = DIAG_STATE_WARN, f"last problem: {auto['last_error']}"
    elif auto.get("active"):
        a_state = DIAG_STATE_OK
        a_detail = f"recording {', '.join(symbols)}" if symbols else "watching the leaders; no free Level 2 line or no leader yet"
    else:
        a_state, a_detail = DIAG_STATE_OFF, f"outside {auto.get('window') or 'its window'}"
    rows.append(row(
        id="auto_record",
        group=DIAG_GROUP_RECORDER,
        title="Auto-record (leaders)",
        state=a_state,
        detail=a_detail,
        cause="Records the top leaders on free Level 2 lines only; yields a line when you open Level 2.",
        fix="Nothing to do." if a_state != DIAG_STATE_WARN else "It retries on its own; Record by hand if a leader matters now.",
        evidence=dict(auto),
    ))
    return rows
