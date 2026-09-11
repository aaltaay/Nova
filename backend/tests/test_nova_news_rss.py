"""RSS parser for Nova News -- no HTML scrape, Google News source tags."""
from __future__ import annotations

from nova_news.rss import parse_feed

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Yahoo Finance</title>
    <item>
      <title>Acme jumps on contract award - Reuters</title>
      <link>https://finance.yahoo.com/news/acme</link>
      <pubDate>Thu, 11 Sep 2026 12:00:00 GMT</pubDate>
      <description>Shares rose after a new deal.</description>
      <source url="https://www.reuters.com">Reuters</source>
    </item>
    <item>
      <title></title>
      <link>https://finance.yahoo.com/empty</link>
    </item>
  </channel>
</rss>
"""


def test_parse_feed_reads_yahoo_item_and_publisher():
    articles = parse_feed(RSS, "Yahoo Finance")
    assert len(articles) == 1
    art = articles[0]
    assert art["headline"] == "Acme jumps on contract award"
    assert art["url"] == "https://finance.yahoo.com/news/acme"
    assert art["source"] == "Reuters"
    assert art["created_at"]
    assert "Shares rose" in art["summary"]


def test_parse_feed_bad_xml_is_empty_not_raise():
    assert parse_feed("<not-xml", "Yahoo") == []
