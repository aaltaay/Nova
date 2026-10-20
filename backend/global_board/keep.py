"""The Global page's answers kept across restarts (ADR 060).

Owner of ``<cache_dir>/global-board/global-store.json`` (shape in architecture/schema/global-board.md): ``{schema_version,
saved_at, entries: {key: {at, value}}}``. The desk's backend restarts when the app closes and after every update; a
market that closed hours ago would otherwise spend IBKR's historical budget again to show the same day. The reader
writes the store here at most every ``GLOBAL_KEEP_SAVE_SEC`` when an answer changed; the first start reads them back,
each at its own answer time. A file of another ``schema_version`` reads as absent, never migrated by guesswork, and an
entry older than ``GLOBAL_KEEP_MAX_AGE_SEC`` is not read back. Nothing here asks IBKR.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from constants_global_board import (
    GLOBAL_KEEP_DIR,
    GLOBAL_KEEP_FILE,
    GLOBAL_KEEP_MAX_AGE_SEC,
    GLOBAL_KEEP_SAVE_SEC,
    GLOBAL_SCHEMA_VERSION,
)
from global_board.state import Store

logger = logging.getLogger(__name__)
KEPT = ("flow:", "quotes", "fx:", "index_daily:", "daily_flow:", "refused:")

_lock = threading.Lock()
_saved_version = -1
_last_save = 0.0
_loaded = False


def path() -> Path:
    import paths

    folder = paths.cache_dir() / GLOBAL_KEEP_DIR
    folder.mkdir(parents=True, exist_ok=True)
    return folder / GLOBAL_KEEP_FILE


def kept(key: str) -> bool:
    return any(key.startswith(k) for k in KEPT)


def save(st: Store, now: float) -> int:
    global _saved_version, _last_save
    version = st.version()
    entries = {k: {"at": at, "value": v} for k, (v, at) in st.entries().items() if kept(k)}
    target = path()
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps({"schema_version": GLOBAL_SCHEMA_VERSION, "saved_at": now, "entries": entries},
                              separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, target)
    with _lock:
        _saved_version, _last_save = version, now
    return len(entries)


def maybe_save(st: Store, now: float) -> bool:
    global _last_save
    with _lock:
        if now - _last_save < GLOBAL_KEEP_SAVE_SEC or st.version() == _saved_version:
            return False
    try:
        save(st, now)
    except (OSError, TypeError, ValueError):
        logger.warning("global_board: keeping the answers failed; the next start reads them again", exc_info=True)
        with _lock:
            _last_save = now
        return False
    return True


def load(st: Store, now: float) -> int:
    target = path()
    if not target.is_file():
        return 0
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("global_board: %s unreadable; treated as absent", target, exc_info=True)
        return 0
    if not isinstance(data, dict) or data.get("schema_version") != GLOBAL_SCHEMA_VERSION:
        logger.warning("global_board: %s has another schema_version; treated as absent", target)
        return 0
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return 0
    taken = 0
    for key, entry in entries.items():
        if not kept(key) or not isinstance(entry, dict):
            continue
        at = entry.get("at")
        if not isinstance(at, (int, float)) or now - at > GLOBAL_KEEP_MAX_AGE_SEC or at > now + 60:
            continue
        if st.restore(key, entry.get("value"), float(at)):
            taken += 1
    return taken


def load_once(st: Store, now: float) -> int:
    global _loaded, _saved_version
    with _lock:
        if _loaded:
            return 0
        _loaded = True
    try:
        taken = load(st, now)
    except OSError:
        logger.warning("global_board: the kept answers could not be read; every read starts over", exc_info=True)
        return 0
    with _lock:
        _saved_version = st.version()
    if taken:
        logger.info("global_board: %d kept answers restored from %s", taken, GLOBAL_KEEP_FILE)
    return taken


def reset_for_tests() -> None:
    global _saved_version, _last_save, _loaded
    with _lock:
        _saved_version, _last_save, _loaded = -1, 0.0, False
