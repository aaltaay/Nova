"""A fund names what it tracks (ADR 028 amendment 4, 2026-10-26). Pure: no I/O, no clock.

A symbol Yahoo calls a fund (``quote_type`` ``ETF``, which Yahoo also gives ETNs) moves with what it tracks, not on
company news: BRZD +76% and BZQ +50% on 2026-10-26 were inverse Brazil funds the day after Lula won Brazil's
runoff, and the read called them unexplained. ``from_name`` reads the fund's own name -- inverse or not, the
leverage, what it tracks -- and ``cause_label`` says what the fund is and that it moves with or against what it
tracks. It never says what that market did: a fund's own move can come from a payout or a split, not its market
(held-back set 4: AVL -13% on 2025-12-10 while AVGO rose 1.6%). A name it cannot read keeps what it can: "Fund"
with no tracks, 1x when no leverage is written, "Leveraged" with no number when the name gives none.

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
_SHORT_DURATION = re.compile(r"\bshort[- ](term|duration|maturity|dated|treasury|bond|municipal|muni|government)\b",
                             re.I)
# A hedge fund's style, never a side: "Long/Short Equity", "Long-Short".
_LONG_SHORT = re.compile(r"\blong\s*[/-]\s*short\b", re.I)
_LEVERAGE_WORD = re.compile(r"\bleveraged?\b", re.I)
# "2X Long ON Daily", "Daily Target 2X Short AMD": the side words any case, the ticker only in capitals.
_SINGLE_STOCK = re.compile(r"(?i:\b\d+(?:\.\d+)?\s*x\s+(?:long|short|inverse|bull|bear))\s+([A-Z]{1,5})\b")
# The legal tail of a listing's name says nothing about what the fund tracks: "... ETNs due February 17, 2045",
# "... ETF Common Shares of Beneficial Interest Shares".
_LEGAL_TAIL = re.compile(r"\b(due\b|common shares of beneficial interest|shares of beneficial interest|"
                         r"units of beneficial interest|of beneficial interest)", re.I)


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
    # "Short" is the side ("Defiance Daily Target 2X Short AMD", "ProShares Short QQQ", "YieldMax Short COIN Option
    # Income Strategy" -- short through options), never a bond's duration nor a long/short hedge style.
    if _SHORT.search(name) and not _SHORT_DURATION.search(name) and not _LONG_SHORT.search(name):
        return SIDE_INVERSE
    return SIDE_LONG


def _leverage(name: str) -> float | None:
    """The written multiple; 1 when the name writes none; None when it says "Leveraged" but not how much
    ("Defiance Leveraged Long Income MSTR ETF" runs about 1.5-2x)."""
    m = _MULTIPLE.search(name)
    if m:
        return float(m.group(1))
    low = name.lower()
    for word, multiple in MOVE_FUND_MULTIPLE_WORDS:
        if re.search(rf"\b{word}\b", low):
            return multiple
    return None if _LEVERAGE_WORD.search(name) else 1.0


def _tracks(name: str) -> str | None:
    # A single-stock fund writes its ticker in capitals right after its side: "2X Long ON Daily", "2X Long BULL"
    # -- tickers that are also plain words ("on", "bull") would be dropped below.
    single = _SINGLE_STOCK.search(name)
    if single:
        return single.group(1)
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
    tail = _LEGAL_TAIL.search(text)
    text = text[:tail.start()].strip() if tail else text
    return {"name": raw or None, "side": _side(text), "leverage": _leverage(text), "tracks": _tracks(text) if text else None}


def describe(fund: dict[str, Any]) -> str:
    """"Inverse 2x fund on Brazil", "Fund on Bitcoin", "Leveraged 3x fund", "Leveraged fund on MSTR"."""
    lev = fund.get("leverage")
    multiple = f"{lev:g}x " if lev not in (None, 1.0) else ("leveraged " if lev is None else "")
    side = "Inverse " if fund.get("side") == SIDE_INVERSE else ("Leveraged " if lev not in (None, 1.0) else "")
    what = f"{side}{multiple}fund"
    what = what[:1].upper() + what[1:]
    return f"{what} on {fund['tracks']}" if fund.get("tracks") else what


def cause_label(fund: dict[str, Any], change: float) -> str:
    """"Inverse 2x fund on Brazil: up 50.3%, moves against Brazil" -- what the fund is, never what its market did:
    a fund's own move can come from something else (AVL -13% on 2025-12-10 while AVGO rose 1.6%)."""
    what = fund.get("tracks") or "what it tracks"
    way = "against" if fund.get("side") == SIDE_INVERSE else "with"
    return f"{describe(fund)}: {'up' if change > 0 else 'down'} {abs(change) * 100:.1f}%, moves {way} {what}"

