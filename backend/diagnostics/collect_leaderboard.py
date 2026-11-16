"""Diagnostics rows for the always-on scanner recorder (ADR 023) and the three lanes (ADR 071).

#485 (operator decision 2026-09-24): the leaderboard keeps every day, so the
recorder row also guards its drive. ``disk`` is ``{store_bytes, free_bytes,
size_error, free_error}``, read by the shell (``diagnostics.gather``) on its
worker thread. Low free space warns or fails the row; a size or free space
that cannot be read is ``unknown`` with the reason, never ``ok``. The drive's
verdict only ever makes the row worse.
"""
from __future__ import annotations

import ntpath
import os
from typing import Any

from constants_diagnostics import (
    DIAG_GROUP_RECORDER,
    DIAG_STATE_FAIL,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_UNKNOWN,
    DIAG_STATE_WARN,
)
from constants_leaderboard import (
    LEADERBOARD_DIR_ENV,
    LEADERBOARD_FREE_FAIL_BYTES,
    LEADERBOARD_FREE_WARN_BYTES,
    LEADERBOARD_GROWTH_PER_YEAR,
)
from diagnostics.rows import row

# How bad a state is, for "the drive only makes the row worse". Off is a quiet
# state, not a problem; unknown is below a known warning.
_SEVERITY = {DIAG_STATE_OK: 0, DIAG_STATE_OFF: 0, DIAG_STATE_UNKNOWN: 1, DIAG_STATE_WARN: 2, DIAG_STATE_FAIL: 3}


def _gb(n: int) -> str:
    """Sizes as Windows Explorer shows them (1024-based, labelled GB / MB)."""
    value = n / 1024**3
    if value < 1:
        return f"{n / 1024**2:.0f} MB"
    return f"{value:.1f} GB" if value < 10 else f"{value:.0f} GB"


def _volume(store_path: str) -> str:
    """``F:`` for a Windows path, else the folder that holds the store."""
    return ntpath.splitdrive(store_path)[0] or f"the drive holding {os.path.dirname(store_path) or store_path}"


def _disk_verdict(disk: dict[str, Any], store_path: str) -> tuple[str, str, str, str]:
    """``(state, detail, cause, fix)`` for the store's drive."""
    where = _volume(store_path)
    free, size = disk.get("free_bytes"), disk.get("store_bytes")
    keeps = f"The leaderboard keeps every day (no automatic deletion, #485); it adds {LEADERBOARD_GROWTH_PER_YEAR}."
    move = f"Free space on {where}, or move {LEADERBOARD_DIR_ENV} to a larger drive and restart the backend."
    store = f"; the store is {_gb(size)}" if size is not None else ""
    if free is None:
        why = disk.get("free_error") or "not read"
        return (DIAG_STATE_UNKNOWN, f"Unknown: free space on {where} ({why})",
                f"Nova could not read the free space on {where}, so a filling drive would go unseen: {why}.",
                f"Check that the drive holding {store_path} is mounted and readable.")
    if free < LEADERBOARD_FREE_FAIL_BYTES:
        return (DIAG_STATE_FAIL, f"{where} has {_gb(free)} free (fails under {_gb(LEADERBOARD_FREE_FAIL_BYTES)}){store}",
                f"{keeps} With this little room the next writes can fail, and those minutes are lost.", move)
    if free < LEADERBOARD_FREE_WARN_BYTES:
        return (DIAG_STATE_WARN, f"{where} has {_gb(free)} free (warns under {_gb(LEADERBOARD_FREE_WARN_BYTES)}){store}",
                keeps, move)
    if size is None:
        why = disk.get("size_error") or "not read"
        return (DIAG_STATE_UNKNOWN, f"Unknown: the size of {store_path} ({why})",
                f"Nova could not read the leaderboard store's size: {why}.",
                f"Check that {store_path} is readable.")
    return DIAG_STATE_OK, f"{where} has {_gb(free)} free{store}", keeps, "Nothing to do."


