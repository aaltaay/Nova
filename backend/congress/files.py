"""Where the Congress page keeps its files: ``<cache_dir>/congress/`` (ADR 066). A folder is made once per path per
process -- a mkdir through the desk's F: junction once held a request for seconds (ADR 045)."""
from __future__ import annotations

import threading
from pathlib import Path

from congress.constants_congress import CONGRESS_DIR

_lock = threading.Lock()
_made: set[str] = set()


def folder(*parts: str) -> Path:
    import paths

    p = paths.cache_root().joinpath(CONGRESS_DIR, *parts)
    key = str(p)
    with _lock:
        if key not in _made:
            p.mkdir(parents=True, exist_ok=True)
            _made.add(key)
    return p
