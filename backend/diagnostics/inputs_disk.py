"""What the checklist reads from the disk (ADR 021): every data folder and the drive that really holds it, and the
scanner leaderboard store's size and its drive's free space. Read on the checklist's worker thread; a fact that
cannot be read is stated with its reason, never a guess. ``gather.py`` feeds these to the pure collectors.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from constants_data_root import DATA_DRIVE_WIN, DATA_SYSTEM_DRIVE_DEFAULT


def data_folder_inputs() -> dict[str, Any]:
    """Every data folder and the drive that really holds it (junctions resolved).

    Nothing here creates a folder to look at it: the cache and the logs are
    read with ``paths.cache_root()`` / ``log_root()``, so a junction whose
    drive is gone reports that drive instead of failing a ``mkdir``.
    """
    import paths
    from capture.storage import capture_root
    from catalysts import feed_store
    from constants_catalysts import CATALYST_DIR_ENV
    from constants_eyes import EYES_DIR_ENV
    from constants_leaderboard import LEADERBOARD_DIR_ENV
    from constants_sim import SIM_HISTORY_DIR_ENV
    from eyes import journal as eyes_journal
    from leaderboard import store as leaderboard_store
    from sim import history_store

    folders: list[dict[str, Any]] = []
    for fid, label, env, resolve in (
        ("cache", "Nova cache", "NOVA_CACHE_DIR", paths.cache_root),
        ("logs", "Logs", "NOVA_LOG_DIR", paths.log_root),
        ("captures", "Session Records", "NOVA_SIM_CAPTURE_DIR", capture_root),
        ("downloads", "Replay downloads", SIM_HISTORY_DIR_ENV, lambda: history_store.path().parent),
        ("leaderboard", "Scanner leaderboard", LEADERBOARD_DIR_ENV, leaderboard_store.root),
        ("catalysts", "Catalyst feed", CATALYST_DIR_ENV, feed_store.root),
        ("eyes", "Eyes journal", EYES_DIR_ENV, eyes_journal.eyes_dir),
    ):
        item: dict[str, Any] = {"id": fid, "label": label, "path": None, "real": None,
                                "env": env if (os.environ.get(env) or "").strip() else None, "error": None}
        try:
            item["path"] = str(resolve())
            item["real"] = os.path.realpath(item["path"])
        except (OSError, RuntimeError, ValueError) as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"     # stated on the row, never read as "on F:"
        folders.append(item)
    return {
        "folders": folders,
        "data_drive": DATA_DRIVE_WIN,
        "data_drive_mounted": os.name == "nt" and os.path.isdir(DATA_DRIVE_WIN + "\\"),
        "system_drive": os.environ.get("SystemDrive") or DATA_SYSTEM_DRIVE_DEFAULT,
    }


def leaderboard_disk(db: Path) -> dict[str, Any]:
    """The store's size (the database plus its write-ahead log) and its drive's free space (#485).

    Read here, on the checklist's worker thread. A store not created yet is 0
    bytes; a fact that cannot be read is None with its reason, never a guess.
    """
    out: dict[str, Any] = {"store_bytes": None, "free_bytes": None, "size_error": None, "free_error": None}
    try:
        size = 0
        for part in (db, db.with_name(db.name + "-wal")):
            try:
                size += part.stat().st_size
            except FileNotFoundError:
                continue                        # no store yet, or no write-ahead log right now
        out["store_bytes"] = size
    except OSError as exc:
        out["size_error"] = f"{type(exc).__name__}: {exc}"
    try:
        out["free_bytes"] = int(shutil.disk_usage(db.parent).free)
    except OSError as exc:
        out["free_error"] = f"{type(exc).__name__}: {exc}"
    return out


def leaderboard_inputs() -> dict[str, Any]:
    from leaderboard import auto_record, recorder, store

    db = store.path()
    return {"recorder": recorder.status(), "auto": auto_record.status(), "store_path": str(db),
            "disk": leaderboard_disk(db)}
