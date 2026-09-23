"""Archive/R2 + news impact. Domain constants (Phase 3)."""
from constants_ibkr import *  # noqa: F403

ARCHIVE_DB_FILENAME = "archive.db"              # under paths.cache_dir(), not git-tracked
ARCHIVE_COLD_DIRNAME = "archive_cold"           # finished-day JSONL + manifests
ARCHIVE_HOT_RETENTION_DAYS = 30                 # hot window before a day is compact-eligible
ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM = True     # never timer-purge until remote verify
ARCHIVE_MAINTENANCE_ENABLED = False             # opt-in via env ARCHIVE_MAINTENANCE_ENABLED
ARCHIVE_MAINTENANCE_INTERVAL_SEC = 3600.0       # hourly stub when maintenance enabled
ARCHIVE_L1_MIN_UNIX_TS = 1_000_000_000.0        # reject epoch-0 / 1969-12-31 L1 stamps
SQLITE_BACKUP_DIRNAME = "backups"               # under cache_dir(), WAL-safe copies
SQLITE_BACKUP_RETENTION_DAYS = 7
SQLITE_BACKUP_FILENAMES = (
    "execution_ledger.db",
    "journal.db",
    "archive.db",
    "l2.db",
    "nova_os_events.db",
)
ARCHIVE_SOURCE_IBKR = "ibkr"
ARCHIVE_SOURCE_IBKR_L1 = "ibkr_l1"          # live 1Min overlay; never shares hist row identity
ARCHIVE_SOURCE_ALPACA = "alpaca"
ARCHIVE_STREAM_TAPE = "tape"
ARCHIVE_STREAM_L2 = "l2"
ARCHIVE_STREAM_BARS_1M = "bars_1m"
ARCHIVE_STREAM_BARS_1D = "bars_1d"
ARCHIVE_STREAM_L1_TICKS = "l1_ticks"
ARCHIVE_COUNTER_TAPE_RECEIVED = "tape_received"
ARCHIVE_COUNTER_TAPE_DROPPED = "tape_dropped"
ARCHIVE_COUNTER_L2_SNAPSHOTS = "l2_snapshots"
ARCHIVE_COUNTER_BARS_1M = "bars_1m"
ARCHIVE_COUNTER_BARS_1D = "bars_1d"
ARCHIVE_COUNTER_GAPS = "capture_gaps"
ARCHIVE_COUNTER_INCOMPLETE_WINDOWS = "incomplete_windows"
ARCHIVE_COUNTER_L1_TICKS = "l1_ticks"
ARCHIVE_COUNTER_ENRICHMENT_SNAPSHOTS = "enrichment_snapshots"
# Non-blocking archive writes (ADR 010): producers on the IB loop enqueue in
# memory; one writer drains batches off that loop. Bound the queue so a disk
# stall costs bounded RAM and counts drops instead of wedging the desk.
ARCHIVE_WRITE_QUEUE_MAX = 100_000        # rows held before oldest are dropped
ARCHIVE_WRITE_BATCH_MAX = 5_000          # rows per transaction
ARCHIVE_WRITE_FLUSH_SEC = 1.0            # drain cadence
ARCHIVE_TABLES_COLD = (
    "bars_1m",
    "bars_1d",
    "tape_ibkr",
    "l1_ticks",
    "enrichment_snapshots",
    "capture_gaps",
    "incomplete_windows",
)
# L2 depth snapshots + tape prints already live durably in the pre-existing
# l2/db.py hot store (l2/continuous.py samples at L2_CONTINUOUS_SNAPSHOT_INTERVAL_SEC
# whenever a depth session is open). These two tables are bridged into the same
# checksummed cold-archive + R2 pattern by archive/l2_bridge.py, but kept out of
# ARCHIVE_TABLES_COLD (a different sqlite file, no session_date column) so the
# existing bars/tape_ibkr compact+upload+restore contract is untouched.
ARCHIVE_TABLES_COLD_L2 = (
    "l2_snapshots",
    "tape_trades",
)
# Cloudflare R2 (P8) — credentials ONLY in .env (never commit). Env var names:
#   R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
#   ARCHIVE_R2_ENABLED=true to attempt uploads (still no-ops without keys)
#   R2_BUCKET (optional override of R2_BUCKET_DEFAULT)
ARCHIVE_R2_ENABLED = False
R2_BUCKET_DEFAULT = "nova-archive"
R2_PREFIX = "nova-os/archive/"                  # content-addressed keys under this prefix
R2_ENDPOINT_HOST_SUFFIX = "r2.cloudflarestorage.com"
ARCHIVE_R2_VERIFIED_INDEX = "_r2_verified.json"  # under archive_cold/
ARCHIVE_R2_VERIFIED_INDEX_L2 = "_r2_verified_l2.json"  # under archive_cold/ (l2_bridge)
# An archived 1m bar is stamped with the minute's OPENING ts; its final OHLCV is
# only known at bar_start + this. Replay projections must not reveal it earlier.
ARCHIVE_BAR_1M_INTERVAL_SEC = 60.0

