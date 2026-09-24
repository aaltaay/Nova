"""The ``data_folders`` row: which drive really holds each of Nova's data folders.

Operator ask 2026-09-24: "any recording and data, lets keep them off the C
drive". ``folders`` is ``[{id, label, path, real, env, error}]``, read by the
shell (``diagnostics.gather``): ``real`` is the path with junctions resolved,
because ``tools/data_root.py move`` leaves ``backend\\.cache`` and
``backend\\logs`` in place as junctions to F:. A folder on the system drive
while F: is mounted warns; a folder whose drive is gone fails; a folder that
cannot be resolved is ``unknown`` with the reason, never ``ok``.
"""
from __future__ import annotations

import ntpath
from typing import Any

from constants_data_root import DATA_MOVE_COMMAND
from constants_diagnostics import (
    DIAG_GROUP_PROCESS,
    DIAG_STATE_FAIL,
    DIAG_STATE_OK,
    DIAG_STATE_UNKNOWN,
    DIAG_STATE_WARN,
)
from diagnostics.rows import row


def _drive(path: str | None) -> str:
    """``F:`` for a Windows path (upper case); ``""`` for a POSIX one."""
    return ntpath.splitdrive(path or "")[0].upper()


def _named(folders: list[dict[str, Any]]) -> str:
    return ", ".join(f"{f['label']} ({f['real']})" for f in folders)


def data_folder_rows(
    *, folders: list[dict[str, Any]], data_drive: str, data_drive_mounted: bool, system_drive: str,
) -> list[dict[str, Any]]:
    data_drive, system_drive = data_drive.upper(), system_drive.upper()
    unread = [f for f in folders if f.get("error")]
    read = [f for f in folders if not f.get("error")]
    gone = [f for f in read if _drive(f["real"]) == data_drive and not data_drive_mounted]
    on_system = [f for f in read if data_drive_mounted and _drive(f["real"]) == system_drive]
    if gone:
        state = DIAG_STATE_FAIL
        detail = f"{data_drive} is not reachable: {_named(gone)}"
        cause = f"Nova's data lives on {data_drive}; with the drive gone these folders cannot be read or written."
        fix = f"Reconnect {data_drive} (Disk Management shows it), then Reload backend."
    elif unread:
        state = DIAG_STATE_UNKNOWN
        detail = "Unknown: " + "; ".join(f"{f['label']} ({f['error']})" for f in unread)
        cause = "Nova could not resolve where these folders really are, so data on C: would go unseen."
        fix = "Check that the folders exist and are readable."
    elif on_system:
        state = DIAG_STATE_WARN
        detail = f"On {system_drive} while {data_drive} is mounted: {_named(on_system)}"
        cause = f"Operator decision 2026-09-24: recordings and data stay off {system_drive}."
        steps = []
        if any(not f.get("env") for f in on_system):
            steps.append(f"stop Nova (Stop Nova.bat), run `{DATA_MOVE_COMMAND}`, then start Nova")
        steps += [f"set {f['env']} to a folder on {data_drive} in .env, then Reload backend"
                  for f in on_system if f.get("env")]
        joined = "; ".join(steps)
        fix = joined[:1].upper() + joined[1:] + "."
    else:
        state = DIAG_STATE_OK
        where = data_drive if data_drive_mounted else f"{system_drive} (no {data_drive} drive on this PC)"
        detail = f"All {len(folders)} data folders on {where}" if folders else "No data folders reported"
        cause = f"Operator decision 2026-09-24: recordings and data stay off {system_drive}."
        fix = "Nothing to do."
    return [row(
        id="data_folders",
        group=DIAG_GROUP_PROCESS,
        title="Where Nova keeps its data",
        state=state,
        detail=detail,
        cause=cause,
        fix=fix,
        evidence={
            "data_drive": data_drive,
            "data_drive_mounted": data_drive_mounted,
            "system_drive": system_drive,
            "folders": [dict(f) for f in folders],
        },
    )]
