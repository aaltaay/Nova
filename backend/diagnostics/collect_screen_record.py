"""The diagnostics row for the trading screen recording (ADR 035, ADR 067).

The screen recording is paused by default (ADR 067): a report that says
``paused`` -- or no desktop app reporting while this backend's own environment
does not turn ``NOVA_SCREEN_RECORD`` on -- is ``off``, stated with how to turn
it on, never a failure. Once it is on, the row fails whenever nothing says the
screen is recorded: no desktop app reporting (a browser desk cannot record the
screen), a report gone stale, or a report that says a monitor is not recording.
While it records it judges the drive like the leaderboard does (#485): low free
space warns or fails, and the drive's verdict only ever makes the row worse.
"""
from __future__ import annotations

import ntpath
import os
from collections.abc import Mapping
from typing import Any

from constants_diagnostics import (
    DIAG_GROUP_RECORDER,
    DIAG_STATE_FAIL,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_UNKNOWN,
    DIAG_STATE_WARN,
)
from constants_screen_record import (
    SCREEN_RECORD_DIR_ENV,
    SCREEN_RECORD_ENV,
    SCREEN_RECORD_FREE_FAIL_BYTES,
    SCREEN_RECORD_FREE_WARN_BYTES,
    SCREEN_RECORD_ON_VALUES,
    SCREEN_RECORD_STALE_SEC,
)
from diagnostics.rows import row

_SEVERITY = {DIAG_STATE_OK: 0, DIAG_STATE_OFF: 0, DIAG_STATE_UNKNOWN: 1, DIAG_STATE_WARN: 2, DIAG_STATE_FAIL: 3}
_ID = "screen_recorder"
_TITLE = "Trading screen recording"
_OPEN_APP = (f"Open Nova from the desktop app (Nova.exe): with {SCREEN_RECORD_ENV}=1 it records every monitor "
             "from launch to quit.")
_PAUSED = "screen recording is paused (off by default)"
_TURN_ON = f"Nothing to do. To record every monitor, set {SCREEN_RECORD_ENV}=1 in Nova's .env and restart Nova."


def _flag_on(environ: Mapping[str, str]) -> bool:
    """``NOVA_SCREEN_RECORD`` says yes in this backend's environment (its .env, loaded at start)."""
    return str(environ.get(SCREEN_RECORD_ENV) or "").strip().lower() in SCREEN_RECORD_ON_VALUES


def _gb(n: float) -> str:
    value = n / 1024**3
    if value < 1:
        return f"{n / 1024**2:.0f} MB"
    return f"{value:.1f} GB" if value < 10 else f"{value:.0f} GB"


def _codec(mime: str | None) -> str:
    text = (mime or "").lower()
    if "h264" in text or "avc1" in text:
        return "H.264"
    if "vp9" in text:
        return "VP9"
    if "vp8" in text:
        return "VP8"
    return mime or "video"


def _monitors(n: int) -> str:
    return "1 monitor" if n == 1 else f"{n} monitors"


def _disk_verdict(report: dict[str, Any]) -> tuple[str, str, str, str] | None:
    disk = report.get("disk") or {}
    free = disk.get("free_bytes")
    where = ntpath.splitdrive(str(report.get("dir") or ""))[0] or "the recording drive"
    keeps = "Nova keeps every recording (nothing deletes one); a trading day is a few GB to tens of GB."
    move = f"Free space on {where}, or point {SCREEN_RECORD_DIR_ENV} at a larger drive and restart Nova."
    if free is None:
        why = disk.get("error") or "not read"
        return (DIAG_STATE_UNKNOWN, f"free space on {where} unknown ({why})",
                f"Nova could not read the free space on {where}, so a filling drive would go unseen.", move)
    if free < SCREEN_RECORD_FREE_FAIL_BYTES:
        return (DIAG_STATE_FAIL, f"{where} has {_gb(free)} free (fails under {_gb(SCREEN_RECORD_FREE_FAIL_BYTES)})",
                f"{keeps} With this little room the recording can stop when the drive fills.", move)
    if free < SCREEN_RECORD_FREE_WARN_BYTES:
        return (DIAG_STATE_WARN, f"{where} has {_gb(free)} free (warns under {_gb(SCREEN_RECORD_FREE_WARN_BYTES)})",
                keeps, move)
    return None


def _paused_row(evidence: dict[str, Any], detail: str, cause: str) -> list[dict[str, Any]]:
    return [row(id=_ID, group=DIAG_GROUP_RECORDER, title=_TITLE, state=DIAG_STATE_OFF, detail=detail, cause=cause,
                fix=_TURN_ON, evidence=evidence)]


