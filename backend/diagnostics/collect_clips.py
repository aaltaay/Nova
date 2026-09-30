"""The diagnostics row for share clips (ADR 039).

A clip is marks on the always-on screen recording, so this row is quiet in the
ordinary run: off with no desktop app reporting (a browser desk cannot record
clips), ok while clips are open or on file. It warns when a high-quality
capture was lost (the screen recording fills in) or the clip list cannot be
written, and fails only when an open clip has no picture at all -- the one loud
state, as on the header chip.
"""
from __future__ import annotations

from typing import Any

from constants_clips import CLIPS_DIR_ENV, CLIPS_STALE_SEC
from constants_diagnostics import (
    DIAG_GROUP_RECORDER,
    DIAG_STATE_FAIL,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_UNKNOWN,
    DIAG_STATE_WARN,
)
from diagnostics.rows import row

_ID = "clips"
_TITLE = "Share clips"


def _names(clips: list[dict[str, Any]]) -> str:
    return ", ".join(str(c.get("symbol") or "?") for c in clips)


def clip_rows(*, status: dict[str, Any]) -> list[dict[str, Any]]:
    view = status.get("view")
    evidence: dict[str, Any] = {"reported": bool(status.get("reported")), "fresh": bool(status.get("fresh")),
                                "age_sec": status.get("age_sec")}
    if view is None:
        return [row(id=_ID, group=DIAG_GROUP_RECORDER, title=_TITLE, state=DIAG_STATE_OFF,
                    detail="no desktop app reports clips",
                    cause="Clips are cut from the desktop app's screen recording (ADR 039); a browser desk cannot record them.",
                    fix="Open Nova from the desktop app to record clips.", evidence=evidence)]
    if not status.get("fresh"):
        age = status.get("age_sec") or 0
        return [row(id=_ID, group=DIAG_GROUP_RECORDER, title=_TITLE, state=DIAG_STATE_UNKNOWN,
                    detail=f"the desktop app's last clip report is {age:.0f} s old",
                    cause=(f"The desktop app reports every few seconds; nothing for over {CLIPS_STALE_SEC:.0f} s means it "
                           "was closed, hung, or cannot reach this backend."),
                    fix="Check the Trading screen recording row; restart Nova from the desktop app if it is down.",
                    evidence=evidence)]
    open_clips = list(view.get("open") or [])
    listed = list(view.get("clips") or [])
    no_picture = [c for c in open_clips if c.get("state") == "no_picture"]
    lost = [c for c in open_clips if c.get("state") == "hq_lost"]
    hq = sum(1 for c in open_clips if c.get("hq"))
    summary = (f"{len(open_clips)} clip{'' if len(open_clips) == 1 else 's'} open ({_names(open_clips)}; {hq} in high quality)"
               if open_clips else "no clip open")
    detail = f"{summary} · {len(listed)} on file in {view.get('dir')}"
    state, cause, fix = DIAG_STATE_OK, "A clip is marks on the screen recording; nothing runs until one is exported.", "Nothing to do."
    if no_picture:
        state = DIAG_STATE_FAIL
        detail = f"{_names(no_picture)}: the clip has no picture -- {detail}"
        cause = "The screen recording is not seeing that tab's monitor, and High quality is off, so nothing films the tab."
        fix = "Turn High quality on for the clip (Record menu), or fix the Trading screen recording row."
    elif lost:
        state = DIAG_STATE_WARN
        detail = f"{_names(lost)}: high quality stopped, the screen recording fills in -- {detail}"
        cause = "A high-quality capture stopped by itself; the desktop app starts it again with back-off."
        fix = "Nothing to do unless it stays lost; the export takes those seconds from the screen recording."
    elif view.get("dir_error"):
        state = DIAG_STATE_WARN
        detail = f"{view.get('dir_error')} -- {detail}"
        cause = "The clip list or a clip file cannot be written where clips go."
        fix = f"Free or fix {view.get('dir')}, or point {CLIPS_DIR_ENV} at another folder and restart Nova."
    elif view.get("dir_source") == "fallback":
        state = DIAG_STATE_WARN
        detail = f"{detail} -- on the system drive"
        cause = str(view.get("dir_note") or "The data drive is not mounted, so clips go to the system drive.")
        fix = f"Mount the data drive (F:), or point {CLIPS_DIR_ENV} at another drive, and restart Nova."
    evidence.update({
        "open": [{k: c.get(k) for k in ("symbol", "state", "started_ts")} | {"hq": bool(c.get("hq"))} for c in open_clips],
        "hq_in_use": view.get("hq_in_use"),
        "hq_max": view.get("hq_max"),
        "clips": len(listed),
        "dir": view.get("dir"),
        "dir_source": view.get("dir_source"),
        "exporting": view.get("exporting"),
        "free_bytes": (view.get("disk") or {}).get("free_bytes"),
    })
    return [row(id=_ID, group=DIAG_GROUP_RECORDER, title=_TITLE, state=state, detail=detail, cause=cause, fix=fix,
                evidence=evidence)]
