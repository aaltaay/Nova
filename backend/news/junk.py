"""Low-signal movers / listicle classifier for the News column and flame.

Hard listicles (N-stocks-moving, movers recaps, Benzinga movers URLs) are
always junk. Sector roundups are junk unless the headline also names a
company-specific catalyst. News never places orders.
"""
from __future__ import annotations

import re

from constants import (
    NEWS_JUNK_HEADLINE_PHRASES,
    NEWS_JUNK_HEADLINE_RES,
    NEWS_JUNK_SECTOR_ROUNDUP_RE,
    NEWS_JUNK_URL_FRAGMENTS,
    NEWS_SIGNAL_HEADLINE_KEYWORDS,
)

_HEADLINE_RES = tuple(re.compile(pat, re.IGNORECASE) for pat in NEWS_JUNK_HEADLINE_RES)
_SECTOR_RE = re.compile(NEWS_JUNK_SECTOR_ROUNDUP_RE, re.IGNORECASE)
_PHRASES = tuple(p.lower() for p in NEWS_JUNK_HEADLINE_PHRASES)
_SIGNALS = tuple(k.lower() for k in NEWS_SIGNAL_HEADLINE_KEYWORDS)
_URL_FRAGMENTS = tuple(f.lower() for f in NEWS_JUNK_URL_FRAGMENTS)


def _has_signal(text: str) -> bool:
    return any(key in text for key in _SIGNALS)


def is_junk_headline(headline: str, url: str = "", source: str = "") -> bool:
    """True for movers listicles / sector recaps that are not a single-name catalyst.

    ``source`` is accepted for call-site symmetry; classification is headline + URL.
    """
    del source
    text = (headline or "").strip().lower()
    url_l = (url or "").strip().lower()
    if any(frag in url_l for frag in _URL_FRAGMENTS):
        return True
    if not text:
        return False
    if any(rx.search(text) for rx in _HEADLINE_RES):
        return True
    if any(phrase in text for phrase in _PHRASES):
        return True
    if _SECTOR_RE.search(text) and not _has_signal(text):
        return True
    return False


def is_junk_article(article: dict) -> bool:
    headline = str(
        article.get("headline") or article.get("catalyst_headline") or ""
    )
    url = str(article.get("url") or article.get("catalyst_url") or "")
    source = str(article.get("source") or article.get("catalyst_source") or "")
    return is_junk_headline(headline, url=url, source=source)


def partition_signal_articles(articles: list[dict]) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    junked: list[dict] = []
    for article in articles:
        if is_junk_article(article):
            junked.append(article)
        else:
            kept.append(article)
    return kept, junked


def filter_signal_articles(articles: list[dict]) -> list[dict]:
    kept, _junked = partition_signal_articles(articles)
    return kept


def newest_signal_by_symbol(articles: list[dict]) -> dict[str, dict]:
    """Map each symbol to the newest non-junk article payload."""
    out: dict[str, dict] = {}
    for article in articles:
        if is_junk_article(article):
            continue
        created_at = str(article.get("created_at") or "")
        payload = {
            "created_at": created_at,
            "headline": article.get("headline") or "",
            "url": article.get("url") or "",
            "source": article.get("source") or "",
        }
        for sym in article.get("symbols") or []:
            if not sym:
                continue
            prev = out.get(sym)
            if prev is None or created_at > prev["created_at"]:
                out[sym] = payload
    return out
