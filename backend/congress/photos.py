"""Members' official portraits, kept on the desk (ADR 066, decision 4).

One source: the Biographical Directory of the United States Congress (``CONGRESS_PHOTO_URL``), the House and Senate
historians' own record, under the same bioguide id every member is matched by -- both chambers, and members who left.
Owner of ``<cache_dir>/congress/photos/``: ``<BIOGUIDE>.jpg`` (the Bioguide's portrait shrunk to fit
``CONGRESS_PHOTO_BOX``) and ``index.json`` (``{schema_version: 2, source, kept: {bioguide: fetched_at}, misses:
{bioguide: asked_at}}``). Only a portrait the index says came from ``source`` is served: a file kept from another
source (``unitedstates/images`` before 2026-10-23) or of another index version is asked for again and replaced. A kept
portrait is asked again after ``CONGRESS_PHOTO_MAX_AGE_SEC``, so a new official one replaces it; a member the Bioguide
has none for, after ``CONGRESS_PHOTO_RETRY_SEC``. The page draws initials meanwhile. The route only serves what is kept.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import threading
from pathlib import Path

from PIL import Image, ImageOps

from congress import files
from congress.constants_congress import (
    CONGRESS_MAX_PHOTO_BYTES,
    CONGRESS_MAX_PHOTO_PIXELS,
    CONGRESS_PHOTO_BOX,
    CONGRESS_PHOTO_INDEX_FILE,
    CONGRESS_PHOTO_INDEX_VERSION,
    CONGRESS_PHOTO_MAX_AGE_SEC,
    CONGRESS_PHOTO_QUALITY,
    CONGRESS_PHOTO_RETRY_SEC,
    CONGRESS_PHOTO_URL,
    CONGRESS_PHOTOS_DIR,
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


def _index() -> dict[str, dict[str, float]]:
    empty: dict[str, dict[str, float]] = {"kept": {}, "misses": {}}
    try:
        doc = json.loads((folder() / CONGRESS_PHOTO_INDEX_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:  # maintainer: allow-swallow nothing kept yet: every portrait may be asked
        return empty
    except (OSError, ValueError) as exc:  # maintainer: allow-swallow logged; a forgotten index only asks again
        logger.warning("congress: %s could not be read (%s); portraits asked again", CONGRESS_PHOTO_INDEX_FILE, exc)
        return empty
    if (not isinstance(doc, dict) or doc.get("schema_version") != CONGRESS_PHOTO_INDEX_VERSION
            or doc.get("source") != CONGRESS_PHOTO_URL):
        return empty
    return {k: {b: float(t) for b, t in (doc.get(k) or {}).items() if valid(b) and isinstance(t, (int, float))}
            for k in ("kept", "misses")}


def _save_index(index: dict[str, dict[str, float]]) -> None:
    target = folder() / CONGRESS_PHOTO_INDEX_FILE
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"schema_version": CONGRESS_PHOTO_INDEX_VERSION, "source": CONGRESS_PHOTO_URL, **index}),
                   encoding="utf-8")
    os.replace(tmp, target)


def kept() -> set[str]:
    """Members whose portrait from the one source is on the desk."""
    on_disk = {p.stem for p in folder().glob("*.jpg") if valid(p.stem)}
    return on_disk & set(_index()["kept"])


def kept_file(bioguide: str) -> Path | None:
    """The kept portrait of one member, found in the folder's own listing -- never a path built from the ask."""
    if bioguide not in _index()["kept"]:
        return None
    return next((p for p in folder().glob("*.jpg") if p.stem == bioguide and valid(p.stem)), None)


def wanted(bioguides: list[str], now: float) -> list[str]:
    """Those to ask the Bioguide for, in the order given: first the members without a portrait, then those whose
    portrait is older than ``CONGRESS_PHOTO_MAX_AGE_SEC``; none the Bioguide had nothing for within the retry time."""
    index, have = _index(), kept()
    missed = index["misses"]
    due = [b for b in dict.fromkeys(bioguides)
           if valid(b) and now - missed.get(b, float("-inf")) >= CONGRESS_PHOTO_RETRY_SEC]
    return ([b for b in due if b not in have]
            + [b for b in due if b in have and now - index["kept"][b] >= CONGRESS_PHOTO_MAX_AGE_SEC])


def shrink(data: bytes) -> bytes | None:
    """The portrait made to fit ``CONGRESS_PHOTO_BOX``, as JPEG; None when ``data`` is not a JPEG picture."""
    if data[:3] != b"\xff\xd8\xff":
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format != "JPEG" or im.width * im.height > CONGRESS_MAX_PHOTO_PIXELS:
                return None
            im.draft("RGB", CONGRESS_PHOTO_BOX)
            face = ImageOps.exif_transpose(im).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:  # maintainer: allow-swallow logged; a miss
        logger.warning("congress: a portrait could not be decoded: %s", exc)
        return None
    face.thumbnail(CONGRESS_PHOTO_BOX, Image.Resampling.LANCZOS)
    out = io.BytesIO()
    face.save(out, "JPEG", quality=CONGRESS_PHOTO_QUALITY, optimize=True)
    return out.getvalue()


def fetch(net, bioguide: str, now: float) -> bool:
    """Ask the Bioguide for one member's portrait and keep it. False (and a miss) when it has none; a failure of the
    site itself (any answer but 200 or 404, or no answer) is raised, so the reader waits on the source, not the member.
    """
    target = file(bioguide)
    if target is None:
        return False
    try:
        resp = net.get(CONGRESS_PHOTO_URL.format(bioguide=bioguide), max_bytes=CONGRESS_MAX_PHOTO_BYTES)
    except TooLarge:  # maintainer: allow-swallow over the limit is a miss, said in the log
        logger.warning("congress: the portrait of %s is over %d KB", bioguide, CONGRESS_MAX_PHOTO_BYTES // 1024)
        resp = None
    if resp is not None and resp.status_code != 404:
        resp.raise_for_status()
    face = shrink(resp.content) if resp is not None and resp.status_code == 200 else None
    with _lock:
        index = _index()
        if face is None:
            index["misses"][bioguide] = now
        else:
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(face)
            os.replace(tmp, target)
            index["kept"][bioguide] = now
            index["misses"].pop(bioguide, None)
        _save_index(index)
    return face is not None
