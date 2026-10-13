"""Which filings bring results out, read from their own words. Pure.

**6-K.** A foreign issuer files its results on Form 6-K, and so does every other announcement it makes; SEC's
submissions file names no item for a 6-K (MNDR's 6-K of 2026-03-12, its first-half results, reads ``6-K``
like its share issues). The cover document says what it is, after the Form 20-F / Form 40-F check boxes:
"today announced its unaudited financial results for the six months ended December 31, 2025", or an exhibit
index line "99.1 NIO Inc. Reports Unaudited Second Quarter 2026 Financial Results" / "Alibaba Group Announces
June Quarter 2026 Results".

**8-K Item 2.02** ("Results of Operations and Financial Condition") carries earnings releases, and also
vehicle deliveries (LCID 2026-10-05, "production and delivery totals"), restatements (BBAI 2025-03-18, with
Item 4.02), an offering's preliminary figures (ASTS 2025-01-22) and an acquisition's partial results (LUNR
2025-11-04, "certain financial results"). The section's own words say which.

A filing **reports results** when one of its opening sentences says results were reported, announced,
released or published with a word that makes them financial, or a press release on its results, or
furnishes interim financial statements -- and that sentence does not announce a date to come ("to Report ...
on September 1"), speak of a meeting's votes, restate, warn of results still being prepared (NIO's "Profit
Alert"), or give deliveries ("XPENG Announces Vehicle Delivery Results for July 2026"). It is
**preliminary** when that sentence says preliminary, estimated, certain or selected results. A cover that
only says a press release is attached (TSLA's "published the press release which is attached hereto as
Exhibit 99.1", or a 6-K's non-GAAP note) is **unknown** until its Exhibit 99.1's opening is read
(``read_exhibit``); an 8-K still unknown then is a weak release (``earnings.py``), since the Item 2.02 8-Ks
that only attach a press release were deliveries, an asset sale, layoffs, a financing, an acquisition and a
restructuring as often as results (TSLA, PLUG, SNAP, LCID, IONQ, FCEL, 2024-2026). Links are dropped before
reading: SNDL's "to Announce ... Financial Results on July 31" release ends in a URL that spells it out
without the "to".

The period is read from the same words ("three / six / nine / twelve months ended <date>", "quarter ended
<date>", "year ended <date>", a "second quarter 2026"), and the day the company says it happened ("On August
12, 2025, ...") as ``stated``.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime
from typing import Any

_COVER_END = re.compile(r"form\s*40-f", re.I)      # a 6-K cover's last check box line
_ITEM_202 = re.compile(r"\bitem\s*2\.02\.?\s*(?:results\s+of\s+operations\s+and\s+financial\s+condition\.?)?", re.I)
_COVER_SPAN = 20000          # the cover sits in the document's opening characters
_BODY_CHARS = 2500           # the subject is stated in the opening of the body
_SENTENCES = 12
_HEAD_SENTENCES = 3          # a document's title area: its opening sentences
# A sentence ends at . ; ! ? -- not after a company's "Inc." or "Ltd." -- before an exhibit number, or at an
# item heading or the signatures.
_SPLIT = re.compile(r"(?<=[.;!?])(?<!\bInc\.)(?<!\bCorp\.)(?<!\bLtd\.)(?<!\bCo\.)(?<!\bNo\.)(?<!\bU\.S\.)\s+"
                    r"|\s+(?=\b\d{2}\.\d\b)|\bSIGNATURES?\b|\bItem\s*\d\.\d{2}\b", re.I)
# What a cover's check boxes leave at the start of the first sentence: "☐ ", "o ", "¨ ".
_CHECK_BOX = re.compile(r"^(?:[☐☒¨ýox]\s+)+")

_VERB = (r"(?:reports?|reported|reporting|announc(?:es|ed|ing|ement(?:\s+of)?)|announce|releases?|released|"
         r"releasing|publish(?:es|ed|ing)?|posts?|posted|presents?|presented)")
_KIND = (r"(?:financial|operating|operational|earnings|interim|quarterly|annual|half[- ]year(?:ly)?|"
         r"semi[- ]annual|unaudited|audited|year[- ]end|full[- ]year|fiscal|first[- ]half|second[- ]half|quarter)")
_RESULTS = (
    re.compile(rf"\b{_VERB}\b[^.;]{{0,150}}?\b{_KIND}\b[^.;]{{0,60}}?\bresults\b", re.I),
    re.compile(rf"\b{_KIND}\b[^.;]{{0,40}}?\bfinancial results\b", re.I),
    re.compile(r"\b(?:press release|shareholder letter|letter to shareholders)\b[^.;]{0,80}?\b(?:financial\s+|"
               r"operating\s+)?results\b", re.I),
    re.compile(r"\bfinancial results\s+(?:of operations\s+)?for\b", re.I),
    re.compile(r"\b(?:unaudited|interim)\b[^.;]{0,30}?\b(?:condensed\s+)?(?:consolidated\s+)?financial\s+"
               r"(?:statements|information)\b", re.I),
)
_NOT = (
    re.compile(r"\b(?:will|to|plans? to|expects? to|intends? to|scheduled to|shall|to be)\s+(?:report|announce|"
               r"release|publish|host|hold|held|discuss)\b", re.I),
    re.compile(r"\b(?:date|dates|schedule)\b[^.;]{0,40}\b(?:of|for)\b[^.;]{0,60}\bresults\b", re.I),
    re.compile(r"\b(?:general|shareholders'?|annual|extraordinary|special)\s+meeting\b", re.I),
    re.compile(r"\bvoting results\b|\bboard meeting\b|\brestate|\bnon-reliance\b", re.I),
    re.compile(r"\bprofit (?:alert|warning)\b|\bpreparing\b|\bfinaliz\w*", re.I),
    re.compile(r"\bdeliver(?:y|ies)\s+(?:results|update|totals?|figures|numbers)\b|\bproduction\s+and\s+deliver\w*"
               r"|\bproduction,\s+deliveries\b", re.I),
)
_PRELIMINARY = re.compile(r"\b(?:preliminary|estimated)\b|\b(?:certain|selected)\s+(?:\w+\s+){0,2}results\b", re.I)
# An 8-K Item 2.02 that is about something else than the period's results.
_OTHER_202 = re.compile(r"\b(?:production|deliver(?:y|ies)|restate\w*|non-reliance|offering|investor presentation)\b",
                        re.I)
# A cover that says only that a press release is attached, or that it uses non-GAAP measures.
_ATTACHED = re.compile(r"\b(?:press release|exhibit 99)\b|not prepared in accordance with (?:u\.s\. )?generally "
                       r"accepted accounting principles|\bnon-gaap\b", re.I)

_WORDS = {"three": 3, "six": 6, "nine": 9, "twelve": 12}
_ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_DATE = r"([A-Z][a-z]{2,8}\.?\s+\d{1,2},?\s+\d{4})"
_QUARTER_ENDED = re.compile(rf"\bquarter\s+(?:and\s+(?:six|nine|twelve)\s+months\s+)?ended\s+{_DATE}", re.I)
# "the three and six months ended June 30": the quarter is the period the results are for.
_MONTHS_ENDED = re.compile(rf"\b(three|six|nine|twelve)(?:\s+and\s+(three|six|nine|twelve))?[- ]months?\s+"
                           rf"(?:periods?\s+)?ended\s+{_DATE}", re.I)
_HALF_ENDED = re.compile(rf"\bhalf[- ]year\s+ended\s+{_DATE}", re.I)
_YEAR_ENDED = re.compile(rf"\b(?:fiscal\s+)?year\s+ended\s+{_DATE}", re.I)
_QUARTER_NAMED = re.compile(r"\b(first|second|third|fourth)\s+(?:fiscal\s+)?quarter\s+(?:of\s+)?(?:fiscal\s+"
                            r"(?:year\s+)?)?(\d{4})\b", re.I)
_STATED = re.compile(rf"\bOn\s+{_DATE}", re.I)


def text_of(document: bytes | str) -> str:
    """A document's words: scripts and styles dropped, tags removed, entities read, spaces collapsed."""
    raw = document.decode("utf-8", "replace") if isinstance(document, bytes) else document
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    words = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    words = re.sub(r"\bhttps?://\S+|\bwww\.\S+", " ", words)
    return re.sub(r"\s+", " ", words).strip()


