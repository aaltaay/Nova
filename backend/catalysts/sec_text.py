"""What an SEC filing says: the press release an 8-K / 6-K carries, reduced to a headline (ADR 024).

Shared by the live catalyst feed (``catalysts/feed.py``) and the research backfill
(``research/catalysts/fetch_edgar.py``) so a filing reads the same in both. Pure apart from
``release_text``, which takes the fetch as an argument.
"""
from __future__ import annotations

import html
import re
from typing import Callable

PRESS_FORMS = frozenset({"8-K", "6-K"})
KEEP_FORMS = PRESS_FORMS | {"8-K/A", "6-K/A", "424B1", "424B3", "424B4", "424B5", "S-1", "F-1", "S-3", "F-3",
                            "425", "8-A12B", "SC TO-T", "SC 14D9", "DEFM14A", "10-Q", "10-K", "20-F", "S-4", "F-4"}
ITEM_NAMES = {
    "1.01": "Material agreement", "1.02": "Agreement terminated", "1.03": "Bankruptcy", "2.01": "Acquisition completed",
    "2.02": "Results of operations", "2.03": "Financial obligation", "3.01": "Delisting notice",
    "3.02": "Unregistered equity sale", "3.03": "Rights modified", "5.01": "Change in control",
    "5.02": "Officer / director change", "5.03": "Charter / bylaws (e.g. reverse split)", "5.07": "Shareholder vote",
    "7.01": "Regulation FD", "8.01": "Other events", "9.01": "Exhibits",
}
EXHIBIT_RE = re.compile(r"(ex|exhibit|dex)[-_ ]?99", re.I)
_BLOCK_RE = re.compile(r"<\s*(br|/p|/div|/tr|/h[1-6]|/li|/td)\b[^>]*>", re.I)
_BOILER_RE = re.compile(r"^(ex(hibit)?[- ]?99|for immediate release|press release|news release|source:|contact|"
                        r"investor|media|nasdaq:|nyse|page \d|\(?[a-z .]+,? ?(inc|corp|ltd)\.?\)?$)|"
                        r"pursuant to|securities exchange act|report of foreign private issuer|form (6|8)-k|"
                        r"commission file|indicate by check mark|washington, d\.?c|united states securities|"
                        r"current report|date of report|incorporated by reference|forward-looking|"
                        r"for the month of|commission file number|address of principal|name of registrant|"
                        r"translation of registrant|exact name|specified in its charter", re.I)
_LEAD_VERB_RE = re.compile(r"^(announces|agrees|reports|secures|receives|enters|signs|completes|launches|regains|"
                           r"closes|prices|expands|awarded|wins|partners|provides|to acquire|acquires)\b", re.I)
_DATELINE_RE = re.compile(r"^[A-Z][A-Za-z .,'-]+,\s+[A-Z][a-z]+\.? \d{1,2},? \d{4}")
# A headline line ending on one of these was cut by the layout, not finished ("... HCLP Debt and").
_CONTINUES = frozenset({"and", "or", "of", "to", "the", "for", "with", "in", "on", "a", "an", "&", "its", "at", "by",
                        "from", "as", "into", "over", "their", "new"})
_HEADLINE_MAX_WORDS = 45
_ITEM_TEXT_RE = re.compile(r"Item\s+[1-8]\.0\d.{0,1400}")
_OPENING_RE = re.compile(r"[^.]{0,200}\b(announce[sd]?|today|reported|entered into)\b.{0,1200}", re.I)


def text_of(raw: str) -> list[str]:
    """A filing document's visible lines."""
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = _BLOCK_RE.sub("\n", raw)
    raw = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return [re.sub(r"\s+", " ", ln).strip() for ln in raw.splitlines() if ln.strip()]


def headline(lines: list[str]) -> tuple[str | None, str]:
    """The release's headline (first real sentence-length line) and its opening text."""
    title = None
    for k, ln in enumerate(lines[:80]):
        words = ln.split()
        if len(words) < 3 or len(words) > _HEADLINE_MAX_WORDS or _BOILER_RE.search(ln) or _DATELINE_RE.match(ln):
            continue
        prev = lines[k - 1] if k else ""
        if _LEAD_VERB_RE.match(ln) and 0 < len(prev.split()) <= 6 and not _BOILER_RE.search(prev):
            ln = f"{prev} {ln}"  # the company name sat on its own line
        nxt = lines[k + 1] if k + 1 < len(lines) else ""
        joined = ln.split()
        wrapped = len(joined) < 8 or joined[-1].lower() in _CONTINUES
        if (wrapped and nxt and len(nxt.split()) <= 30 and len(joined) + len(nxt.split()) <= _HEADLINE_MAX_WORDS
                and not _BOILER_RE.search(nxt) and not _DATELINE_RE.match(nxt)):
            ln = f"{ln} {nxt}"  # the headline wrapped
        if len(ln.split()) < 5:
            continue
        title = ln
        break
    body = " ".join(lines)
    m = _OPENING_RE.search(body)
    return title, (m.group(0) if m else body[:1400])


def pick_document(names: list[str], primary: str | None) -> tuple[str | None, bool]:
    """The press-release exhibit when there is one (else the primary document), and whether it is an exhibit."""
    docs = [n for n in names if n.lower().endswith((".htm", ".html", ".txt"))]
    ex = sorted(n for n in docs if EXHIBIT_RE.search(n))
    return (ex[0], True) if ex else (primary or None, False)


def release_text(form: str, names: list[str], primary: str | None,
                 fetch_text: Callable[[str], str]) -> tuple[str | None, str]:
    """(headline, opening) of an 8-K / 6-K. An 8-K without a release keeps its Item text, never its cover."""
    doc, is_exhibit = pick_document(names, primary)
    if not doc:
        return None, ""
    lines = text_of(fetch_text(doc))
    if not is_exhibit and form.startswith("8-K"):
        m = _ITEM_TEXT_RE.search(" ".join(lines))
        return None, (m.group(0) if m else "")
    return headline(lines)


def describe(form: str, items: str | None) -> str:
    """``8-K: Material agreement; Regulation FD`` -- the form and its Item names."""
    codes = [c.strip() for c in (items or "").split(",") if c.strip() and c.strip() != "9.01"]
    names = "; ".join(ITEM_NAMES.get(c, c) for c in codes)
    return f"{form}{': ' + names if names else ''}"


def title_for(form: str, items: str | None, head: str | None) -> str:
    """The stored title the classifier reads: ``<form: items> | <release headline>``."""
    return f"{describe(form, items)} | {head}" if head else describe(form, items)
