"""Members' official portraits, kept on the desk (ADR 066, decision 4).

Owner of ``<cache_dir>/congress/photos/``: ``<BIOGUIDE>.jpg`` and ``misses.json`` (``{schema_version, misses:
{bioguide: asked_at}}``). A portrait comes from ``unitedstates/images`` (public domain), else the Congress biographical
directory; only a real JPEG under ``CONGRESS_MAX_PHOTO_BYTES`` is kept. A member with neither is asked again after
``CONGRESS_PHOTO_RETRY_SEC``; the page draws their initials meanwhile. The route only serves what is kept.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path

from congress import files
from congress.constants_congress import (
    CONGRESS_MAX_PHOTO_BYTES,
    CONGRESS_PHOTO_MISSES_FILE,
    CONGRESS_PHOTO_RETRY_SEC,
    CONGRESS_PHOTO_URLS,
    CONGRESS_PHOTOS_DIR,
    CONGRESS_SCHEMA_VERSION,
)
from congress.net import TooLarge

logger = logging.getLogger(__name__)
BIOGUIDE = re.compile(r"^[A-Z][0-9]{6}$")
_lock = threading.Lock()


def valid(bioguide: str) -> bool:
    return bool(BIOGUIDE.match(bioguide or ""))


def folder() -> Path:
    return files.folder(CONGRESS_PHOTOS_DIR)


def file(bioguide: str) -> Path | None:
    return folder() / f"{bioguide}.jpg" if valid(bioguide) else None


def kept_file(bioguide: str) -> Path | None:
    """The kept portrait of one member, found in the folder's own listing -- never a path built from the ask."""
    return next((p for p in folder().glob("*.jpg") if p.stem == bioguide and valid(p.stem)), None)


def has(bioguide: str) -> bool:
    f = file(bioguide)
    return bool(f and f.exists())


def kept() -> set[str]:
    return {p.stem for p in folder().glob("*.jpg") if valid(p.stem)}


def _misses() -> dict[str, float]:
    try:
        doc = json.loads((folder() / CONGRESS_PHOTO_MISSES_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:  # maintainer: allow-swallow no misses kept yet: every portrait may be asked
        return {}
    except (OSError, ValueError) as exc:  # maintainer: allow-swallow logged; forgotten misses are only asked again
        logger.warning("congress: %s could not be read (%s); misses forgotten", CONGRESS_PHOTO_MISSES_FILE, exc)
        return {}
    if not isinstance(doc, dict) or doc.get("schema_version") != CONGRESS_SCHEMA_VERSION:
        return {}
    return {k: float(v) for k, v in (doc.get("misses") or {}).items() if valid(k) and isinstance(v, (int, float))}


def _save_misses(misses: dict[str, float]) -> None:
    target = folder() / CONGRESS_PHOTO_MISSES_FILE
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"schema_version": CONGRESS_SCHEMA_VERSION, "misses": misses}), encoding="utf-8")
    os.replace(tmp, target)


def wanted(bioguides: list[str], now: float) -> list[str]:
    """Those still without a portrait and not asked within the retry time, in the order given."""
    have, misses = kept(), _misses()
    return [b for b in dict.fromkeys(bioguides)
            if valid(b) and b not in have and now - misses.get(b, float("-inf")) >= CONGRESS_PHOTO_RETRY_SEC]


def fetch(net, bioguide: str, now: float) -> bool:
    """Ask each source for one member's portrait; keep the first real JPEG. False (and a miss) when none had one."""
    target = file(bioguide)
    if target is None:
        return False
    for template in CONGRESS_PHOTO_URLS:
        url = template.format(bioguide=bioguide, letter=bioguide[0])
        try:
            resp = net.get(url, max_bytes=CONGRESS_MAX_PHOTO_BYTES)
        except TooLarge:
            continue
        if resp.status_code == 200 and resp.content[:3] == b"\xff\xd8\xff":
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(resp.content)
            os.replace(tmp, target)
            return True
    with _lock:
        misses = _misses()
        misses[bioguide] = now
        _save_misses(misses)
    return False