# ── News impact decision layer (rules-first; not a black box) ────────────────
# Explicit thresholds for whether news actually moved a ticker / Level 2.
# Every value here is surfaced in NewsImpactVerdict.factors and UI tooltips.
# "Lincoln AI" reasoning (see below) fills ai_reasoning; rules stay authoritative.
NEWS_IMPACT_RULE_VERSION = "rules-v1"
NEWS_IMPACT_FRESH_HOURS = 2.0          # age ≤ this → fresh (mirrors NEWS_FLAME_HOT_HOURS)
NEWS_IMPACT_AGING_HOURS = 6.0          # age ≤ this → aging (still attributable)
NEWS_IMPACT_STALE_HOURS = 24.0         # age ≤ this → stale; above → expired
NEWS_IMPACT_STRONG_MOVE_PCT = 10.0     # |gap%| ≥ this → strong price reaction
NEWS_IMPACT_MILD_MOVE_PCT = 3.0        # |gap%| ≥ this → mild price reaction
NEWS_IMPACT_ATTENTION_RVOL = 2.0       # RVOL ≥ this → attention spike (mirrors REL_VOLUME_HIGH)
NEWS_IMPACT_L2_IMBALANCE_MIN = 0.35    # |bid/ask imbalance| ≥ this → L2 reacting
NEWS_IMPACT_MULTI_SOURCE_CONFIRM = 2   # ≥ this many major/official sources → confirmed
# Confidence floors/ceilings applied after rule scoring (0–1).
NEWS_IMPACT_CONFIDENCE_FLOOR = 0.15
NEWS_IMPACT_CONFIDENCE_CEILING = 0.95
# Source-name substrings (case-insensitive) for credibility tiers.
NEWS_IMPACT_OFFICIAL_SOURCE_KEYWORDS = (
    "sec", "edgar", "fda", "business wire", "globe newswire", "pr newswire",
    "accesswire", "company press", "investor relations",
)
NEWS_IMPACT_OFFICIAL_URL_KEYWORDS = (
    "sec.gov", "fda.gov", "businesswire.com", "globenewswire.com",
    "prnewswire.com", "accesswire.com",
)
NEWS_IMPACT_MAJOR_SOURCE_KEYWORDS = (
    "bloomberg", "reuters", "wsj", "wall street journal", "cnbc", "marketwatch",
    "benzinga", "dow jones", "associated press", "ap news", "financial times",
    "barron", "the street", "yahoo finance", "yahoo news", "yahoo",
)
NEWS_IMPACT_SECONDARY_SOURCE_KEYWORDS = (
    "motley fool", "seeking alpha", "investopedia", "zacks", "tipranks",
    "investorplace", "fool.com", "traders magazine", "markets media",
    "hedgeweek", "finextra", "techcrunch", "ars technica",
)

