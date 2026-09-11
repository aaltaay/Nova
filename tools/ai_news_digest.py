"""Build the "AI x the tape" news block on nova.altaystudio.com.

The marketing site is static: no build step, no API, no secrets. So the digest
is generated ahead of time and committed as plain HTML between sentinel
comments in `site/index.html`. A scheduled GitHub Action re-runs this and
commits the diff; Vercel redeploys from git. Readers get server-rendered
markup -- no client fetch, no loading flash, no empty state if JS is off.

Sources are public RSS/Atom only, so this needs no API key and stdlib only.

    py -3 tools/ai_news_digest.py --dry-run --json    # inspect the picks
    py -3 tools/ai_news_digest.py                     # rewrite site/index.html

Ranking lives in `tools/ai_news_rank.py`.
"""
from __future__ import annotations

import argparse
import html
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

from ai_news_rank import Article, rank_articles

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "site" / "index.html"

START_MARKER = "<!-- AI_NEWS:START -->"
END_MARKER = "<!-- AI_NEWS:END -->"

DEFAULT_LIMIT = 6
# Refuse to publish a thin page. Nova's own feed rule applies here too: an
# empty result is a failure, not a fresh answer. Better to keep yesterday's
# good block than overwrite it with one survivor of a bad fetch.
DEFAULT_MIN_ITEMS = 4
FETCH_TIMEOUT_SEC = 20
MAX_SUMMARY_CHARS = 190
USER_AGENT = "NovaNewsDigest/1.0 (+https://nova.altaystudio.com)"

# Google News search feeds aggregate paywalled wires (Reuters, Bloomberg, FT)
# that publish no usable RSS of their own; the publisher is recovered from each
# item's <source url="..."> element. Publisher feeds cover the AI trade press.
_GNEWS = "https://news.google.com/rss/search?q={}&hl=en-US&gl=US&ceid=US:en"

