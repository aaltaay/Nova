"""Reading a stock split out of an SEC filing and holding it against the price (#772) -- pure.

Massive's split list misses some splits, and a missed reverse split reads as a giant overnight
mover on a rebuilt board (PHGE on 2026-09-09: +925%). This module decides, from a filing's text
and the overnight prices alone, whether the filing proves a split took effect between two
sessions. No I/O: ``confirm_splits.py`` reads the flat files and fetches the filings.

What proves a split (AGENTS.md section 3, "Splits a rebuild confirms from SEC filings"):

* a passage about a reverse / forward split or a share consolidation states a ratio outside any
  range -- "a ratio in the range of 1-for-5 to 1-for-50" proves nothing;
* the split-adjusted open sits in a band around the prior close; several ratios in one filing (an
  earlier split recalled) leave the one the price agrees with;
* a date the filing names beside "effective" / "split-adjusted" / "begin trading" falls after the
  prior session and by the session. With no such date the band is tighter; a filing that names
  only other dates is refused.

Ratios use Massive's convention: ``split_from`` old shares become ``split_to`` new ones, so a
1-for-10 reverse split is 10 / 1 and a 2-for-1 forward split is 1 / 2.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from lb_config import SPLIT_ADJUSTED_BAND, SPLIT_ADJUSTED_BAND_NO_DATE

# ── Numbers, written as digits or words ─────────────────────────────────────

_SMALL = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1000}
_WORD = "|".join(sorted([*_SMALL, *_TENS, *_SCALES], key=len, reverse=True))
_NUM = rf"(?:\d{{1,3}}(?:,\d{{3}})+|\d+|(?:{_WORD})(?:[\s-]+(?:and[\s-]+)?(?:{_WORD}))*)"
_PAREN = r"(?:\s*\(\s*\d[\d,]*\s*\))?"     # "one (1)", "ten (10)"
_MAX_RATIO = 1000


def number(token: str) -> int | None:
    """``"25"``, ``"1,000"``, ``"twenty-five"``, ``"one hundred fifty"`` -> int; None when not a number."""
    token = token.strip().lower()
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+|\d+", token):
        return int(token.replace(",", ""))
    total, current = 0, 0
    for word in re.split(r"[\s-]+", token):
        if word == "and" or not word:
            continue
        if word in _SMALL:
            current += _SMALL[word]
        elif word in _TENS:
            current += _TENS[word]
        elif word in _SCALES:
            current = max(current, 1) * _SCALES[word]
            if _SCALES[word] == 1000:
                total, current = total + current, 0
        else:
            return None
    value = total + current
    return value or None


# ── What a passage says ─────────────────────────────────────────────────────

_REVERSE_RE = re.compile(
    r"\breverse\s+(?:stock\s+|share\s+)?split|\bshare\s+consolidation|\bconsolidat\w*\s+(?:of\s+)?"
    r"(?:its\s+|the\s+|our\s+|all\s+)?(?:issued\s+(?:and\s+outstanding\s+)?)?(?:ordinary\s+|common\s+)?shares",
    re.I)
_FORWARD_RE = re.compile(r"\bforward\s+(?:stock\s+|share\s+)?split|\b(?:stock|share)\s+split\b", re.I)
_RANGE_RE = re.compile(
    r"\b(?:range|ranging|between|up\s+to|not\s+(?:less|more|greater|fewer)\s+than|no\s+(?:less|more|greater|fewer)\s+than|"
    r"not\s+to\s+exceed|at\s+least|at\s+most|maximum|minimum|any\s+whole\s+number|to\s+be\s+determined|"
    r"determined\s+by\s+the\s+board|(?:at|in)\s+the\s+(?:sole\s+)?discretion)\b", re.I)
_EFFECTIVE_RE = re.compile(
    r"\b(?:effective|effectiveness|split[-\s]adjusted|post[-\s]split|begin(?:s|ning)?\s+trading|"
    r"commenc\w*\s+(?:trading|with\s+the\s+market\s+open)|market\s+open|opening\s+of\s+trading|ex-date)\b", re.I)
# "X-for-Y": X new shares for Y old ones.
_FOR_RE = re.compile(rf"\b(?P<x>{_NUM}){_PAREN}[\s-]+for[\s-]+(?P<y>{_NUM}){_PAREN}", re.I)
# "X (new) share(s) for each / every Y (old) shares".
_EVERY_RE = re.compile(
    rf"\b(?P<x>{_NUM}){_PAREN}\s+(?:new\s+|post-split\s+)?(?:ordinary\s+|common\s+)?shares?\b[^.;]{{0,80}}?"
    rf"\bfor\s+(?:each|every)\s+(?P<y>{_NUM}){_PAREN}", re.I)
# "each / every Y shares ... combined into X".
_INTO_RE = re.compile(
    rf"\b(?:each|every)\s+(?P<y>{_NUM}){_PAREN}\s+(?:issued\s+and\s+outstanding\s+|pre-split\s+|old\s+)?"
    rf"(?:ordinary\s+|common\s+)?shares?\b[^.;]{{0,160}}?\b(?:combined|consolidated|converted|reclassified|"
    rf"changed|exchanged)\s+into\s+(?P<x>{_NUM}){_PAREN}", re.I)
# "a ratio of 1:10", "on a 1:10 basis", "1:10 reverse split": direction from the passage's kind.
_COLON_RE = re.compile(
    r"(?:ratio\s+of\s+|on\s+an?\s+)(?P<a>\d{1,4})\s*:\s*(?P<b>\d{1,4})\b(?!\s*[ap]\.?\s?m)|"
    r"\b(?P<c>\d{1,4})\s*:\s*(?P<d>\d{1,4})\s+(?:reverse|forward|share|stock|consolidation|ratio|basis)\b", re.I)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
    "nov": 11, "dec": 12,
}
_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|" \
         r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DATE_MDY = re.compile(rf"\b(?P<m>{_MONTH})\.?\s+(?P<d>\d{{1,2}}),?\s+(?P<y>(?:19|20)\d{{2}})\b", re.I)
_DATE_DMY = re.compile(rf"\b(?P<d>\d{{1,2}})\s+(?P<m>{_MONTH})\.?,?\s+(?P<y>(?:19|20)\d{{2}})\b", re.I)
_ABBREV = {"inc", "corp", "ltd", "co", "no", "nos", "u.s", "a.m", "p.m", "mr", "ms", "dr", "st", "jan", "feb",
           "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "s.a", "n.v", "plc"}
_PASSAGE_BEFORE, _PASSAGE_AFTER = 600, 1500


def sentences(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence: a period then a capital starts a new one, except after an abbreviation."""
    out, start = [], 0
    for m in re.finditer(r"[.!?;]\s+(?=[A-Z“\"])", text):
        word = re.search(r"([A-Za-z.]+)$", text[start:m.start()])
        if m.group(0)[0] == "." and word and word.group(1).lower().rstrip(".") in _ABBREV:
            continue
        out.append((start, m.end()))
        start = m.end()
    if start < len(text):
        out.append((start, len(text)))
    return out


