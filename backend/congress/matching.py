"""A filer, as a report names them, matched to a member of Congress (ADR 066). Pure.

House reports name the filer by first and last name and ``StateDst`` (``CA31``, ``AK00`` at large); the Senate by
first and last name (``"Justice, II"``, ``"McConnell, Jr."``). A member is matched within the chamber by last name --
one or two words, so "April McClain Delaney" finds "McClain Delaney" -- then, when more than one fits, by the House
district and the first name (or nickname). Former members count, so a filer who left is still matched; a current
member wins a tie. No match is None: the page shows the name as filed.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

SUFFIX = re.compile(r",?\s*(jr\.?|sr\.?|ii|iii|iv)$", re.I)


def norm(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", ascii_name)


def _last_keys(first: str, last: str) -> set[str]:
    words = f"{first} {SUFFIX.sub('', last.strip())}".split()
    keys = {norm(SUFFIX.sub("", last.strip()))}
    if words:
        keys.add(norm(words[-1]))
    if len(words) >= 2:
        keys.add(norm(" ".join(words[-2:])))
    keys.discard("")
    return keys


def _first_fits(first: str, member: dict) -> bool:
    want = norm(first)[:3]
    if not want:
        return False
    return any(norm(member.get(k) or "")[:3] == want for k in ("first", "nickname"))


def _pick(cands: list[dict], first: str, district: int | None) -> str | None:
    if len(cands) > 1 and district is not None:
        cands = [c for c in cands if c.get("district") == district] or cands
    if len(cands) > 1:
        cands = [c for c in cands if _first_fits(first, c)] or cands
    if len(cands) > 1:
        cands = [c for c in cands if c.get("current")] or cands
    return cands[0]["bioguide"] if len(cands) == 1 else None


def house(members: Iterable[dict], first: str, last: str, state_dst: str) -> str | None:
    state = (state_dst or "")[:2].upper()
    digits = (state_dst or "")[2:]
    district = int(digits) if digits.isdigit() else None
    keys = _last_keys(first, last)
    cands = [m for m in members if m["chamber"] == "house" and m.get("state") == state and norm(m["last"]) in keys]
    return _pick(cands, first, district)


def senate(members: Iterable[dict], first: str, last: str) -> str | None:
    keys = _last_keys(first, last)
    cands = [m for m in members if m["chamber"] == "senate" and norm(m["last"]) in keys]
    return _pick(cands, first, None)
