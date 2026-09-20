"""Source allowlist, trade-press set, and blocked press-release hosts.

Used by `ai_news_rank.py`. An unlisted domain never reaches the homepage
when `REQUIRE_KNOWN_SOURCE` is on. Weighting alone was tried and failed --
a keyword-stuffed PRLog release outscored every newsroom.
"""
from __future__ import annotations

UNKNOWN_SOURCE_WEIGHT = 0.45
REQUIRE_KNOWN_SOURCE = True
MEGA_WIRE_CAP = 2

# Title pairing uses this set -- not invest / Wall Street / stock market.
# Those three turned "ChatGPT + Wall Street bankers" and "UAE to invest in AI"
# into fake AI-trading hits. Agents that actually invest still pass via
# HIGH_SIGNAL or the agent/bot exception in is_on_topic.
STRICT_MARKET_TERMS = (
    "trading", "trader", "trades", "trade desk", "trading desk",
    "hedge fund", "quant", "quantitative", "asset manager",
    "asset management", "portfolio", "market maker", "market making",
    "broker", "brokerage", "order flow", "order execution",
    "trade execution", "backtest", "buy-side", "sell-side", "buy side",
    "proprietary trading", "wealth management", "stock picking",
    "securities trading", "high-frequency", "market microstructure",
    "capital markets", "equities", "fund manager", "money manager",
    "institutional investing", "investment process",
)

# Hard out, even when a high-signal phrase also matches. These are the
# stories that padded /news after PR #108.
THEME_REJECT_PHRASES = (
    "ai stock", "ai stocks", "ai stock market", "stock market boom",
    "the ai trade", "beyond the ai", "ai boom", "ai wealth",
    "junior banker", "junior bankers", "financial services",
    "regular plan returns", "plan returns",
    "spruiking ai", "full time parenting",
    ".png", "my real test",
    "trading card", "trading cards",
    "trading under symbol",
    "best crypto ai", "best ai trading platform", "best ai trading platforms",
    "best ai trading bots", "which bots actually",
    "i built a",
    "direct plan", "plan portfolio",
    "stock surges", "stock pops", "stock rises",
    "youtube channel",
    "ai bets", "ai-fuelled", "ai-fueled", "crowded ai",
    "ai trade unwind", "trade insults",
    "best ai forex", "certificate in",
    "used ai to write",
    "ai-led selloff", "ai positions",
    "ai-speed coding", "best ai & auto",
)

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
    "tradersmagazine.com": 0.88,
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

MEGA_WIRE_DOMAINS = frozenset({
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com",
    "cnbc.com", "marketwatch.com", "nytimes.com", "theguardian.com",
    "bbc.co.uk", "economist.com", "fortune.com", "cnn.com",
    "forbes.com", "businessinsider.com", "economictimes.com",
    "benzinga.com",
})

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
    "accessnewswire.com",
    "prlog.org",
    "openpr.com",
    "einnews.com",
    "einpresswire.com",
    "newsfilecorp.com",
    "issuewire.com",
})

# Exchange blogs, content mills, and affiliate desks. Not the AI-trading beat.
FEED_SPAM_DOMAINS = frozenset({
    "mexc.com", "mexc.co", "kucoin.com", "weex.com", "moomoo.com",
    "coinedition.com", "crypto.news", "blockchain.news",
    "en.cryptonomist.ch", "fool.com", "stocktitan.net",
    "financialcontent.com", "techbullion.com", "citybuzz.co",
    "timestabloid.com", "the420.in", "analyticsinsight.net",
    "finance.biggo.com", "univest.in", "tradersunion.com",
    "coinspot.io", "cryptotimes.io", "coinbureau.com",
    "gurufocus.com", "www1.ru", "tipranks.com",
    "ccn.com", "ventureburn.com", "t.co", "binance.com",
    "bitcoin.org", "techstock2.com",
    "youtube.com", "youtu.be", "britannica.com", "tradingview.com",
    "bignewsnetwork.com", "arabtribune.com", "mshale.com",
    "coingape.com", "coinmarketcap.com", "yellow.com",
    "nubiapage.com", "indiagazette.com", "americanbazaaronline.com",
    "ebc.com", "macaubusiness.com", "techflowpost.com",
    "pulse2.com", "efinancialcareers.com", "seekingalpha.com",
    "stockstotrade.com", "digitaljournal.com", "kalkinemedia.com",
    "issuewire.com",
})

# Unknown outlets mentioning these are almost always coin-bot filler.
UNKNOWN_CRYPTO_TERMS = (
    "bitcoin", "btc", "ethereum", "xrp", "bnb", "defi", "binance",
    "memecoin", "solana", "nft", "crypto bot", "pepe",
)
