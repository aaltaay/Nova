"""Build the AI-in-trading digest on nova.altaystudio.com.

The marketing site is static: no API, no secrets. A scheduled Action fetches
public RSS, ranks it, and commits HTML. Homepage gets a short teaser;
`/news` gets the full Reddit-style feed (50+ when inventory exists).

    python3 tools/ai_news_digest.py --dry-run --json
    python3 tools/ai_news_digest.py

Ranking: `tools/ai_news_rank.py`. HTML: `tools/ai_news_html.py`.
"""
from __future__ import annotations

import argparse
import gzip
import html
import logging
import zlib
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree

from ai_news_publish import publication_unchanged
from ai_news_feeds import FEEDS
from ai_news_html import (
    END_MARKER,
    FEED_END_MARKER,
    FEED_START_MARKER,
    START_MARKER,
    count_marked_items,
    feed_json_text,
    inject,
    render_block,
    render_feed_block,
)
from ai_news_rank import Article, rank_articles

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "site" / "index.html"
NEWS_HTML = REPO_ROOT / "site" / "news" / "index.html"
FEED_JSON = REPO_ROOT / "site" / "news" / "feed.json"

DEFAULT_LIMIT = 6
DEFAULT_FEED_LIMIT = 60
DEFAULT_MIN_ITEMS = 4
DEFAULT_FEED_MIN_ITEMS = 50
FEED_MAX_PER_DOMAIN = 10
FEED_MIN_SCORE = 0.2
FEED_RECENCY_HALF_LIFE_HOURS = 336.0
FEED_MAX_AGE_DAYS = 90
TRADE_PRESS_BOOST = 1.25
FETCH_TIMEOUT_SEC = 25
MAX_SUMMARY_CHARS = 190
USER_AGENT = "NovaNewsDigest/1.0 (+https://nova.altaystudio.com)"

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# ElementTree keeps namespaces in tag names; Atom and Dublin Core need stripping.
_NS_RE = re.compile(r"^\{[^}]*\}")


def _localname(tag: str) -> str:
    return _NS_RE.sub("", tag)


def clean_text(raw: str | None) -> str:
    """Strip markup and entities out of a feed blurb, collapse whitespace."""
    if not raw:
        return ""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", raw))).strip()


