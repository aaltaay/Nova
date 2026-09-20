"""Public RSS/Atom sources for the marketing-site AI-in-trading digest.

No secrets. Native trade-press RSS first so headlines link to the publisher,
not a Google News wrapper. Mega-wire dumps stay out of the candidate pool;
ranking still accepts a Reuters/FT hit that arrives through a targeted search.
"""
from __future__ import annotations

_GNEWS = "https://news.google.com/rss/search?q={}&hl=en-US&gl=US&ceid=US:en"

# One Google News query per outlet. A single OR-of-sites query returns 100
# mixed hits and starves the smaller desks.
_SITE_SEARCHES = (
    "thetradenews.com",
    "waterstechnology.com",
    "risk.net",
    "tradersmagazine.com",
    "finextra.com",
    "marketsmedia.com",
    "hedgeweek.com",
    "globaltrading.net",
    "financialit.net",
    "institutionalinvestor.com",
    "pionline.com",
    "tabbforum.com",
    "ai-cio.com",
    "mondovisione.com",
    "investmentexecutive.com",
    "financemagnates.com",
    "automatedtrader.com",
)


def _gnews(query: str) -> str:
    return _GNEWS.format(query)


def _site_feed(host: str) -> tuple[str, str]:
    return (
        "Google News",
        _gnews(
            "%28AI+OR+%22artificial+intelligence%22+OR+algorithmic+OR+quant%29+"
            f"trading+site:{host}+when:90d"
        ),
    )


FEEDS: tuple[tuple[str, str], ...] = (
    ("The TRADE", "https://www.thetradenews.com/feed/"),
    ("WatersTechnology", "https://www.waterstechnology.com/feeds/rss"),
    ("Risk.net", "https://www.risk.net/feeds/rss/latest"),
    ("Traders Magazine", "https://www.tradersmagazine.com/feed/"),
    ("Finextra", "https://www.finextra.com/rss/headlines.aspx"),
    ("Markets Media", "https://www.marketsmedia.com/feed/"),
    ("Hedgeweek", "https://www.hedgeweek.com/feed/"),
    ("Global Trading", "https://www.globaltrading.net/feed/"),
    ("Financial IT", "https://financialit.net/rss.xml"),
    ("Institutional Investor", "https://www.institutionalinvestor.com/rss.xml"),
    ("arXiv q-fin.TR", "http://export.arxiv.org/rss/q-fin.TR"),
    ("Google News", _gnews(
        "%22algorithmic+trading%22+OR+%22AI+trading%22+OR+%22trading+algorithm%22+when:30d")),
    ("Google News", _gnews(
        "%22quant+fund%22+OR+%22quantitative+trading%22+OR+%22AI+hedge+fund%22+"
        "OR+%22systematic+trading%22+when:30d")),
    ("Google News", _gnews(
        "%22artificial+intelligence%22+%22hedge+fund%22+when:30d")),
    ("Google News", _gnews(
        "%22machine+learning%22+%22market+making%22+OR+%22trade+execution%22+"
        "OR+%22order+flow%22+when:30d")),
    ("Google News", _gnews(
        "%22AI+agents%22+trading+OR+%22autonomous+trading%22+OR+%22trading+bots%22+when:30d")),
    ("Google News", _gnews(
        "%22execution+algorithm%22+OR+%22smart+order+routing%22+OR+"
        "%22transaction+cost+analysis%22+%28AI+OR+%22machine+learning%22%29+when:30d")),
    ("Google News", _gnews(
        "%22execution+algorithm%22+OR+%22execution+algo%22+OR+%22smart+order+routing%22+"
        "when:90d")),
    ("Google News", _gnews(
        "%22buy-side%22+%28AI+OR+%22artificial+intelligence%22+OR+algorithmic%29+when:60d")),
    ("Google News", _gnews(
        "%22claude%22+%28%22investment+process%22+OR+%22hedge+fund%22+OR+trading%29+when:60d")),
    ("Google News", _gnews(
        "%22reinforcement+learning%22+%28trading+OR+execution+OR+%22market+making%22%29+"
        "when:90d")),
    *tuple(_site_feed(host) for host in _SITE_SEARCHES),
    ("Financial Times", "https://www.ft.com/markets?format=rss"),
    ("Financial Times", "https://www.ft.com/technology?format=rss"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
    ("WIRED", "https://www.wired.com/feed/category/business/latest/rss"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
)
