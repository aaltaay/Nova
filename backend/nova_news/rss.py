"""Public RSS/Atom fetch + parse for the Nova News desk.

Stdlib only. Never scrapes HTML. A failed feed is a loud ProviderResult,
not an empty success.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

from constants import NOVA_NEWS_DESK_HTTP_TIMEOUT_SEC, NOVA_NEWS_HTTP_USER_AGENT
from nova_news.models import ProviderResult

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NS_RE = re.compile(r"^\{[^}]*\}")


def _localname(tag: str) -> str:
    return _NS_RE.sub("", tag)


def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", raw))).strip()


def parse_date(raw: str | None) -> datetime | None:
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    for parser in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            parsed = parser(
                raw.replace("Z", "+00:00") if parser is datetime.fromisoformat else raw
            )
        except (TypeError, ValueError, OverflowError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _entry_link(entry: ElementTree.Element) -> str:
    for child in entry:
        if _localname(child.tag) != "link":
            continue
        if child.text and child.text.strip():
            return child.text.strip()
        href = child.attrib.get("href", "").strip()
        if href and child.attrib.get("rel", "alternate") == "alternate":
            return href
    return ""


def parse_feed(xml_text: str, fallback_source: str) -> list[dict]:
    """Parse RSS 2.0 / Atom into raw article dicts. Never raises."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    articles: list[dict] = []
    for entry in root.iter():
        if _localname(entry.tag) not in ("item", "entry"):
            continue
        fields: dict[str, ElementTree.Element] = {}
        for child in entry:
            fields.setdefault(_localname(child.tag), child)

        title = clean_text(fields["title"].text if "title" in fields else "")
        url = _entry_link(entry)
        if not title or not url:
            continue

        body = ""
        for key in ("description", "summary", "content"):
            if key in fields:
                body = clean_text(fields[key].text)
                if body:
                    break

        published = None
        for key in ("pubDate", "published", "updated", "date"):
            if key in fields:
                published = parse_date(fields[key].text)
                if published:
                    break

        source_label = fallback_source
        if "source" in fields:
            named = clean_text(fields["source"].text)
            if named:
                source_label = named

        suffix = f" - {source_label}"
        if source_label and title.endswith(suffix):
            title = title[: -len(suffix)].strip()

        articles.append({
            "headline": title,
            "summary": body,
            "url": url,
            "source": source_label,
            "created_at": published.isoformat() if published else None,
        })
    return articles


def fetch_rss(provider_id: str, label: str, url: str) -> ProviderResult:
    try:
        resp = requests.get(
            url,
            timeout=NOVA_NEWS_DESK_HTTP_TIMEOUT_SEC,
            headers={"User-Agent": NOVA_NEWS_HTTP_USER_AGENT},
        )
    except Exception:
        logger.warning("nova_news: RSS fetch failed for %s", provider_id, exc_info=True)
        return ProviderResult(
            id=provider_id,
            label=label,
            ok=False,
            count=0,
            error=f"{label} request failed.",
        )
    if resp.status_code != 200:
        return ProviderResult(
            id=provider_id,
            label=label,
            ok=False,
            count=0,
            error=f"{label} returned HTTP {resp.status_code}.",
        )
    articles = parse_feed(resp.text, label)
    return ProviderResult(
        id=provider_id,
        label=label,
        ok=True,
        count=len(articles),
        articles=articles,
    )
