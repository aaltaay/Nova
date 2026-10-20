"""Where the operator's data lives, read from the environment on every call so a test (or another PC) can move it.

``NOVA_MARKET_DATA_DIR`` -- the Massive files and their reference dump (default ``E:\\Nova\\massive``);
``NOVA_CATALYST_DIR`` -- the catalyst store and SEC's bulk EDGAR files under ``edgar/`` (default
``F:\\Nova\\catalysts``). The same variables ``research/leaderboard/lb_config.py`` and
``research/catalysts/cat_config.py`` read. ``NOVA_SIM_CAPTURE_DIR`` -- the Session Records (default
``F:\\Nova\\sim_capture``) and ``NOVA_CACHE_DIR`` -- the desk cache that holds ``l2.db`` and ``archive.db``: the
variables the recorder and ``backend/paths.py`` read.
"""
from __future__ import annotations

import os
from pathlib import Path

from market_reads import REPO

MASSIVE_DEFAULT = r"E:\Nova\massive"
CATALYST_DEFAULT = r"F:\Nova\catalysts"


def massive() -> Path:
    return Path(os.environ.get("NOVA_MARKET_DATA_DIR") or MASSIVE_DEFAULT)


def reference() -> Path:
    """Massive's reference dump: financials, float, IPOs, ticker details, splits, short interest."""
    return massive() / "store" / "reference"


def movers_db() -> Path:
    from constants_day_movers import DAY_MOVERS_DB_FILENAME, DAY_MOVERS_SUBDIR
    return massive() / DAY_MOVERS_SUBDIR / DAY_MOVERS_DB_FILENAME


def edgar() -> Path:
    """SEC's bulk files: ``companyfacts.zip`` (every XBRL fact) and ``submissions.zip`` (every filing's form/date)."""
    return Path(os.environ.get("NOVA_CATALYST_DIR") or CATALYST_DEFAULT) / "edgar"


def sim_capture() -> Path:
    """The Session Records folder, as the recorder resolves it (``NOVA_SIM_CAPTURE_DIR``, else ``F:\\Nova\\sim_capture``)
    -- named, never made."""
    from capture.storage import capture_root
    return capture_root(create=False)


def _main_checkout() -> Path:
    """The checkout this worktree was cut from (this one when it is not a worktree): the desk's own cache lives there."""
    marker = REPO / ".git"
    try:
        if marker.is_file():
            gitdir = marker.read_text(encoding="utf-8").strip().removeprefix("gitdir:").strip()
            return Path(gitdir).parents[2]
    except (OSError, IndexError):
        pass
    return REPO


def cache_candidates() -> list[Path]:
    """Folders the desk cache (``l2.db``, ``archive.db``) may be in, best first: ``NOVA_CACHE_DIR`` alone when set,
    else the main checkout's ``backend/.cache`` (a worktree keeps its own, empty one), this checkout's, then
    ``F:\\Nova\\cache`` (where ``tools/data_root.py`` moves it)."""
    from constants_data_root import DATA_CACHE_TARGET_WIN
    if os.environ.get("NOVA_CACHE_DIR"):
        return [Path(os.environ["NOVA_CACHE_DIR"])]
    found: list[Path] = []
    for path in (_main_checkout() / "backend" / ".cache", REPO / "backend" / ".cache", Path(DATA_CACHE_TARGET_WIN)):
        if path not in found:
            found.append(path)
    return found


def cache_store(filename: str) -> Path:
    """``filename`` in the first cache folder that holds it; ``LookupError`` names every folder looked in."""
    candidates = cache_candidates()
    for folder in candidates:
        if (folder / filename).is_file():
            return folder / filename
    raise LookupError(f"{filename} is not on disk; looked in {', '.join(str(c) for c in candidates)} "
                      "(NOVA_CACHE_DIR names the desk's cache folder)")
