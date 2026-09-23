"""Parse the primary catalyst sources into items (ADR 024). Pure: no I/O, no clock.

  EDGAR    the "latest filings" Atom feed per form: accession, CIK, form, Item codes, accepted time
  wires    GlobeNewswire / PR Newswire / Newsfile / FDA RSS: title, link, publish time and the US
           tickers the release names -- GlobeNewswire tags them (``Nasdaq:ANGI``), the others say
           them in the text ("(NASDAQ: ABCD)")

An item has the research store's shape (``research/catalysts/store.py``) so the recorded feed can
be read by the classifier and later folded into the history unchanged.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree

from constants_catalysts import CATALYST_TICKER_RE

_TICKER = re.compile(CATALYST_TICKER_RE)
_TAGS = re.compile(r"<[^>]+>")
_EDGAR_TITLE = re.compile(r"^(?P<form>\S+(?:\s\S+)?) - (?P<company>.+?) \((?P<cik>\d{10})\) \((?P<role>[^)]+)\)$")
_EDGAR_ITEM = re.compile(r"Item\s+(\d\.\d\d)")
_ATOM = "{http://www.w3.org/2005/Atom}"
_GNW_STOCK = "rss/stock"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub(" ", text or ""))).strip()


def tickers_in(text: str) -> list[str]:
    """US tickers a release names ("(NASDAQ: ABCD)", "(NYSE American: XYZ, XYZ.WS)"), in order, once each."""
    out: list[str] = []
    for group in _TICKER.findall(text or ""):
        for sym in group.split(","):
            sym = sym.strip().upper()
            if sym and sym not in out:
                out.append(sym)
    return out


def _ts(text: str | None) -> float | None:
    if not text:
        return None
    raw = text.strip()
    try:
        return parsedate_to_datetime(raw).timestamp()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def parse_edgar_atom(xml_text: str | bytes) -> list[dict[str, Any]]:
    """Filings from EDGAR's getcurrent Atom: ``{acc, cik, form, company, items, accepted_ts, url}``."""
    root = ElementTree.fromstring(xml_text)
    out = []
    for entry in root.iter(f"{_ATOM}entry"):
        title = _clean(getattr(entry.find(f"{_ATOM}title"), "text", ""))
        m = _EDGAR_TITLE.match(title)
        if not m:
            continue
        summary = html.unescape(getattr(entry.find(f"{_ATOM}summary"), "text", "") or "")
        acc = re.search(r"AccNo:\s*</b>\s*([\d-]+)|AccNo:\s*([\d-]+)", summary)
        ident = getattr(entry.find(f"{_ATOM}id"), "text", "") or ""
        accession = (acc.group(1) or acc.group(2)) if acc else ident.rsplit("=", 1)[-1]
        link = entry.find(f"{_ATOM}link")
        out.append({
            "acc": accession.strip(),
            "cik": str(int(m.group("cik"))),
            "form": m.group("form").strip(),
            "company": m.group("company").strip(),
            "role": m.group("role"),
            "items": ",".join(dict.fromkeys(_EDGAR_ITEM.findall(summary))),
            "accepted_ts": _ts(getattr(entry.find(f"{_ATOM}updated"), "text", None)),
            "url": link.get("href") if link is not None else None,
        })
    return [f for f in out if f["acc"] and f["accepted_ts"] is not None]


def parse_rss(xml_text: str | bytes, source: str) -> list[dict[str, Any]]:
    """Items of a wire's RSS feed: ``{item_id, source, published_ts, title, summary, url, publisher, company, tickers}``."""
    if isinstance(xml_text, (bytes, bytearray)):
        xml_text = bytes(xml_text).decode("utf-8-sig", "replace")
    root = ElementTree.fromstring(xml_text.lstrip())
    out = []
    for item in root.iter("item"):
        fields: dict[str, str] = {}
        tagged: list[str] = []
        for child in item:
            name = _local(child.tag)
            if name == "category" and _GNW_STOCK in (child.get("domain") or ""):
                tagged += tickers_in((child.text or "").replace(":", ": "))
            elif name not in fields:
                fields[name] = child.text or ""
        title = _clean(fields.get("title"))
        summary = _clean(fields.get("description"))[:2000]
        url = (fields.get("link") or fields.get("guid") or "").strip()
        published = _ts(fields.get("pubDate") or fields.get("date"))
        if not title or not url or published is None:
            continue
        tickers = list(dict.fromkeys(tagged + tickers_in(f"{title} {summary}")))
        out.append({
            "item_id": f"{source}:{url}",
            "source": source,
            "published_ts": published,
            "title": title,
            "summary": summary,
            "url": url,
            "publisher": fields.get("creator") or fields.get("publisher") or source,
            "company": _clean(fields.get("contributor")) or None,   # the issuer, when the wire names it
            "tickers": tickers,
        })
    return out


def company_key(name: str | None) -> str:
    """A company name reduced for matching: lower case, no punctuation, no Inc / Corp / Ltd / plc."""
    text = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    text = re.sub(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|sa|nv|ag|holdings?|group|llc|lp)\b",
                  " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tickers_named(text: str, names: dict[str, list[str]], min_len: int = 8) -> list[str]:
    """Tickers of listed companies whose full reduced name appears in ``text`` (FDA releases name companies,
    not tickers). Short names are skipped: a false match is worse than no match."""
    hay = f" {company_key(text)} "
    out: list[str] = []
    for key, syms in names.items():
        if len(key) >= min_len and f" {key} " in hay:
            out += [s for s in syms if s not in out]
    return out
