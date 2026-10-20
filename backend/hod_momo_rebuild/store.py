"""The files of a rebuilt day's HOD Momo alerts.

Persisted state (persisted-state.mdc). Owner: this module, the only reader and writer of
``<leaderboard root>/hod_momo/<date>.alerts.json`` and ``<date>.job.json``, each written whole (temp file, rename):

* the data file -- ``{schema_version, date, built_ts, fingerprint, float_basis, summary, alerts}`` -- is whole or
  absent; ``alerts`` oldest first, each in ``hod_momo_models.alert_to_dict``'s shape;
* the job file is the build's state: ``{schema_version, date, status, stage, done, total, started_ts, updated_ts,
  finished_ts, error, summary, fingerprint}``.

Invalidated when what a build read changes (``fingerprint``, compared by ``job``). An unknown version of either
file is never read (logged): the day reads as never built, and asking builds it again. Shapes:
``architecture/schema/scanner.md``, "A rebuilt day's HOD Momo alerts".
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date as date_cls
from pathlib import Path
from time import time as _wall_clock      # the real clock: the engine pins ``time.time`` to the replay's
from typing import Any

from constants_hod_momo import HOD_MOMO_REBUILD_SCHEMA_VERSION, HOD_MOMO_REBUILD_SUBDIR
from leaderboard import store as board_store

logger = logging.getLogger(__name__)
_REPLACE_TRIES = 50
_REPLACE_PAUSE_SEC = 0.1


def day_key(day: str) -> str:
    """``day`` as ``YYYY-MM-DD``, rebuilt from its numbers -- the only form a file name, a path or the worker's
    command line is made from. Anything that is not a calendar day raises ``ValueError``."""
    parts = str(day).split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("a day is YYYY-MM-DD")
    year, month, mday = (int(part) for part in parts)
    return date_cls(year, month, mday).isoformat()


def folder() -> Path:
    return board_store.root() / HOD_MOMO_REBUILD_SUBDIR


def _inside(name: str) -> Path:
    base = os.path.realpath(folder())
    target = os.path.realpath(os.path.join(base, name))
    if not target.startswith(base + os.sep):
        raise ValueError("a rebuild file stays inside its folder")
    return Path(target)


def data_path(day: str) -> Path:
    return _inside(f"{day_key(day)}.alerts.json")


def job_path(day: str) -> Path:
    return _inside(f"{day_key(day)}.job.json")


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    for attempt in range(_REPLACE_TRIES):
        try:
            os.replace(temp, path)
            return
        except PermissionError:             # a reader holds it for a moment (Windows refuses the rename)
            if attempt == _REPLACE_TRIES - 1:
                temp.unlink(missing_ok=True)
                raise
            time.sleep(_REPLACE_PAUSE_SEC)


def _read(path: Path, what: str) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("HOD rebuild: %s %s unreadable (%s); read as never built", what, path, exc)
        return None
    if not isinstance(raw, dict) or raw.get("schema_version") != HOD_MOMO_REBUILD_SCHEMA_VERSION:
        logger.warning("HOD rebuild: %s %s is not schema %d; read as never built", what, path,
                       HOD_MOMO_REBUILD_SCHEMA_VERSION)
        return None
    return raw


def read_job(day: str) -> dict[str, Any] | None:
    return _read(job_path(day), "job file")


def write_job(day: str, **fields: Any) -> dict[str, Any]:
    """Merge ``fields`` into the job and write it whole; ``updated_ts`` is stamped every time."""
    job = read_job(day) or {}
    job.update(fields)
    job.update(schema_version=HOD_MOMO_REBUILD_SCHEMA_VERSION, date=day, updated_ts=_wall_clock())
    _write(job_path(day), job)
    return job


def write_data(day: str, *, fingerprint: str, float_basis: str, summary: dict[str, Any], alerts: list[dict]) -> None:
    _write(data_path(day), {"schema_version": HOD_MOMO_REBUILD_SCHEMA_VERSION, "date": day, "built_ts": _wall_clock(),
                            "fingerprint": fingerprint, "float_basis": float_basis, "summary": summary,
                            "alerts": alerts})


def read_data(day: str) -> dict[str, Any] | None:
    return _read(data_path(day), "alerts file")