def cover_body(text: str) -> str:
    """A 6-K's own words: after the cover's Form 40-F check box, its opening characters."""
    marks = list(_COVER_END.finditer(text[:_COVER_SPAN]))
    start = marks[-1].end() if marks else 0
    return text[start:start + _BODY_CHARS]


def item_202_body(text: str) -> str:
    """An 8-K's Item 2.02 section, its heading dropped; empty when the document has none."""
    hit = _ITEM_202.search(text)
    return text[hit.end():hit.end() + _BODY_CHARS] if hit else ""


def _date(raw: str) -> date | None:
    cleaned = re.sub(r"\s+", " ", raw.replace(".", "").replace(",", ""))
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def period(text: str) -> dict[str, Any]:
    """The period the words name: ``months`` and ``end`` from an "... ended <date>" phrase, and ``named`` --
    "2026 Q2" -- when the company names its quarter and year."""
    out: dict[str, Any] = {"months": None, "end": None, "named": None}
    named = _QUARTER_NAMED.search(text)
    if named:
        out["named"] = f"{named.group(2)} Q{_ORDINAL[named.group(1).lower()]}"
    for pattern, months in ((_QUARTER_ENDED, 3), (_MONTHS_ENDED, None), (_HALF_ENDED, 6), (_YEAR_ENDED, 12)):
        hit = pattern.search(text)
        end = _date(hit.group(hit.lastindex)) if hit else None
        if end is None:
            continue
        out["months"] = months or min(_WORDS[w.lower()] for w in hit.groups()[:2] if w)
        out["end"] = end
        break
    if named:
        # "second quarter and six months ended June 30, 2026": the quarter ends on that date too. A year
        # ended is a comparison, never the named quarter's end.
        out["end"] = out["end"] if out["months"] in (3, 6, 9) else None
        out["months"] = 3
    return out


