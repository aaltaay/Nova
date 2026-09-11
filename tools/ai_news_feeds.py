"""Public RSS/Atom sources for the marketing-site AI-in-trading digest.

No secrets. Trade-press and targeted Google News searches first; mega wires
are present so a real story is not missed, but ranking down-weights them
on the /news feed.
"""
from __future__ import annotations

_GNEWS = "https://news.google.com/rss/search?q={}&hl=en-US&gl=US&ceid=US:en"

FEEDS: tuple[tuple[str, str], ...] = (
    ("Google News", _GNEWS.format(
        "%22algorithmic+trading%22+OR+%22AI+trading%22+OR+%22trading+algorithm%22+when:14d")),
    ("Google News", _GNEWS.format(
        "%22quant+fund%22+OR+%22quantitative+trading%22+OR+%22AI+hedge+fund%22+"
        "OR+%22systematic+trading%22+when:14d")),
    ("Google News", _GNEWS.format(
        "%22artificial+intelligence%22+%22hedge+fund%22+when:14d")),
    ("Google News", _GNEWS.format(
        "%22machine+learning%22+%22market+making%22+OR+%22trade+execution%22+"
        "OR+%22order+flow%22+when:14d")),
    ("Google News", _GNEWS.format(
        "%22AI+agents%22+trading+OR+%22autonomous+trading%22+OR+%22trading+bots%22+when:14d")),
    ("Google News", _GNEWS.format(
        "%28AI+OR+%22artificial+intelligence%22%29+trading+site:thetradenews.com+OR+"
        "site:waterstechnology.com+OR+site:risk.net+OR+site:institutionalinvestor.com+"
        "OR+site:pionline.com+when:30d")),
    ("Google News", _GNEWS.format(
        "%22artificial+intelligence%22+trading+site:reuters.com+OR+site:bloomberg.com+"
        "OR+site:wsj.com+OR+site:ft.com+when:30d")),
    ("Google News", _GNEWS.format(
        "%28AI+OR+%22artificial+intelligence%22%29+trading+site:tradersmagazine.com+OR+"
        "site:finextra.com+OR+site:marketsmedia.com+OR+site:hedgeweek.com+"
        "OR+site:globaltrading.net+OR+site:financialit.net+when:30d")),
    ("Google News", _GNEWS.format(
        "%22execution+algorithm%22+OR+%22smart+order+routing%22+OR+"
        "%22transaction+cost+analysis%22+%28AI+OR+%22machine+learning%22%29+when:14d")),
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
    ("Traders Magazine", "https://www.tradersmagazine.com/feed/"),
    ("Finextra", "https://www.finextra.com/rss/headlines.aspx"),
    ("Markets Media", "https://www.marketsmedia.com/feed/"),
    ("Hedgeweek", "https://www.hedgeweek.com/feed/"),
    ("arXiv q-fin.TR", "http://export.arxiv.org/rss/q-fin.TR"),
)
