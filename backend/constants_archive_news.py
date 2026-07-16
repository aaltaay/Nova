"""Archive/R2 + news impact. Domain constants (Phase 3)."""
from constants_ibkr import *  # noqa: F403

ARCHIVE_DB_FILENAME = "archive.db"              # under paths.cache_dir(), not git-tracked
ARCHIVE_COLD_DIRNAME = "archive_cold"           # finished-day JSONL + manifests
ARCHIVE_HOT_RETENTION_DAYS = 30                 # hot window before a day is compact-eligible
ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM = True     # never timer-purge until remote verify
ARCHIVE_MAINTENANCE_ENABLED = False             # opt-in via env ARCHIVE_MAINTENANCE_ENABLED
ARCHIVE_MAINTENANCE_INTERVAL_SEC = 3600.0       # hourly stub when maintenance enabled
ARCHIVE_SOURCE_IBKR = "ibkr"
ARCHIVE_SOURCE_ALPACA = "alpaca"
ARCHIVE_STREAM_TAPE = "tape"
ARCHIVE_STREAM_L2 = "l2"
ARCHIVE_STREAM_BARS_1M = "bars_1m"
ARCHIVE_STREAM_BARS_1D = "bars_1d"
ARCHIVE_COUNTER_TAPE_RECEIVED = "tape_received"
ARCHIVE_COUNTER_TAPE_DROPPED = "tape_dropped"
ARCHIVE_COUNTER_L2_SNAPSHOTS = "l2_snapshots"
ARCHIVE_COUNTER_BARS_1M = "bars_1m"
ARCHIVE_COUNTER_BARS_1D = "bars_1d"
ARCHIVE_COUNTER_GAPS = "capture_gaps"
ARCHIVE_COUNTER_INCOMPLETE_WINDOWS = "incomplete_windows"
ARCHIVE_TABLES_COLD = (
    "bars_1m",
    "bars_1d",
    "tape_ibkr",
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
# Replay / evening review (P9)
ARCHIVE_EVENING_REVIEW_HORIZON_MIN = 5         # minutes after decision for outcome heuristic
# v2 (2026-07-15 hardening): v1 fed decide() the *entire* archived day's bars
# for one decision per symbol (hindsight — decide() could see the close before
# "deciding"), and scored outcome by looking backward from the day's last bar
# instead of forward from the actual decision moment. v2 walks the day in
# ARCHIVE_REPLAY_WALK_STEP_MIN steps, slicing bars to ts <= as_of at decision
# time, and scores outcome forward from that same as_of.
ARCHIVE_EVENING_REVIEW_VERSION = "evening-review-v2-2026-07-15"
ARCHIVE_REPLAY_MAX_SYMBOLS = 50
ARCHIVE_REPLAY_WALK_STEP_MIN = 5               # minutes between as-of snapshots in walk_day
ARCHIVE_REPLAY_WALK_MAX_STEPS = 200            # hard cap on snapshots per walk (safety)
ARCHIVE_EVENING_REVIEW_MAX_SYMBOLS = 10        # walk_day is O(steps x symbols); keep review scoped

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
    "barron", "the street", "yahoo finance",
)
NEWS_IMPACT_SECONDARY_SOURCE_KEYWORDS = (
    "motley fool", "seeking alpha", "investopedia", "zacks", "tipranks",
    "investorplace", "fool.com",
)

# ── News language understanding (FinBERT sentiment + Lincoln AI narrative) ───
# FinBERT (ProsusAI/finbert) reads the headline text itself and returns a
# positive/negative/neutral label. It runs locally (no API key, no per-call
# cost), lazily loading the model on first real headline. It is informational
# only — it never changes impact_class/confidence, so the rules stay the
# visible, authoritative decision layer per this module's own contract.
NEWS_SENTIMENT_ENABLED = True
NEWS_SENTIMENT_MODEL_NAME = "ProsusAI/finbert"
NEWS_SENTIMENT_CACHE_MAX_ENTRIES = 500

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