def screen_record_rows(*, status: dict[str, Any], environ: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """The ``screen_recorder`` row; ``environ`` is this backend's environment (``os.environ`` by default)."""
    environ = os.environ if environ is None else environ
    report = status.get("report")
    age = status.get("age_sec")
    evidence: dict[str, Any] = {"reported": bool(status.get("reported")), "fresh": bool(status.get("fresh")),
                                "age_sec": age, "flag_on": _flag_on(environ)}
    since = None
    if report is None and not evidence["flag_on"]:
        return _paused_row(
            evidence, f"{_PAUSED}; no desktop app has reported",
            f"Only the desktop app records the screen, and only with {SCREEN_RECORD_ENV}=1 (ADR 067); this "
            "backend's .env does not set it, and no desktop app has said otherwise.")
    if report is not None and report.get("state") == "paused":
        evidence.update({"state": "paused", "dir": report.get("dir"), "dir_source": report.get("dir_source")})
        stale = "" if status.get("fresh") else f"; the desktop app's last report is {age:.0f} s old"
        return _paused_row(
            evidence, f"{_PAUSED}: no monitor is recorded{stale}",
            f"The desktop app records the screen only when {SCREEN_RECORD_ENV} is set to 1 (ADR 067). It read no "
            "such setting when it started, so it captures nothing and writes nothing.")
    if report is None:
        state, detail = DIAG_STATE_FAIL, "the screen is not being recorded: no Nova desktop app has reported"
        cause = (f"{SCREEN_RECORD_ENV} turns the screen recording on, and only the desktop app records it "
                 "(ADR 035, ADR 067). A browser desk cannot record the screen, and no desktop app has told this "
                 "backend it is recording.")
        fix = _OPEN_APP
    elif not status.get("fresh"):
        state = DIAG_STATE_FAIL
        detail = f"the screen may not be recorded: the desktop app's last report is {age:.0f} s old"
        cause = (f"The desktop app reports every few seconds; nothing for over {SCREEN_RECORD_STALE_SEC:.0f} s "
                 "means it was closed, hung, or cannot reach this backend.")
        fix = _OPEN_APP
    else:
        displays = list(report.get("displays") or [])
        on = sum(1 for d in displays if d.get("recording"))
        total = len(displays) + len(report.get("unmatched") or [])
        rec_state = report.get("state")
        error = report.get("error") or next((d.get("error") for d in displays if d.get("error")), None)
        since = report.get("since")
        if rec_state == "recording":
            state = DIAG_STATE_OK
            detail = (f"recording {_monitors(total)} to {report.get('dir')} "
                      f"({_codec(report.get('mime'))}, {report.get('fps'):g} fps)")
            cause = f"On ({SCREEN_RECORD_ENV}=1) while the desktop app runs; a new file every quarter hour."
            fix = f"Nothing to do. To pause it, remove {SCREEN_RECORD_ENV}=1 from Nova's .env and restart Nova."
        elif rec_state == "starting":
            state, detail = DIAG_STATE_WARN, f"starting to record {_monitors(total) if total else 'every monitor'}"
            cause, fix = "The desktop app just started.", "Nothing to do; it records within seconds."
        elif rec_state == "suspended":
            state, detail = DIAG_STATE_OFF, "the PC is asleep; recording resumes when it wakes"
            cause, fix = "Nothing is on screen while the PC sleeps.", "Nothing to do."
        elif rec_state == "partial":
            state = DIAG_STATE_FAIL
            detail = f"only {on} of {total} monitors are recorded: {error or 'a monitor is not recording'}"
            cause = "A monitor's capture failed or stalled; the desktop app retries on its own, at least once a minute."
            fix = "If it does not come back, restart Nova; the Windows lock screen can block capture until you sign in."
        else:
            state = DIAG_STATE_FAIL
            detail = f"the screen is not being recorded: {error or rec_state}"
            cause = "The desktop app's recorder is down; it retries on its own, at least once a minute."
            fix = "If it does not come back within a minute, restart Nova."
        if state in (DIAG_STATE_OK, DIAG_STATE_WARN) and report.get("dir_source") == "fallback":
            state = DIAG_STATE_WARN
            detail = f"{detail} -- on the system drive"
            cause = report.get("dir_note") or "The data drive is not mounted, so the screen records to the system drive."
            fix = f"Mount the data drive (F:), or point {SCREEN_RECORD_DIR_ENV} at another drive, and restart Nova."
        verdict = _disk_verdict(report)
        if verdict is not None:
            d_state, d_detail, d_cause, d_fix = verdict
            if _SEVERITY[d_state] > _SEVERITY[state]:
                state, detail, cause, fix = d_state, f"{d_detail} -- {detail}", d_cause, d_fix
            else:
                detail = f"{detail} -- {d_detail}"
        evidence.update({
            "state": rec_state,
            "recording": bool(report.get("recording")),
            "dir": report.get("dir"),
            "dir_source": report.get("dir_source"),
            "mime": report.get("mime"),
            "fps": report.get("fps"),
            "displays": [{k: d.get(k) for k in ("index", "recording", "width", "height", "error")} for d in displays],
            "free_bytes": (report.get("disk") or {}).get("free_bytes"),
            "restarts": report.get("restarts"),
            "problems": list(report.get("problems") or [])[:5],
        })
    return [row(id=_ID, group=DIAG_GROUP_RECORDER, title=_TITLE, state=state, detail=detail, cause=cause,
                fix=fix, since=since, evidence=evidence)]
