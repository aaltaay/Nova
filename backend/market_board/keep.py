"""The Market page's IBKR answers kept across restarts (ADR 053 amendment 2026-10-13 evening).

Owner of ``<cache_dir>/market-board/board-store.json`` (shape in architecture/schema/market-board.md). The desk app's
backend restarts when the app closes and after every update, and a fresh process waited 8-10 minutes for the ~105
daily-close reads behind the 7 D / 30 D moves (``market_board.first.closes`` 509-632 s on 2026-10-13). So the
``files`` refresher writes the store's IBKR answers here at most every ``MARKET_KEEP_SAVE_SEC`` when one changed,
and the first refresher start reads them back, each at its own answer time: the store's age rules then decide what
the page shows and what is read again, exactly as if this process had read them. Nothing here asks IBKR.
"""
from __future__ import annotations

import logging
import threading
from constants_market_board import MARKET_KEEP_FILE, MARKET_KEEP_MAX_AGE_SEC, MARKET_KEEP_SAVE_SEC
from market_board import disk
from market_board.state import Store

logger = logging.getLogger(__name__)

# Exact keys, and prefixes ending in ":" (one key per tile, symbol or chunk).
KEPT = ("quotes", "etf_quotes", "etf_bars", "movers", "movers_bars", "pool_quotes:", "line:", "prior:", "closes:")

_lock = threading.Lock()
_saved_version = -1
_last_save = 0.0
_loaded = False


def kept(key: str) -> bool:
    return any(key.startswith(k) if k.endswith(":") else key == k for k in KEPT)


def save(st: Store, now: float) -> int:
    """Write every kept answer; returns how many were written."""
    global _saved_version, _last_save
    version = st.version()
    entries = st.entries(kept)
    disk.write(MARKET_KEEP_FILE, {"saved_at": now,
                                  "entries": {k: {"at": at, "value": v} for k, (v, at) in entries.items()}})
    with _lock:
        _saved_version, _last_save = version, now
    return len(entries)


def maybe_save(st: Store, now: float) -> bool:
    """``save`` when an answer changed since the last write and ``MARKET_KEEP_SAVE_SEC`` passed."""
    global _last_save
    with _lock:
        if now - _last_save < MARKET_KEEP_SAVE_SEC or st.version() == _saved_version:
            return False
    try:
        save(st, now)
    except (OSError, TypeError, ValueError):
        logger.warning("market_board: keeping the board's answers failed; the next start reads them again",
                       exc_info=True)
        with _lock:
            _last_save = now   # try again after the save interval, not on every turn
        return False
    return True


def load(st: Store, now: float) -> int:
    """Restore the kept answers younger than ``MARKET_KEEP_MAX_AGE_SEC``; returns how many were taken."""
    data = disk.read(MARKET_KEEP_FILE)
    entries = (data or {}).get("entries")
    if not isinstance(entries, dict):
        return 0
    taken = 0
    for key, entry in entries.items():
        if not kept(key) or not isinstance(entry, dict):
            continue
        at = entry.get("at")
        if not isinstance(at, (int, float)) or now - at > MARKET_KEEP_MAX_AGE_SEC or at > now + 60:
            continue
        if st.restore(key, entry.get("value"), float(at)):
            taken += 1
    return taken


def load_once(st: Store, now: float) -> int:
    """``load`` the first time a refresher starts in this process; later calls do nothing."""
    global _loaded, _saved_version
    with _lock:
        if _loaded:
            return 0
        _loaded = True
    try:
        taken = load(st, now)
    except OSError:
        logger.warning("market_board: the kept board could not be read; every read starts over", exc_info=True)
        return 0
    with _lock:
        _saved_version = st.version()   # what was just read back needs no write until something new arrives
    if taken:
        logger.info("market_board: %d kept answers restored from %s", taken, MARKET_KEEP_FILE)
    return taken


def reset_for_tests() -> None:
    global _saved_version, _last_save, _loaded
    with _lock:
        _saved_version, _last_save, _loaded = -1, 0.0, False
