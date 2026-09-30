"""The Cryptos page (ADR 040): its sources, cadences, the coin and bridge tables, and the read's thresholds.

Every URL here is a public, keyless endpoint, and the page names each source beside its numbers. Nothing
here is a stock price source or an order path (``single-market-data-feed.mdc`` rule 13).
"""
from __future__ import annotations

CRYPTO_SCHEMA_VERSION = 1
CRYPTO_ENV = "NOVA_CRYPTO"                          # "0" turns the refreshers off
CRYPTO_COINGECKO_KEY_ENV = "COINGECKO_DEMO_API_KEY"  # optional: CoinGecko's free demo key, a higher rate limit
CRYPTO_NEWS_RULES_VERSION = "crypto-news-v1-2026-09-30"

# -- the coins, in the approved mockup's order ---------------------------------------------------------
# coingecko: CoinGecko's coin id; coinbase: Coinbase Exchange's USD product (None: no market there);
# perp: Hyperliquid's perpetual (kPEPE is 1,000 PEPE); news: Alpaca's news symbol; etf: the US spot ETF
# the desk can trade; groups: the table's filter pills.
CRYPTO_COINS: tuple[dict, ...] = (
    {"symbol": "BTC", "name": "Bitcoin", "coingecko": "bitcoin", "coinbase": "BTC-USD", "perp": "BTC",
     "news": "BTCUSD", "etf": "IBIT", "groups": ("major",)},
    {"symbol": "ETH", "name": "Ether", "coingecko": "ethereum", "coinbase": "ETH-USD", "perp": "ETH",
     "news": "ETHUSD", "etf": "ETHA", "groups": ("major", "layer1")},
    {"symbol": "SOL", "name": "Solana", "coingecko": "solana", "coinbase": "SOL-USD", "perp": "SOL",
     "news": "SOLUSD", "etf": None, "groups": ("major", "layer1")},
    {"symbol": "XRP", "name": "XRP", "coingecko": "ripple", "coinbase": "XRP-USD", "perp": "XRP",
     "news": "XRPUSD", "etf": None, "groups": ("major", "payments")},
    {"symbol": "BNB", "name": "BNB", "coingecko": "binancecoin", "coinbase": None, "perp": "BNB",
     "news": "BNBUSD", "etf": None, "groups": ("major", "layer1")},
    {"symbol": "DOGE", "name": "Dogecoin", "coingecko": "dogecoin", "coinbase": "DOGE-USD", "perp": "DOGE",
     "news": "DOGEUSD", "etf": None, "groups": ("meme",)},
    {"symbol": "ADA", "name": "Cardano", "coingecko": "cardano", "coinbase": "ADA-USD", "perp": "ADA",
     "news": "ADAUSD", "etf": None, "groups": ("layer1",)},
    {"symbol": "LINK", "name": "Chainlink", "coingecko": "chainlink", "coinbase": "LINK-USD", "perp": "LINK",
     "news": "LINKUSD", "etf": None, "groups": ("defi",)},
    {"symbol": "SUI", "name": "Sui", "coingecko": "sui", "coinbase": "SUI-USD", "perp": "SUI",
     "news": "SUIUSD", "etf": None, "groups": ("layer1",)},
    {"symbol": "AVAX", "name": "Avalanche", "coingecko": "avalanche-2", "coinbase": "AVAX-USD", "perp": "AVAX",
     "news": "AVAXUSD", "etf": None, "groups": ("layer1",)},
    {"symbol": "BCH", "name": "Bitcoin Cash", "coingecko": "bitcoin-cash", "coinbase": "BCH-USD", "perp": "BCH",
     "news": "BCHUSD", "etf": None, "groups": ("payments",)},
    {"symbol": "LTC", "name": "Litecoin", "coingecko": "litecoin", "coinbase": "LTC-USD", "perp": "LTC",
     "news": "LTCUSD", "etf": None, "groups": ("payments",)},
    {"symbol": "PEPE", "name": "Pepe", "coingecko": "pepe", "coinbase": "PEPE-USD", "perp": "kPEPE",
     "news": "PEPEUSD", "etf": None, "groups": ("meme",)},
)
CRYPTO_CHART_DEFAULT = "BTC"

# -- the stocks crypto moves (the bridge panel); IBKR prices them --------------------------------------
CRYPTO_BRIDGE: tuple[dict, ...] = (
    {"symbol": "IBIT", "what": "BTC ETF", "driver": "BTC"},
    {"symbol": "ETHA", "what": "ETH ETF", "driver": "ETH"},
    {"symbol": "MSTR", "what": "Holds BTC", "driver": "BTC"},
    {"symbol": "COIN", "what": "Exchange", "driver": "BTC"},
    {"symbol": "MARA", "what": "Miner", "driver": "BTC"},
    {"symbol": "RIOT", "what": "Miner", "driver": "BTC"},
    {"symbol": "CLSK", "what": "Miner", "driver": "BTC"},
    {"symbol": "HOOD", "what": "Broker", "driver": "BTC"},
)
CRYPTO_BRIDGE_DRIVERS = ("BTC", "ETH")
CRYPTO_CORR_SYMBOL = "QQQ"                          # the Nasdaq 100, for BTC's 30-day correlation