# The searches aim straight at "AI is doing the trading". Broad queries such as
# `"artificial intelligence" trading` were tried and mostly returned AI-as-a-
# hot-stock coverage, so the phrases themselves are the query.
FEEDS: tuple[tuple[str, str], ...] = (
    ("Google News", _GNEWS.format(
        "%22algorithmic+trading%22+OR+%22AI+trading%22+OR+%22trading+algorithm%22+when:14d")),
    ("Google News", _GNEWS.format(
        "%22quant+fund%22+OR+%22quantitative+trading%22+OR+%22AI+hedge+fund%22+"
        "OR+%22systematic+trading%22+when:14d")),
    ("Google News", _GNEWS.format("%22artificial+intelligence%22+%22hedge+fund%22+when:14d")),
    ("Google News", _GNEWS.format(
        "%22machine+learning%22+%22market+making%22+OR+%22trade+execution%22+"
        "OR+%22order+flow%22+when:14d")),
    ("Google News", _GNEWS.format(
        "%22AI+agents%22+trading+OR+%22autonomous+trading%22+OR+%22trading+bots%22+when:14d")),
    # Site-scoped searches reach outlets whose own feeds are paywalled or
    # Cloudflare-blocked. thetradenews.com and waterstechnology.com are the
    # sharpest sources on this beat and are only reachable this way.
    ("Google News", _GNEWS.format(
        "%28AI+OR+%22artificial+intelligence%22%29+trading+site:thetradenews.com+OR+"
        "site:waterstechnology.com+OR+site:risk.net+OR+site:institutionalinvestor.com+"
        "OR+site:pionline.com+when:30d")),
    ("Google News", _GNEWS.format(
        "%22artificial+intelligence%22+trading+site:reuters.com+OR+site:bloomberg.com+"
        "OR+site:wsj.com+OR+site:ft.com+when:30d")),
    # Direct publisher feeds, all verified reachable.
    ("Financial Times", "https://www.ft.com/markets?format=rss"),
    ("Financial Times", "https://www.ft.com/technology?format=rss"),
    ("CNBC Investing", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"),
    ("CNBC Technology", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910"),
    ("CNBC Finance", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("The Guardian", "https://www.theguardian.com/uk/business/rss"),
    ("WIRED", "https://www.wired.com/feed/category/business/latest/rss"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    # Market-structure trade press: low volume, but this is their actual beat.
    ("Traders Magazine", "https://www.tradersmagazine.com/feed/"),
    ("Finextra", "https://www.finextra.com/rss/headlines.aspx"),
    ("Markets Media", "https://www.marketsmedia.com/feed/"),
    ("Hedgeweek", "https://www.hedgeweek.com/feed/"),
    ("arXiv q-fin.TR", "http://export.arxiv.org/rss/q-fin.TR"),
)

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
            payload = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  warn: {label} unreachable ({exc})", file=sys.stderr)
        return []
    articles = parse_feed(payload, label)
    print(f"  {label}: {len(articles)} items", file=sys.stderr)
    return articles


def collect(feeds: tuple[tuple[str, str], ...] = FEEDS) -> list[Article]:
    print(f"Fetching {len(feeds)} feeds...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        batches = pool.map(lambda feed: fetch_feed(*feed), feeds)
    return [article for batch in batches for article in batch]


def _relative_day(published: datetime | None, now: datetime) -> str:
    if published is None:
        return "Recent"
    days = (now.date() - published.date()).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    return f"{days} days ago"


def render_block(articles: list[Article], now: datetime) -> str:
    """Render the shortlist as the static HTML that lives inside the markers."""
    rows: list[str] = ['      <ol class="news-list">']
    for index, article in enumerate(articles, start=1):
        stamp = article.published.isoformat() if article.published else now.isoformat()
        summary = (
            f'\n            <p class="news-sum">{html.escape(article.summary)}</p>'
            if article.summary else ""
        )
        rows.append(f"""        <li class="news-item">
          <a class="news-link" href="{html.escape(article.url, quote=True)}" rel="noopener noreferrer" target="_blank">
            <p class="news-meta">
              <span class="news-rank">{index:02d}</span>
              <span class="news-src">{html.escape(article.source)}</span>
              <time datetime="{html.escape(stamp, quote=True)}">{_relative_day(article.published, now)}</time>
            </p>
            <h3>{html.escape(article.title)}</h3>{summary}
          </a>
        </li>""")
    rows.append("      </ol>")
    rows.append(
        f'      <p class="news-foot">Ranked by source credibility, topical depth, and '
        f'recency. Headlines link to the publisher. Updated '
        f'<time datetime="{now.isoformat()}">{now.strftime("%b %d, %Y %H:%M UTC")}</time>.</p>'
    )
    return "\n".join(rows)


def inject(page_html: str, block: str) -> str:
    """Replace whatever sits between the sentinels. Raises if they are missing."""
    start = page_html.find(START_MARKER)
    end = page_html.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"{START_MARKER} / {END_MARKER} not found in the page")
    head = page_html[: start + len(START_MARKER)]
    tail = page_html[end:]
    return f"{head}\n{block}\n      {tail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="stories to publish")
    parser.add_argument("--min-items", type=int, default=DEFAULT_MIN_ITEMS,
                        help="refuse to write below this many stories")
    parser.add_argument("--index", type=Path, default=INDEX_HTML, help="page to rewrite")
    parser.add_argument("--dry-run", action="store_true", help="rank but do not write")
    parser.add_argument("--json", action="store_true", help="print the ranked picks as JSON")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    candidates = collect()
    print(f"{len(candidates)} candidates fetched", file=sys.stderr)

    picks = rank_articles(candidates, now, args.limit)
    print(f"{len(picks)} stories survived ranking", file=sys.stderr)

    if args.json:
        print(json.dumps([
            {
                "rank": i,
                "score": round(a.score, 2),
                "source": a.source,
                "domain": a.domain,
                "title": a.title,
                "url": a.url,
                "published": a.published.isoformat() if a.published else None,
                "why": a.reasons,
            }
            for i, a in enumerate(picks, start=1)
        ], indent=2))

    if len(picks) < args.min_items:
        print(
            f"REFUSING to write: {len(picks)} stories < --min-items {args.min_items}. "
            "Keeping the previously published block.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print("Dry run -- page not modified.", file=sys.stderr)
        return 0

    page = args.index.read_text(encoding="utf-8")
    updated = inject(page, render_block(picks, now))
    if updated == page:
        print("No change.", file=sys.stderr)
        return 0
    args.index.write_text(updated, encoding="utf-8")
    print(f"Wrote {len(picks)} stories to {args.index}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