@dataclass(frozen=True)
class Mention:
    """A split ratio a filing states: ``split_from`` old shares become ``split_to`` new ones.

    ``dates`` are the dates in its own sentence: a ratio stated beside a date that is not the
    split's ("a 1-for-19 reverse split on November 25, 2025") is about another split.
    """

    split_from: int
    split_to: int
    text: str
    dates: tuple[date, ...] = ()


def _passages(text: str) -> list[tuple[int, int, str]]:
    """(start, end, kind) around each place the filing names a split or a share consolidation."""
    out = []
    for kind, pattern in (("reverse", _REVERSE_RE), ("forward", _FORWARD_RE)):
        for m in pattern.finditer(text):
            if kind == "forward" and _REVERSE_RE.search(text, max(0, m.start() - 20), m.end()):
                continue   # "reverse stock split" also reads as "stock split"
            out.append((max(0, m.start() - _PASSAGE_BEFORE), min(len(text), m.end() + _PASSAGE_AFTER), kind))
    return out


def _sentence_at(spans: Sequence[tuple[int, int]], pos: int) -> tuple[int, int]:
    for a, b in spans:
        if a <= pos < b:
            return a, b
    return 0, 0


def mentions(text: str) -> list[Mention]:
    """Every split ratio stated near split language, outside a range."""
    text = re.sub(r"\s+", " ", text)
    spans = sentences(text)
    out: dict[tuple[int, int], Mention] = {}
    for start, end, kind in _passages(text):
        for pattern in (_FOR_RE, _EVERY_RE, _INTO_RE, _COLON_RE):
            for m in pattern.finditer(text, start, end):
                a, b = _sentence_at(spans, m.start())
                if _RANGE_RE.search(text, a, b):
                    continue   # a range the board may pick from proves no split
                if pattern is _COLON_RE:
                    x, y = number(m.group("a") or m.group("c")), number(m.group("b") or m.group("d"))
                    if x is None or y is None:
                        continue
                    old, new = (max(x, y), min(x, y)) if kind == "reverse" else (min(x, y), max(x, y))
                else:
                    new, old = number(m.group("x")), number(m.group("y"))
                    if new is None or old is None:
                        continue
                if old == new or not (1 <= old <= _MAX_RATIO and 1 <= new <= _MAX_RATIO):
                    continue
                if (kind == "reverse") != (old > new):
                    continue   # "1-for-10" read as a forward split, or "2-for-1" as a reverse one
                out.setdefault((old, new), Mention(old, new, text[a:b].strip()[:300], _dates_in(text, a, b)))
    return list(out.values())


def _date(m: re.Match) -> date | None:
    try:
        return date(int(m.group("y")), _MONTHS[m.group("m")[:3].lower()], int(m.group("d")))
    except (KeyError, ValueError):
        return None