# -- endpoints -----------------------------------------------------------------------------------------
CRYPTO_COINGECKO_BASE = "https://api.coingecko.com/api/v3"
CRYPTO_COINBASE_BASE = "https://api.exchange.coinbase.com"
CRYPTO_FEAR_GREED_URL = "https://api.alternative.me/fng/"
CRYPTO_HYPERLIQUID_URL = "https://api.hyperliquid.xyz/info"
CRYPTO_STABLES_CHART_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
CRYPTO_DERIBIT_URL = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
CRYPTO_HTTP_TIMEOUT_SEC = 10.0
CRYPTO_USER_AGENT = "Nova-desk/1 (+https://github.com/aaltaay/Nova)"
CRYPTO_COINBASE_MAX_CANDLES = 300                   # Coinbase answers at most this many per request
CRYPTO_COINBASE_PAGE_GAP_SEC = 0.25                 # between two pages of one series

# -- cadences (seconds) --------------------------------------------------------------------------------
CRYPTO_WANTED_SEC = 90.0                            # a read keeps the refreshers going this long
CRYPTO_TICK_SEC = 1.0
CRYPTO_MARKETS_TTL_SEC = 60.0
CRYPTO_GLOBAL_TTL_SEC = 120.0
CRYPTO_VOLUME_HISTORY_TTL_SEC = 6 * 3600.0
CRYPTO_VOLUME_HISTORY_GAP_SEC = 15.0                # CoinGecko's keyless limit: one history read per this
CRYPTO_PERPS_TTL_SEC = 60.0
CRYPTO_NEWS_TTL_SEC = 300.0
CRYPTO_SLOW_TTL_SEC = 1800.0                        # Fear & Greed, DefiLlama, Deribit
CRYPTO_RETRY_SEC = 60.0                             # after a failed read
CRYPTO_STALE_MAX_SEC = 900.0                        # a failing source's last answer is shown this long
CRYPTO_CANDLES_TTL_SEC = {"15m": 30.0, "1h": 120.0, "4h": 300.0, "1d": 900.0}
CRYPTO_CANDLE_TFS = ("15m", "1h", "4h", "1d")
CRYPTO_CANDLES_SHOWN = 96
CRYPTO_HOURLY_TTL_SEC = 6 * 3600.0                  # BTC / ETH hourly history: the 16:00 ET prices
CRYPTO_HOURLY_DAYS = 100                            # 60 sessions need about 87 calendar days
CRYPTO_BRIDGE_QUOTE_TTL_SEC = 60.0
CRYPTO_BRIDGE_CLOSES_RETRY_SEC = 600.0              # a session's bar not in yet: ask again this much later
CRYPTO_BRIDGE_CLOSES_DURATION = "6 M"               # IBKR durationStr for the regular-hours daily closes
CRYPTO_BRIDGE_REQUEST_GAP_SEC = 5.0                 # between two of the page's IBKR historical requests
CRYPTO_BRIDGE_SHED_RETRY_SEC = 30.0                 # IBKR's budget said later (an open chart, pacing)
CRYPTO_IBKR_TIMEOUT_SEC = 30.0
CRYPTO_LISTING_RETRY_SEC = 300.0
CRYPTO_LISTING_GAP_SEC = 1.0
CRYPTO_LISTING_VENUES = ("PAXOS", "ZEROHASH")       # IBKR's crypto venues

# -- the read ------------------------------------------------------------------------------------------
CRYPTO_BETA_DAYS = 60                               # sessions in a stock's beta to its coin
CRYPTO_BETA_MIN_DAYS = 20                           # fewer shared sessions: no beta
CRYPTO_CORR_DAYS = 30                               # sessions in BTC's correlation to the Nasdaq 100
CRYPTO_BRIDGE_READ_BAND_PT = 0.5                    # |stock - implied| within this many points: in line
CRYPTO_FUNDING_CROWDED_PCT = 0.03                   # funding per 8 h at or above: crowded longs
CRYPTO_FUNDING_SHORTS_PCT = -0.01                   # at or below: crowded shorts
CRYPTO_VOLUME_HOT_X = 2.0                           # 24 h volume at this many times its average: unusual
CRYPTO_VOLUME_AVG_DAYS = 30
CRYPTO_SPARK_POINTS = 84                            # the 7-day path, every second hour
CRYPTO_NEWS_WINDOW_SEC = 24 * 3600.0
CRYPTO_NEWS_PAGE_LIMIT = 50
CRYPTO_NEWS_MAX_PAGES = 3
CRYPTO_NEWS_MAX = 4
CRYPTO_NEWS_ROUNDUP_TICKERS = 3                     # an article naming more coins than this is a roundup
CRYPTO_NEXT_MAX = 4
CRYPTO_STABLES_DAYS = 10
CRYPTO_FUNDING_HOURS_UTC = (0, 8, 16)               # the 8-hour exchanges settle funding at these hours
CRYPTO_OPTIONS_EXPIRY_HOUR_UTC = 8                  # Deribit's expiries: 08:00 UTC, Fridays for weeklies

# Regions by their own clocks (weekdays; local holidays not modelled): Tokyo opens the Asian day and
# Hong Kong closes it; London is Europe.
CRYPTO_REGIONS: tuple[dict, ...] = (
    {"id": "asia", "open": ("Asia/Tokyo", 9, 0), "close": ("Asia/Hong_Kong", 16, 0)},
    {"id": "europe", "open": ("Europe/London", 8, 0), "close": ("Europe/London", 16, 30)},
)

CRYPTO_NO_LIQUIDATIONS_NOTE = ("No free source reachable from the desk reports liquidations; "
                               "they need a paid aggregate (for example Coinglass).")
CRYPTO_NO_ETF_FLOWS_NOTE = ("No free source publishes daily spot ETF flows as data; "
                            "the chart shows stablecoin supply until one exists.")
CRYPTO_ERR_UNKNOWN_SYMBOL = "CRYPTO_UNKNOWN_SYMBOL"
CRYPTO_ERR_UNKNOWN_TF = "CRYPTO_UNKNOWN_TF"