def _disk_error(disk: dict[str, Any]) -> str | None:
    errors = [str(e) for e in (disk.get("size_error"), disk.get("free_error")) if e]
    return "; ".join(errors) or None


def leaderboard_rows(
    *, recorder: dict[str, Any], lanes: dict[str, Any] | None, switch: dict[str, Any] | None, store_path: str,
    disk: dict[str, Any],
) -> list[dict[str, Any]]:
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
    d_state, d_detail, d_cause, d_fix = _disk_verdict(disk, store_path)
    if _SEVERITY[d_state] > _SEVERITY[state]:
        state, detail, cause, fix = d_state, f"{d_detail} -- {detail}", d_cause, d_fix
    elif d_state != DIAG_STATE_OK:
        detail = f"{detail} -- {d_detail}"
    rows = [row(
        id="leaderboard_recorder",
        group=DIAG_GROUP_RECORDER,
        title="Scanner board recorder",
        state=state,
        detail=detail,
        cause=cause,
        fix=fix,
        since=recorder.get("since"),
        evidence={**recorder, "store": store_path, "store_bytes": disk.get("store_bytes"),
                  "free_bytes": disk.get("free_bytes"), "disk_error": _disk_error(disk)},
    )]
    rows.append(_lanes_row(lanes, switch))
    return rows


_OWNERS = (("you", "yours"), ("claude", "Claude's"), ("bots", "the bots'"))


def _lanes_row(lanes: dict[str, Any] | None, switch: dict[str, Any] | None) -> dict[str, Any]:
    """Which stock each lane is on, whether its lines are up, and what Nova records (ADR 071)."""
    if not lanes:
        return row(id="lanes", group=DIAG_GROUP_RECORDER, title="Level 2 lanes and recording",
                   state=DIAG_STATE_UNKNOWN, detail="the lanes could not be read",
                   cause="The lanes' status raised; the backend log has the error.", fix="Restart the backend.",
                   evidence={})
    parts, problems = [], []
    for key, word in _OWNERS:
        lane = lanes.get(key) or {}
        sym = lane.get("symbol")
        if not sym:
            parts.append(f"{word} empty")
            continue
        up = lane.get("depth") and lane.get("tape")
        parts.append(f"{word} on {sym}{'' if up else ' (asking IBKR)'}{', recording' if lane.get('recording') else ''}")
        if lane.get("error"):
            problems.append(f"{sym}: {lane['error']}")
    for why in ((lanes.get("bots") or {}).get("error"), lanes.get("recording_error")):
        if why:
            problems.append(str(why))
    detail = "; ".join(parts)
    if problems:
        state, detail = DIAG_STATE_WARN, f"{detail} -- {'; '.join(problems)}"
    elif (switch or {}).get("mode") in ("off", "off_today"):
        state, detail = DIAG_STATE_OFF, f"{detail} -- recording {_switched_off(switch or {})}"
    else:
        state = DIAG_STATE_OK
    return row(
        id="lanes",
        group=DIAG_GROUP_RECORDER,
        title="Level 2 lanes and recording",
        state=state,
        detail=detail,
        cause=("Three lanes hold Level 2 and Time & Sales: yours, Claude's and the bots' (one setup a bot may buy). "
               "Nova records only what a lane watches (ADR 071)."),
        fix="Nothing to do." if state != DIAG_STATE_WARN else "Each lane asks IBKR again on its own every 15 s.",
        evidence={"lanes": lanes, "switch": switch},
    )


def _switched_off(switch: dict[str, Any]) -> str:
    """Who turned recording off (operator ask 2026-10-14): the switch on Records, or ``.env``."""
    if switch.get("source") == "env":
        return "off: NOVA_AUTO_RECORD=0 in .env"
    if switch.get("mode") == "off_today":
        return "off for today on Records; back on at 04:00 ET"
    return "turned off on Records"
