"""Every member of Congress, their seat and committees, kept on the desk (ADR 066, decision 4).

Owner of ``<cache_dir>/congress/roster.json``: ``{schema_version, read_at, historical_read_at, members: [...]}`` (shape
in architecture/schema/congress.md). Read from the public-domain ``unitedstates/congress-legislators`` data: the
current members and committees every ``CONGRESS_ROSTER_MAX_AGE_SEC``; the historical file (13 MB) only while a filer
is unmatched, at most every ``CONGRESS_HISTORICAL_MAX_AGE_SEC``, for members who left since January 1 of last year.
A file of another version reads as absent and is read again.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date
from pathlib import Path

from congress import files
from congress.constants_congress import (
    CONGRESS_COMMITTEE_MEMBERS,
    CONGRESS_COMMITTEES,
    CONGRESS_HISTORICAL_MAX_AGE_SEC,
    CONGRESS_ROSTER_BASE,
    CONGRESS_ROSTER_CURRENT,
    CONGRESS_ROSTER_FILE,
    CONGRESS_ROSTER_HISTORICAL,
    CONGRESS_ROSTER_MAX_AGE_SEC,
    CONGRESS_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)
PARTY = {"Democrat": "D", "Republican": "R", "Independent": "I"}

_lock = threading.Lock()
_doc: dict | None = None


def path() -> Path:
    return files.folder() / CONGRESS_ROSTER_FILE


def _party(name: str | None) -> str:
    return PARTY.get(name or "", (name or "?")[:1].upper())


def slim(person: dict, current: bool, committees: dict[str, list[str]]) -> dict:
    """One legislator's record, as the page needs it."""
    term = person["terms"][-1]
    name = person.get("name", {})
    bio = person["id"]["bioguide"]
    chamber = "senate" if term.get("type") == "sen" else "house"
    district = term.get("district")
    return {"bioguide": bio, "name": name.get("official_full") or f"{name.get('first', '')} {name.get('last', '')}".strip(),
            "first": name.get("first", ""), "last": name.get("last", ""), "nickname": name.get("nickname", ""),
            "party": _party(term.get("party")), "caucus": term.get("caucus"), "state": term.get("state"),
            "district": district if chamber == "house" else None, "chamber": chamber, "current": current,
            "left": None if current else term.get("end"), "committees": committees.get(bio, [])}


def committee_names(committees: list[dict], membership: dict[str, list[dict]]) -> dict[str, list[str]]:
    """Full committees each member sits on (a four-letter thomas id; subcommittees are longer)."""
    names = {c.get("thomas_id"): c.get("name") for c in committees}
    out: dict[str, list[str]] = {}
    for cid, people in membership.items():
        if len(cid) != 4 or cid not in names:
            continue
        for p in people:
            if p.get("bioguide"):
                out.setdefault(p["bioguide"], []).append(names[cid])
    return out


def load() -> dict:
    """The kept roster (memory first, then the file); an empty one when none is kept."""
    global _doc
    with _lock:
        if _doc is not None:
            return _doc
    doc = {"schema_version": CONGRESS_SCHEMA_VERSION, "read_at": None, "historical_read_at": None, "members": []}
    try:
        kept = json.loads(path().read_text(encoding="utf-8"))
        if isinstance(kept, dict) and kept.get("schema_version") == CONGRESS_SCHEMA_VERSION:
            doc = kept
    except FileNotFoundError:  # maintainer: allow-swallow nothing kept yet: the reader reads it on its first turn
        pass
    except (OSError, ValueError) as exc:
        logger.warning("congress: %s could not be read (%s); read again", CONGRESS_ROSTER_FILE, exc)
    with _lock:
        _doc = doc
    return doc


def members() -> list[dict]:
    return load()["members"]


def by_bioguide() -> dict[str, dict]:
    return {m["bioguide"]: m for m in members()}


def _save(doc: dict) -> None:
    global _doc
    target = path()
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, target)
    with _lock:
        _doc = doc


def due(now: float) -> bool:
    read_at = load().get("read_at")
    return read_at is None or now - read_at >= CONGRESS_ROSTER_MAX_AGE_SEC


def historical_due(now: float) -> bool:
    at = load().get("historical_read_at")
    return at is None or now - at >= CONGRESS_HISTORICAL_MAX_AGE_SEC


def refresh(net, now: float, *, historical: bool = False) -> int:
    """Read the current members (and, when asked, who left since January 1 of last year); keep them. The count."""
    get = lambda name: net.get(CONGRESS_ROSTER_BASE + name).json()  # noqa: E731
    current = get(CONGRESS_ROSTER_CURRENT)
    committees = committee_names(get(CONGRESS_COMMITTEES), get(CONGRESS_COMMITTEE_MEMBERS))
    found = [slim(p, True, committees) for p in current]
    doc = dict(load())
    left = [m for m in doc.get("members", []) if not m.get("current")]
    if historical:
        since = date(date.fromtimestamp(now).year - 1, 1, 1).isoformat()
        past = get(CONGRESS_ROSTER_HISTORICAL)
        left = [slim(p, False, {}) for p in past if (p["terms"][-1].get("end") or "") >= since]
        doc["historical_read_at"] = now
    seated = {m["bioguide"] for m in found}
    doc.update(members=found + [m for m in left if m["bioguide"] not in seated], read_at=now)
    _save(doc)
    return len(doc["members"])


def reset_for_tests() -> None:
    global _doc
    with _lock:
        _doc = None