def _dates_in(text: str, a: int, b: int) -> tuple[date, ...]:
    found = {d for pattern in (_DATE_MDY, _DATE_DMY) for m in pattern.finditer(text, a, b) if (d := _date(m))}
    return tuple(sorted(found))


def effective_dates(text: str) -> list[date]:
    """Dates in sentences that say when the split takes effect or trades split-adjusted."""
    text = re.sub(r"\s+", " ", text)
    spans = sentences(text)
    out: set[date] = set()
    for start, end, _kind in _passages(text):
        for a, b in spans:
            if b <= start or a >= end or not _EFFECTIVE_RE.search(text, a, b):
                continue
            out.update(_dates_in(text, a, b))
    return sorted(out)


# ── The decision ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Verdict:
    """What one filing proves about the overnight move from ``prev_session`` to ``session``."""

    confirmed: bool
    reason: str
    split_from: int | None = None
    split_to: int | None = None
    ratio_text: str | None = None
    date_match: bool | None = None
    adjusted_ratio: float | None = None
    names_split: bool = False


def judge(text: str, *, prev_session: date, session: date, prev_close: float, open_: float) -> Verdict:
    """Does this filing prove a split took effect after ``prev_session`` and by ``session``?"""
    names_split = bool(_REVERSE_RE.search(text) or _FORWARD_RE.search(text))
    found = mentions(text)
    if not found:
        reason = "names a split but states no ratio outside a range" if names_split else "names no split"
        return Verdict(False, reason, names_split=names_split)
    dates = effective_dates(text)
    in_window = [d for d in dates if prev_session < d <= session]
    if dates and not in_window:
        named = ", ".join(d.isoformat() for d in dates)
        return Verdict(False, f"names {named} as effective, not after {prev_session} and by {session}", names_split=True)
    low, high = SPLIT_ADJUSTED_BAND if in_window else SPLIT_ADJUSTED_BAND_NO_DATE

    def dated_here(mention: Mention) -> bool:
        return any(prev_session < d <= session for d in mention.dates)

    # A ratio beside other dates only is about another split (an earlier one recalled).
    current = [m for m in found if not m.dates or dated_here(m)]
    fits = []
    for mention in current:
        adjusted = open_ / (prev_close * mention.split_from / mention.split_to)
        if low <= adjusted <= high:
            fits.append((mention, adjusted))
    if len(fits) > 1 and any(dated_here(m) for m, _ in fits):
        fits = [(m, adj) for m, adj in fits if dated_here(m)]   # the ratio dated on the session wins
    if not current:
        stated = ", ".join(f"{m.split_from}/{m.split_to} ({', '.join(d.isoformat() for d in m.dates)})" for m in found)
        return Verdict(False, f"every ratio stated is dated elsewhere: {stated}", names_split=True)
    if not fits:
        stated = ", ".join(f"{m.split_from}/{m.split_to}" for m in current)
        return Verdict(False, f"the price disagrees with {stated}", names_split=True)
    if len(fits) > 1:
        stated = ", ".join(f"{m.split_from}/{m.split_to}" for m, _ in fits)
        return Verdict(False, f"several ratios fit the price: {stated}", names_split=True)
    mention, adjusted = fits[0]
    return Verdict(True, "confirmed", mention.split_from, mention.split_to, mention.text,
                   True if in_window else None, round(adjusted, 4), names_split=True)


# ── Suspects and the days a split touches ───────────────────────────────────

@dataclass(frozen=True)
class Suspect:
    ticker: str
    prev_session: date
    session: date
    prev_close: float
    open: float
    price_ratio: float
    volume_ratio: float | None


def suspects(
    prev: Mapping[str, tuple[float, float, float]],
    cur: Mapping[str, tuple[float, float, float]],
    *,
    prev_session: date,
    session: date,
    universe: Iterable[str],
    listed: Mapping[str, Sequence[date]],
    up: float,
    down: float,
) -> list[Suspect]:
    """Overnight jumps (open over the prior close) no listed split explains. Rows are (open, close, volume)."""
    out = []
    for ticker in sorted(set(universe) & set(prev) & set(cur)):
        o, _c, v = cur[ticker]
        _po, pc, pv = prev[ticker]
        if pc <= 0 or o <= 0:
            continue
        ratio = o / pc
        if down < ratio < up:
            continue
        if any(prev_session < d <= session for d in listed.get(ticker, ())):
            continue
        out.append(Suspect(ticker, prev_session, session, pc, o, round(ratio, 4), round(v / pv, 4) if pv > 0 else None))
    return out


def affected_sessions(session: date, calendar: Sequence[date], traded: set[date], lookback: int) -> list[date]:
    """The rebuilt days a split on ``session`` changes: that day (its prior close) and the next
    ``lookback`` sessions the ticker traded (their RVOL lookback holds the sessions before it)."""
    if session not in calendar:
        return []
    i = calendar.index(session)
    later = [d for d in calendar[i + 1:i + 1 + lookback] if d in traded]
    return [session, *later]