def truncate(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    """Cut at a word boundary and add an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(".,;:-")
    return f"{cut}..."


def _is_echo_summary(title: str, summary: str, source: str) -> bool:
    """True when a blurb just repeats the headline.

    Google News descriptions are the linked headline plus the outlet name, so
    stripping tags yields "Bank of Korea Warns ... WSJ" -- a duplicate line
    under the headline. Matching that exact shape (summary opens with the
    headline) rather than counting shared words, which also discarded short
    but genuine blurbs.
    """
    if not summary:
        return True
    flat_summary = " ".join(re.findall(r"[a-z0-9]+", summary.lower()))
    flat_title = " ".join(re.findall(r"[a-z0-9]+", title.lower()))
    if not flat_title:
        return False
    if not flat_summary.startswith(flat_title):
        return False
    # Anything past the repeated headline is usually just the outlet name.
    remainder = flat_summary[len(flat_title):].strip()
    source_words = set(re.findall(r"[a-z0-9]+", source.lower()))
    return all(word in source_words for word in remainder.split())


def parse_date(raw: str | None) -> datetime | None:
    """Accept RFC 822 (RSS) or ISO 8601 (Atom); always return UTC-aware."""
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    for parser in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            parsed = parser(raw.replace("Z", "+00:00") if parser is datetime.fromisoformat else raw)
        except (TypeError, ValueError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _entry_link(entry: ElementTree.Element) -> str:
    """RSS puts the URL in link text; Atom puts it in a link/@href."""
    for child in entry:
        if _localname(child.tag) != "link":
            continue
        if child.text and child.text.strip():
            return child.text.strip()
        href = child.attrib.get("href", "").strip()
        if href and child.attrib.get("rel", "alternate") == "alternate":
            return href
    return ""


def parse_feed(xml_bytes: bytes, label: str) -> list[Article]:
    """Parse an RSS 2.0, RDF, or Atom document into Articles. Never raises."""
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return []

    articles: list[Article] = []
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

        # Google News: <source url="https://www.reuters.com">Reuters</source>
        publisher_url = ""
        source_label = label
        if "source" in fields:
            publisher_url = fields["source"].attrib.get("url", "").strip()
            named = clean_text(fields["source"].text)
            if named:
                source_label = named

        # Google News appends " - Publisher" to every headline. It reads badly
        # on the page and it let a "Seeking Alpha" byline score as trading jargon.
        suffix = f" - {source_label}"
        if source_label and title.endswith(suffix):
            title = title[: -len(suffix)].strip()

        if _is_echo_summary(title, body, source_label):
            body = ""

        articles.append(Article(
            title=title,
            url=url,
            summary=truncate(body),
            source=source_label,
            published=published,
            publisher_url=publisher_url,
        ))
    return articles


def fetch_feed(label: str, url: str) -> list[Article]:
    """Fetch one feed. A single dead feed degrades the digest, never kills it."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SEC) as response:
            payload = decode_feed_body(response.read())
    except (urllib.error.URLError, TimeoutError, OSError, EOFError, zlib.error) as exc:
        print(f"  warn: {label} unreachable ({exc})", file=sys.stderr)
        return []
    articles = parse_feed(payload, label)
    print(f"  {label}: {len(articles)} items", file=sys.stderr)
    return articles


def decode_feed_body(payload: bytes) -> bytes:
    """Decode gzip magic even when a publisher omits Content-Encoding."""
    return gzip.decompress(payload) if payload.startswith(b"\x1f\x8b") else payload


def collect(feeds: tuple[tuple[str, str], ...] = FEEDS) -> list[Article]:
    print(f"Fetching {len(feeds)} feeds...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        batches = pool.map(lambda feed: fetch_feed(*feed), feeds)
    return [article for batch in batches for article in batch]


def rank_teaser(candidates: list[Article], now: datetime, limit: int) -> list[Article]:
    """Tight homepage shortlist -- known sources, 2 per domain."""
    return rank_articles(candidates, now, limit)


def rank_feed(candidates: list[Article], now: datetime, limit: int) -> list[Article]:
    """Public /news list -- higher volume, trade press preferred."""
    return rank_articles(
        candidates,
        now,
        limit,
        max_per_domain=FEED_MAX_PER_DOMAIN,
        min_score=FEED_MIN_SCORE,
        require_known_source=False,
        trade_press_boost=TRADE_PRESS_BOOST,
        recency_half_life_hours=FEED_RECENCY_HALF_LIFE_HOURS,
        max_age_days=FEED_MAX_AGE_DAYS,
    )


def _write_if_changed(path: Path, text: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def publish(
    candidates: list[Article],
    *,
    now: datetime,
    homepage_limit: int = DEFAULT_LIMIT,
    feed_limit: int = DEFAULT_FEED_LIMIT,
    homepage_min: int = DEFAULT_MIN_ITEMS,
    feed_min: int = DEFAULT_FEED_MIN_ITEMS,
    index_path: Path = INDEX_HTML,
    news_path: Path = NEWS_HTML,
    feed_json_path: Path = FEED_JSON,
    dry_run: bool = False,
) -> int:
    """Write teaser + /news when each list clears its honesty floor.

    A thin feed never overwrites a page that already has `feed_min` rows.
    Homepage still uses today's min-items rule. Exit 1 only if the teaser
    is too thin to publish.
    """
    teaser = rank_teaser(candidates, now, homepage_limit)
    feed = rank_feed(candidates, now, feed_limit)
    print(f"{len(teaser)} teaser / {len(feed)} feed stories survived ranking", file=sys.stderr)

    existing_feed = 0
    if news_path.exists():
        existing_feed = count_marked_items(
            news_path.read_text(encoding="utf-8"), FEED_START_MARKER, FEED_END_MARKER,
        )

    write_home = len(teaser) >= homepage_min
    write_feed = len(feed) >= feed_min
    if not write_feed:
        print(
            f"REFUSING to write /news: {len(feed)} stories < --feed-min-items {feed_min}. "
            f"Keeping the previously published feed ({existing_feed} rows).",
            file=sys.stderr,
        )

    if not write_home:
        print(
            f"REFUSING to write homepage: {len(teaser)} stories < --min-items {homepage_min}. "
            "Keeping the previously published block.",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        print("Dry run -- pages not modified.", file=sys.stderr)
        return 0

    if write_feed and publication_unchanged(
        feed, teaser, index_path=index_path, news_path=news_path, json_path=feed_json_path,
    ):
        logger.info("Published news content unchanged; keeping existing publication time")
        return 0

    home_page = index_path.read_text(encoding="utf-8")
    home_updated = inject(home_page, render_block(teaser, now), START_MARKER, END_MARKER)
    if home_updated != home_page:
        index_path.write_text(home_updated, encoding="utf-8")
        print(f"Wrote {len(teaser)} teaser stories to {index_path}", file=sys.stderr)
    else:
        print("Homepage teaser unchanged.", file=sys.stderr)

    if write_feed:
        news_page = news_path.read_text(encoding="utf-8")
        news_updated = inject(
            news_page, render_feed_block(feed, now), FEED_START_MARKER, FEED_END_MARKER,
        )
        if news_updated != news_page:
            news_path.write_text(news_updated, encoding="utf-8")
            print(f"Wrote {len(feed)} feed stories to {news_path}", file=sys.stderr)
        dumped = feed_json_text(feed, now)
        if _write_if_changed(feed_json_path, dumped):
            print(f"Wrote {len(feed)} stories to {feed_json_path}", file=sys.stderr)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="homepage teaser size")
    parser.add_argument("--feed-limit", type=int, default=DEFAULT_FEED_LIMIT,
                        help="full /news feed size")
    parser.add_argument("--min-items", type=int, default=DEFAULT_MIN_ITEMS,
                        help="refuse homepage write below this many stories")
    parser.add_argument("--feed-min-items", type=int, default=DEFAULT_FEED_MIN_ITEMS,
                        help="refuse /news overwrite below this many stories")
    parser.add_argument("--index", type=Path, default=INDEX_HTML, help="homepage to rewrite")
    parser.add_argument("--news-page", type=Path, default=NEWS_HTML, help="/news page to rewrite")
    parser.add_argument("--feed-json", type=Path, default=FEED_JSON, help="debug JSON dump")
    parser.add_argument("--dry-run", action="store_true", help="rank but do not write")
    parser.add_argument("--json", action="store_true", help="print the ranked feed as JSON")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    candidates = collect()
    print(f"{len(candidates)} candidates fetched", file=sys.stderr)

    if args.json:
        feed = rank_feed(candidates, now, args.feed_limit)
        print(json.dumps(json.loads(feed_json_text(feed, now))["stories"], indent=2))

    return publish(
        candidates,
        now=now,
        homepage_limit=args.limit,
        feed_limit=args.feed_limit,
        homepage_min=args.min_items,
        feed_min=args.feed_min_items,
        index_path=args.index,
        news_path=args.news_page,
        feed_json_path=args.feed_json,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
