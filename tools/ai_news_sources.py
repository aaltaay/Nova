"""Source allowlist, trade-press set, and blocked press-release hosts.

Used by `ai_news_rank.py`. An unlisted domain never reaches the homepage
when `REQUIRE_KNOWN_SOURCE` is on. Weighting alone was tried and failed --
a keyword-stuffed PRLog release outscored every newsroom.
"""
from __future__ import annotations

UNKNOWN_SOURCE_WEIGHT = 0.45
REQUIRE_KNOWN_SOURCE = True

SOURCE_WEIGHTS = {
    "reuters.com": 1.0, "bloomberg.com": 1.0, "ft.com": 1.0, "wsj.com": 1.0,
    "economist.com": 0.95, "nytimes.com": 0.9, "theinformation.com": 0.9,
    "cnbc.com": 0.85, "marketwatch.com": 0.85, "barrons.com": 0.85,
    "axios.com": 0.8, "semafor.com": 0.78, "fortune.com": 0.72,
    "businessinsider.com": 0.7, "cnn.com": 0.68, "bbc.co.uk": 0.75,
    "theguardian.com": 0.72, "washingtonpost.com": 0.82, "forbes.com": 0.6,
    "thetradenews.com": 0.98, "risk.net": 0.98, "waterstechnology.com": 0.95,
    "institutionalinvestor.com": 0.90, "pionline.com": 0.88,
    "marketsmedia.com": 0.92, "hedgeweek.com": 0.90, "finextra.com": 0.88,
    "tradersmagazine.com": 0.88, "efinancialcareers.com": 0.6,
    "globaltrading.net": 0.74, "financialit.net": 0.70,
    "automatedtrader.com": 0.70, "efinancialnews.com": 0.75,
    "ai-cio.com": 0.72, "tabbforum.com": 0.70,
    "financemagnates.com": 0.74, "ffnews.com": 0.70,
    "mondovisione.com": 0.68, "investmentexecutive.com": 0.68,
    "economictimes.com": 0.70, "afr.com": 0.72,
    "technologyreview.com": 0.75, "wired.com": 0.72, "arstechnica.com": 0.72,
    "techcrunch.com": 0.7, "theverge.com": 0.68, "venturebeat.com": 0.66,
    "arxiv.org": 0.62,
}

TRADE_PRESS_DOMAINS = frozenset({
    "thetradenews.com", "risk.net", "waterstechnology.com",
    "institutionalinvestor.com", "pionline.com", "marketsmedia.com",
    "hedgeweek.com", "finextra.com", "tradersmagazine.com",
    "globaltrading.net", "financialit.net", "automatedtrader.com",
    "efinancialnews.com", "ai-cio.com", "tabbforum.com",
    "financemagnates.com", "ffnews.com", "mondovisione.com",
    "investmentexecutive.com",
})

BLOCKED_DOMAINS = frozenset({
    "markets.businessinsider.com",
    "finance.yahoo.com",
    "yahoo.com",
    "prnewswire.com",
    "globenewswire.com",
    "businesswire.com",
    "accesswire.com",
    "prlog.org",
    "openpr.com",
})

# Exchange blogs, content mills, and affiliate desks. Not the AI-trading beat.
FEED_SPAM_DOMAINS = frozenset({
    "mexc.com", "kucoin.com", "weex.com", "moomoo.com",
    "coinedition.com", "crypto.news", "blockchain.news",
    "en.cryptonomist.ch", "fool.com", "stocktitan.net",
    "financialcontent.com", "techbullion.com", "citybuzz.co",
    "timestabloid.com", "the420.in", "analyticsinsight.net",
    "finance.biggo.com", "univest.in", "tradersunion.com",
    "coinspot.io", "cryptotimes.io", "coinbureau.com",
    "gurufocus.com", "www1.ru", "tipranks.com",
    "ccn.com", "ventureburn.com", "t.co", "binance.com",
    "bitcoin.org", "techstock2.com",
})

# Unknown outlets mentioning these are almost always coin-bot filler.
UNKNOWN_CRYPTO_TERMS = (
    "bitcoin", "btc", "ethereum", "xrp", "bnb", "defi", "binance",
    "memecoin", "solana", "nft", "crypto bot", "pepe",
)