# ── Low-signal movers / listicle headlines (News column + flame) ────────────
# Owner: news.junk. Hard listicles never flame or drive news_impact.
# Frontend mirror: frontend/src/constantGroups/news_junk.ts
NEWS_JUNK_HEADLINE_RES = (
    r"\b\d+\s+(?:\S+\s+){0,6}stocks?\s+moving\b",
    r"\bstocks?\s+moving\s+in\b.*\b("
    r"after[- ]?market|after[- ]?hours|pre[- ]?market|premarket|mid[- ]?day)\b",
)
NEWS_JUNK_HEADLINE_PHRASES = (
    "stocks to watch",
    "gainers and losers",
    "most active stocks",
    "movers recap",
    "biggest movers",
    "top movers",
    "today's movers",
    "todays movers",
    "premarket movers",
    "pre-market movers",
    "after-hours movers",
    "after hours movers",
    "after-market movers",
    "after market movers",
    "midday movers",
    "overnight movers",
)
NEWS_JUNK_SECTOR_ROUNDUP_RE = (
    r"\b(?:health\s*care|healthcare|biotech|technology|tech|energy|financial|"
    r"banks?|retail|industrial|consumer|semiconductor|china|crypto|pharma)"
    r"\s+stocks\s+(?:moving|to\s+watch|roundup|recap|in\s+focus)\b"
)
NEWS_JUNK_URL_FRAGMENTS = (
    "/trading-ideas/movers/",
    "/after-hours-movers",
    "/premarket-movers",
    "/pre-market-movers",
)
# Company-specific catalyst language. Overrides sector-roundup only -- never
# the hard "N stocks moving" / movers-URL class.
NEWS_SIGNAL_HEADLINE_KEYWORDS = (
    "earnings",
    "fda",
    "sec filing",
    "8-k",
    "8k",
    "10-q",
    "10-k",
    "acquires",
    "acquired",
    "acquisition",
    "merger",
    "buyout",
    "offering",
    "bankruptcy",
    "guidance",
    "pdufa",
    "phase 3",
    "phase iii",
    "clinical trial",
    "press release",
)