def _sentences(text: str) -> list[str]:
    return [_CHECK_BOX.sub("", s.strip()) for s in _SPLIT.split(text) if s and s.strip()][:_SENTENCES]


def _reading(kind: str, text: str, said: str | None) -> dict[str, Any]:
    found = period(text)
    stated = _STATED.search(text)
    day = _date(stated.group(1)) if stated else None
    return {"kind": kind, "said": said[:240] if said else None, "months": found["months"],
            "end": found["end"].isoformat() if found["end"] else None, "named": found["named"],
            "stated": day.isoformat() if day else None}


def _results(text: str, sentences: list[str] | None = None) -> dict[str, Any] | None:
    """``results`` or ``preliminary`` with the sentence that says so; None when no sentence does."""
    for sentence in _sentences(text) if sentences is None else sentences:
        if any(p.search(sentence) for p in _RESULTS) and not any(p.search(sentence) for p in _NOT):
            return _reading("preliminary" if _PRELIMINARY.search(sentence) else "results", text, sentence)
    return None


def _headed(text: str) -> tuple[dict[str, Any] | None, bool]:
    """What a document's title area says: a results sentence in it, else whether it says something else
    (a date to come, deliveries, a profit alert). An exhibit's file header pushes its title past the first
    split, so the area is its opening ``_HEAD_SENTENCES`` sentences."""
    head = _sentences(text)[:_HEAD_SENTENCES]
    found = _results(text, head)
    return found, found is None and any(p.search(s) for s in head for p in _NOT)


def read_6k(document: bytes | str) -> dict[str, Any] | None:
    """A 6-K's cover: ``results`` / ``preliminary``, ``unknown`` when it only says a press release is attached
    (its exhibit decides), or None for any other 6-K."""
    text = cover_body(text_of(document))
    found, other = _headed(text)
    if found is not None:
        return found
    if other:
        return None
    found = _results(text)
    if found is not None:
        return found
    return _reading("unknown", text, None) if _ATTACHED.search(text) else None


def read_8k(document: bytes | str, items: str = "") -> dict[str, Any]:
    """An Item 2.02 8-K: ``results`` / ``preliminary``, ``other`` (deliveries, a restatement, an offering), or
    ``unknown`` when its section only says a press release is attached (its exhibit decides)."""
    text = item_202_body(text_of(document))
    if "4.02" in {s.strip() for s in items.split(",")}:
        return _reading("other", text, None)
    found = _results(text)
    if found is not None:
        return found
    first = next(iter(_sentences(text)), "")
    if _OTHER_202.search(first) or _PRELIMINARY.search(first):
        return _reading("other", text, None)
    return _reading("unknown", text, None)


def read_exhibit(document: bytes | str) -> dict[str, Any]:
    """An Exhibit 99.1's title and opening: ``results`` / ``preliminary``, ``other`` when its title is about
    deliveries or a date to come, else ``unknown``."""
    text = text_of(document)[:_BODY_CHARS]
    found, other = _headed(text)
    if found is not None:
        return found
    if other or any(_OTHER_202.search(s) for s in _sentences(text)[:_HEAD_SENTENCES]):
        return _reading("other", text, None)
    found = _results(text)
    return found if found is not None else _reading("unknown", text, None)


def merge(cover: dict[str, Any] | None, exhibit: dict[str, Any]) -> dict[str, Any]:
    """The exhibit's verdict with the cover's stated day when the exhibit states none."""
    return {**exhibit, "stated": exhibit.get("stated") or (cover or {}).get("stated")}
