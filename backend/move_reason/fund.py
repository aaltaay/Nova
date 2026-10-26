"""A fund names what it tracks (ADR 028 amendment 4, 2026-10-26). Pure: no I/O, no clock.

A symbol Yahoo calls a fund (``quote_type`` ``ETF``, which Yahoo also gives ETNs) moves with what it tracks, not on
company news: BRZD +76% and BZQ +50% on 2026-10-26 were inverse Brazil funds the day after Lula won Brazil's
runoff, and the read called them unexplained. ``from_name`` reads the fund's own name -- inverse or not, the
leverage, what it tracks -- and ``cause_label`` says which way the tracked market went from the fund's move and
side: a direction, never an implied percentage (a daily-reset fund's move over days is not its leverage times the
market's). A name it cannot read keeps what it can: "Fund" with no tracks, 1x when no leverage is written.

Owner: this module (no state).
"""
from __future__ import annotations

import re
from typing import Any

from constants_move_reason import (
    MOVE_FUND_DROP_WORDS,
    MOVE_FUND_ISSUERS,
    MOVE_FUND_MULTIPLE_WORDS,
    MOVE_FUND_QUOTE_TYPES,
    MOVE_FUND_TRACKS_MAX_WORDS,
)

SIDE_LONG = "long"
SIDE_INVERSE = "inverse"

# "-3x", "-1.5X": a minus sign before the multiple is inverse whatever the words say.
_NEG_MULTIPLE = re.compile(r"(?<![\w.])-\s*\d+(?:\.\d+)?\s*x\b", re.I)
_MULTIPLE = re.compile(r"(?<![\w.])-?(\d+(?:\.\d+)?)\s*x\b", re.I)
_INVERSE_WORDS = re.compile(r"\b(inverse|bear|ultrashort)\b", re.I)
_SHORT = re.compile(r"\bshort\b", re.I)
# "Short" as a bond's duration, never a side: "iShares Short Treasury Bond ETF" is long.
_SHORT_DURATION = re.compile(r"\bshort[- ](term|duration|maturity|dated|treasury|bond|corporate|high[- ]yield|"
                             r"municipal|muni|government)\b", re.I)
_LEVERED = re.compile(r"\b(daily|ultra\w*|leveraged?|\d+(?:\.\d+)?\s*x)\b", re.I)


def is_fund(quote_type: str | None) -> bool | None:
    """True / False from Yahoo's ``quote_type``; None while it is unknown."""
    if not quote_type:
        return None
    return quote_type.upper() in MOVE_FUND_QUOTE_TYPES


def _norm(name: str) -> str:
    return name.replace("×", "x").replace("–", "-").replace("−", "-")


def _side(name: str) -> str:
    if _NEG_MULTIPLE.search(name) or _INVERSE_WORDS.search(name):
        return SIDE_INVERSE
    # "Short" counts on a levered fund ("Defiance Daily Target 2X Short AMD", "ProShares Short QQQ" -- ProShares'
    # plain inverse line), never as a bond's duration.
    if _SHORT.search(name) and not _SHORT_DURATION.search(name):
        if _LEVERED.search(name) or re.search(r"\bproshares\s+short\b", name, re.I):
            return SIDE_INVERSE
    return SIDE_LONG


def _leverage(name: str) -> float:
    m = _MULTIPLE.search(name)
    if m:
        return float(m.group(1))
    low = name.lower()
    for word, multiple in MOVE_FUND_MULTIPLE_WORDS:
        if re.search(rf"\b{word}\b", low):
            return multiple
    return 1.0


def _tracks(name: str) -> str | None:
    text = _MULTIPLE.sub(" ", name)
    low = text.lower()
    for issuer in sorted(MOVE_FUND_ISSUERS, key=len, reverse=True):
        low = re.sub(rf"(?<![\w-]){re.escape(issuer)}(?![\w-])", " ", low)
    words = [w for w in re.split(r"[\s,()]+", low) if w]
    keep = [w for w in words if w.strip(".") not in MOVE_FUND_DROP_WORDS and not re.fullmatch(r"[-+]?\d*\.?\d+x?", w)]
    if not keep or len(keep) > MOVE_FUND_TRACKS_MAX_WORDS:
        return None
    # The name's own spelling: "Brazil", "AMD", "Semiconductor".
    spelled = {w.lower(): w for w in re.split(r"[\s,()]+", text) if w}
    return " ".join(spelled.get(w, w) for w in keep)


def from_name(name: str | None) -> dict[str, Any]:
    """``{name, side, leverage, tracks}`` read from a fund's name; ``tracks`` None when the name does not say."""
    raw = (name or "").strip()
    text = _norm(raw)
    return {"name": raw or None, "side": _side(text), "leverage": _leverage(text), "tracks": _tracks(text) if text else None}


def describe(fund: dict[str, Any]) -> str:
    """"Inverse 2x fund on Brazil", "Fund on Bitcoin", "Leveraged 3x fund"."""
    lev = fund.get("leverage") or 1.0
    multiple = f"{lev:g}x " if lev != 1.0 else ""
    side = "Inverse " if fund.get("side") == SIDE_INVERSE else ("Leveraged " if lev != 1.0 else "")
    what = f"{side}{multiple}fund"
    what = what[:1].upper() + what[1:]
    return f"{what} on {fund['tracks']}" if fund.get("tracks") else what


def cause_label(fund: dict[str, Any], change: float) -> str:
    """"Inverse 2x fund on Brazil: up 50.3%, so Brazil fell" -- the direction only."""
    up = change > 0
    tracked_up = up if fund.get("side") != SIDE_INVERSE else not up
    what = fund.get("tracks") or "what it tracks"
    return f"{describe(fund)}: {'up' if up else 'down'} {abs(change) * 100:.1f}%, so {what} {'rose' if tracked_up else 'fell'}"