# ── Nova News desk (AI-in-trading headlines -- not a price feed, not HOD) ─
# Owner: nova_news.desk. Invalidation: TTL expiry or schema bump.
# Disk snapshot lives under paths.cache_dir() / NOVA_NEWS_DESK_CACHE_FILENAME.
# Beat: AI used in trading. Not a general market wire. Not "AI stocks to buy."
NOVA_NEWS_DESK_SCHEMA_VERSION = 2
NOVA_NEWS_DESK_TTL_SEC = 120.0
NOVA_NEWS_DESK_HTTP_TIMEOUT_SEC = 8.0
NOVA_NEWS_DESK_MAX_STORIES = 120
NOVA_NEWS_DESK_CACHE_FILENAME = "nova-news-desk.json"
NOVA_NEWS_HTTP_USER_AGENT = "NovaNews/1.0 (+https://github.com/aaltaay/Nova)"
FINNHUB_MARKET_NEWS_URL = "https://finnhub.io/api/v1/news"
FINNHUB_NEWS_CATEGORIES = ("general", "merger")
_GNEWS = "https://news.google.com/rss/search?q={}&hl=en-US&gl=US&ceid=US:en"
# Targeted Google News searches. Broad "AI trading" union queries were tried
# and mostly returned AI-as-a-hot-stock coverage.
NOVA_NEWS_SEARCH_FEEDS = (
    ("gnews_algo", "AI trading", _GNEWS.format(
        "%22algorithmic+trading%22+OR+%22AI+trading%22+OR+%22trading+algorithm%22+when:14d")),
    ("gnews_quant", "Quant / AI funds", _GNEWS.format(
        "%22quant+fund%22+OR+%22quantitative+trading%22+OR+%22AI+hedge+fund%22+"
        "OR+%22systematic+trading%22+when:14d")),
    ("gnews_hf", "AI hedge funds", _GNEWS.format(
        "%22artificial+intelligence%22+%22hedge+fund%22+when:14d")),
    ("gnews_ml_exec", "ML execution", _GNEWS.format(
        "%22machine+learning%22+%22market+making%22+OR+%22trade+execution%22+"
        "OR+%22order+flow%22+when:14d")),
    ("gnews_agents", "AI agents / bots", _GNEWS.format(
        "%22AI+agents%22+trading+OR+%22autonomous+trading%22+OR+%22trading+bots%22+when:14d")),
    ("gnews_trade_press", "Trade press AI", _GNEWS.format(
        "%28AI+OR+%22artificial+intelligence%22%29+trading+site:thetradenews.com+OR+"
        "site:waterstechnology.com+OR+site:risk.net+OR+site:institutionalinvestor.com+"
        "OR+site:pionline.com+when:30d")),
    ("gnews_wires", "Wires AI trading", _GNEWS.format(
        "%22artificial+intelligence%22+trading+site:reuters.com+OR+site:bloomberg.com+"
        "OR+site:wsj.com+OR+site:ft.com+when:30d")),
    ("gnews_yahoo", "Yahoo AI trading", _GNEWS.format(
        "%28AI+OR+%22artificial+intelligence%22%29+trading+site:finance.yahoo.com+OR+"
        "site:news.yahoo.com+when:14d")),
)
# Publisher RSS that actually covers this beat. Generic stock wires stay out.
NOVA_NEWS_OUTLET_FEEDS = (
    ("ft_markets", "FT Markets", "https://www.ft.com/markets?format=rss"),
    ("ft_tech", "FT Technology", "https://www.ft.com/technology?format=rss"),
    ("cnbc_tech", "CNBC Technology", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910"),
    ("techcrunch_ai", "TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("mit_tr", "MIT Technology Review", "https://www.technologyreview.com/feed/"),
    ("wired", "WIRED Business", "https://www.wired.com/feed/category/business/latest/rss"),
    ("ars", "Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("traders_magazine", "Traders Magazine", "https://www.tradersmagazine.com/feed/"),
    ("markets_media", "Markets Media", "https://www.marketsmedia.com/feed/"),
    ("hedgeweek", "Hedgeweek", "https://www.hedgeweek.com/feed/"),
    ("finextra", "Finextra", "https://www.finextra.com/rss/headlines.aspx"),
    ("arxiv_qfin", "arXiv q-fin.TR", "http://export.arxiv.org/rss/q-fin.TR"),
)
NOVA_NEWS_AI_TERMS = (
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "large language model", "generative ai", "genai",
    "reinforcement learning", "foundation model", "transformer model",
    "ai model", "ai system", "ai tool", "ai agent", "agentic", "chatgpt",
    "openai", "anthropic", "deepmind", "llm", "algorithm", "ai",
)
NOVA_NEWS_MARKET_TERMS = (
    "trading", "trader", "trade", "trades", "trade desk", "trading desk",
    "hedge fund", "quant", "quantitative", "asset manager",
    "asset management", "portfolio", "market maker", "market making",
    "broker", "brokerage", "order flow", "order execution",
    "trade execution", "backtest", "buy-side", "sell-side", "buy side",
    "proprietary trading", "wealth management", "stock picking",
    "securities trading", "high-frequency", "market microstructure",
    "invest", "invests", "investing", "investment",
    "wall street", "capital markets", "stock market",
    "equities", "fund manager", "money manager",
)
NOVA_NEWS_HIGH_SIGNAL_PHRASES = (
    "algorithmic trading", "algo trading", "ai trading", "ai-powered trading",
    "ai-driven trading", "trading algorithm", "trading bot", "trading model",
    "quantitative trading", "systematic trading", "high-frequency trading",
    "quant fund", "quant hedge fund", "ai hedge fund",
    "execution algorithm", "alpha generation", "signal generation",
    "portfolio optimization", "robo-advisor", "robo-adviser",
    "market microstructure", "ai analyst", "autonomous trading",
    "trading strategy", "ai in markets",
)
NOVA_NEWS_FUND_KEYWORDS = (
    "hedge fund", "quant fund", "quant", "asset manager", "asset management",
    "systematic trading", "proprietary trading", "fund manager",
)
NOVA_NEWS_RESEARCH_KEYWORDS = (
    "arxiv", "preprint", "working paper", "q-fin", "white paper",
)
NOVA_NEWS_NOISE_PHRASES = (
    "stocks to buy", "best ai stocks", "top 5", "top 10", "top 3",
    "should you buy", "price prediction", "price target",
    "motley fool", "sponsored", "prnewswire", "penny stock",
)
NOVA_NEWS_REGULATORY_KEYWORDS = (
    "sec charges", "doj", "subpoena", "trading halt", "halted",
    "enforcement", "investigation",
)
NOVA_NEWS_BOUNDED_TERMS = frozenset({
    "ai", "llm", "genai", "quant", "trade", "trades", "broker",
    "invest", "invests", "investing", "investment",
})
NOVA_NEWS_CRITICAL_MIN_SCORE = 70
NOVA_NEWS_HIGH_MIN_SCORE = 45
NOVA_NEWS_WATCH_MIN_SCORE = 25
NOVA_NEWS_TIER_POINTS = {
    "official": 40,
    "major": 25,
    "secondary": 12,
    "unknown": 8,
    "none": 0,
}
NOVA_NEWS_CRITICALITY_ORDER = ("critical", "high", "watch", "background")

# ── News language understanding (FinBERT sentiment + Lincoln AI narrative) ───
# FinBERT (ProsusAI/finbert) reads the headline text itself and returns a
# positive/negative/neutral label. It runs locally (no API key, no per-call
# cost). Classify never loads the model -- warmup is a background thread at
# startup (D-015). Informational only; never changes impact_class/confidence.
NEWS_SENTIMENT_ENABLED = True
NEWS_SENTIMENT_MODEL_NAME = "ProsusAI/finbert"
NEWS_SENTIMENT_CACHE_MAX_ENTRIES = 500
# Finnhub free-tier 429 with no Retry-After header (calendar + logos share this).
FINNHUB_RETRY_AFTER_DEFAULT_SEC = 60.0
EARNINGS_ERROR_MISSING_KEY = "missing_key"
EARNINGS_ERROR_RATE_LIMITED = "rate_limited"

# Loughran-McDonald financial lexicon (pysentiment2) — a hand-built financial
# word list, not a fine-tuned model. Zero GPU/model-download cost, so it runs
# alongside FinBERT as a second, instant, independent read of the headline.
# Also purely informational; never changes impact_class/confidence.
NEWS_LEXICON_ENABLED = True
NEWS_LEXICON_CACHE_MAX_ENTRIES = 500

# Lincoln AI — optional LLM narrative that fills NewsImpactVerdict.ai_reasoning
# with a plain-English read of the catalyst type. Off by default: it calls an
# external API and costs money, so it mirrors the IBKR opt-in gate pattern
# (env var overrides this default; see .env.example). Requires OPENAI_API_KEY.
LINCOLN_AI_ENABLED = False
LINCOLN_AI_MODEL = "gpt-4o-mini"
LINCOLN_AI_MAX_TOKENS = 220
LINCOLN_AI_TEMPERATURE = 0.2
LINCOLN_AI_TIMEOUT_SECONDS = 8.0
LINCOLN_AI_CACHE_MAX_ENTRIES = 200

# ── Nova OS — decision brain + audit (Phases P1–P2) ──────────────────────────
# Nova OS is Nova's auditable decision + operations layer. P1 laid the audit
# foundation (event log + vocabulary). P2 adds `decide()` gate composition.
# Everything below is the single source of truth for codes and tunables so the
# event schema, read API, and decide() all speak the same language.
#
# Stability contract: these code strings are persisted in the event log and
