"""The Market page's tunables and reference tables (ADR 053).

Owner: backend/market_board/. Mirrors: frontend/src/market_board/constants.ts (periods, labels). Every price comes
from IBKR; the calendars below are copied from the published sources named beside them and need a new row when the
source publishes the next year.
"""
from __future__ import annotations

from types import MappingProxyType

MARKET_ENV = "NOVA_MARKET_BOARD"                 # "0" turns every refresher off
MARKET_SCHEMA_VERSION = 1
MARKET_PERIODS = ("1D", "7D", "30D")
MARKET_PERIOD_SESSIONS = MappingProxyType({"1D": 1, "7D": 5, "30D": 21})
MARKET_TOP_KINDS = ("movers", "biggest", "runners")
MARKET_ERR_BAD_PARAM = "MARKET_BAD_PARAM"

# -- who is looking, and how often each read runs -------------------------------------------------------------------
MARKET_WANTED_SEC = 30.0                         # a board read keeps the refreshers going this long
MARKET_TICK_SEC = 0.5                            # a refresher's sleep when nothing was due
MARKET_RETRY_SEC = 60.0                          # a failed read is tried again after this
MARKET_STALE_MAX_SEC = 900.0                     # a failed read keeps its last answer at most this long
MARKET_QUOTES_TTL_SEC = 10.0                     # futures / indexes / crypto snapshots
MARKET_LINES_TTL_SEC = 300.0                     # their 5-minute bar lines
MARKET_ETF_TTL_SEC = 60.0                        # sector and industry ETF snapshots
MARKET_MOVERS_TTL_SEC = 120.0                    # the large-cap gainers scan and its snapshots
MARKET_HOLDINGS_QUOTES_TTL_SEC = 90.0            # the biggest names' snapshots (only while that tab shows)
MARKET_CLOSES_RETRY_SEC = 900.0                  # daily closes not yet holding the last session
MARKET_SHED_RETRY_SEC = 20.0                     # the historical service said "later"
MARKET_HISTORY_GAP_SEC = 2.0                     # between two paced historical requests of this page
MARKET_FILES_TTL_SEC = 12 * 3600.0               # BEA calendar, earnings
MARKET_HOLDINGS_TTL_SEC = 20 * 3600.0            # a State Street holdings file
MARKET_CLIMATE_TTL_SEC = 60.0                    # today's climate from the leaderboard store
MARKET_INDUSTRY_GAP_SEC = 0.35                   # between two IBKR contract-details reads
MARKET_INDUSTRY_MAX_AGE_DAYS = 90                # a cached industry older than this is asked again
MARKET_INDUSTRY_BATCH = 40                       # industries asked per refresher turn

# -- IBKR budget: the page holds a line only for a moment (ADR 053 amendment 2026-10-13) -----------------------------
# Lines free beyond Nova's own reserve (IBKR_L1_STREAM_RESERVE, kept for an opening Trader tab) before the page
# opens any. IBKR shares the account's lines with every other platform the login uses; on 2026-10-13
# Nova could hold only 45 of its 100, all but the reserve taken by HOD Momo.
MARKET_MIN_FREE_LINES = 6
# A quote is read from a line opened, read and cancelled at once -- not a snapshot, which waits for IBKR's
# snapshot end (~11 s a batch for futures, indexes and stocks outside the session, measured 2026-10-13).
MARKET_STREAM_BATCH = 5                          # lines open at once: as many as a stock snapshot held, < MIN_FREE
MARKET_STREAM_WAIT_SEC = 2.5                     # a batch's lines are cancelled by then, answered or not
MARKET_STREAM_SETTLE_SEC = 0.4                   # every line has a price: wait this much more for prior closes
MARKET_STREAM_POLL_SEC = 0.05                    # how often a batch looks at its tickers
# Without free lines the page reads prices from bars (historical requests hold no line).
MARKET_BARS_LINE_TTL_SEC = 120.0                 # a tile's 5-minute bars, when its snapshot is missing
MARKET_BARS_QUOTES_TTL_SEC = 300.0               # ETFs' / movers' regular-session daily bars
MARKET_BARS_MOVERS_MAX = 20                      # movers read from bars at most this many
MARKET_BARS_FRESH_SEC = 900.0                    # a bar-read price older than this is not shown
MARKET_PRIOR_DURATION = "5 D"                    # a tile's daily bars, for its prior close without a snapshot
MARKET_IBKR_TIMEOUT_SEC = 12.0                   # one qualify / contract-details read
MARKET_HISTORY_TIMEOUT_SEC = 25.0                # one paced historical request
MARKET_LINE_BAR = "5 mins"                       # the tiles' intraday line
MARKET_LINE_DURATION = "1 D"
MARKET_LINE_START_MIN_ET = 4 * 60                # the line starts at 04:00 ET
MARKET_CLOSES_DURATION = "45 D"                  # daily closes for the 7 D / 30 D moves (21 sessions + margin)

# -- the tiles (tile order) -------------------------------------------------------------------------------------------
# sec_type CONTFUT: the front month is found through IBKR's continuous future and streamed by its own conId.
MARKET_QUOTES = (
    {"id": "es", "label": "S&P 500 futures", "symbol": "ES", "sec_type": "CONTFUT", "exchange": "CME"},
    {"id": "nq", "label": "Nasdaq 100 futures", "symbol": "NQ", "sec_type": "CONTFUT", "exchange": "CME"},
    {"id": "rty", "label": "Russell 2000 futures", "symbol": "RTY", "sec_type": "CONTFUT", "exchange": "CME"},
    {"id": "ym", "label": "Dow futures", "symbol": "YM", "sec_type": "CONTFUT", "exchange": "CBOT"},
    {"id": "vix", "label": "VIX fear gauge", "symbol": "VIX", "sec_type": "IND", "exchange": "CBOE"},
    {"id": "tnx", "label": "10-year yield", "symbol": "TNX", "sec_type": "IND", "exchange": "CBOE"},
    {"id": "cl", "label": "Crude oil futures", "symbol": "CL", "sec_type": "CONTFUT", "exchange": "NYMEX"},
    {"id": "gc", "label": "Gold futures", "symbol": "GC", "sec_type": "CONTFUT", "exchange": "COMEX"},
    {"id": "btc", "label": "Bitcoin", "symbol": "BTC", "sec_type": "CRYPTO", "exchange": "ZEROHASH"},
    {"id": "small_caps", "label": "Small caps vs S&P", "symbol": "RTY - ES", "sec_type": "SPREAD", "exchange": ""},
)
MARKET_SPREAD_LEGS = ("rty", "es")               # the small-caps tile: RTY's change minus ES's, in points
MARKET_INDEX_FUTURES = ("es", "nq", "rty", "ym") # the day read's "futures up across the board"
# Cboe quotes its yield indexes at ten times the yield (TNX 41.2 = 4.12%); a reading at or above this is scaled.
MARKET_TNX_TENTHS_ABOVE = 20.0

# NYSE market indicators (IBKR TWS API "Market Indicators"): IND on NYSE.
MARKET_BREADTH = MappingProxyType({
    "ad": "AD-NYSE",       # bid = advancing issues, ask = declining, bid size = unchanged
    "vol": "VOL-NYSE",     # bid = up volume, ask = down volume
    "tick": "TICK-NYSE",   # last = upticks minus downticks
    "trin": "TRIN-NYSE",   # last = TRIN
})
MARKET_BREADTH_SAMPLE_SEC = 60.0                 # one breadth snapshot a minute, 09:30-16:00 ET
MARKET_BREADTH_KEEP_DAYS = 10                    # breadth-<date>.json files kept
MARKET_BREADTH_STALE_SEC = 180.0                 # in the session, a sample older than this is not current breadth

# -- sectors and industries ------------------------------------------------------------------------------------------
MARKET_SECTORS = (
    ("Technology", "XLK"), ("Communication", "XLC"), ("Consumer disc.", "XLY"), ("Industrials", "XLI"),
    ("Financials", "XLF"), ("Materials", "XLB"), ("Health care", "XLV"), ("Real estate", "XLRE"),
    ("Staples", "XLP"), ("Utilities", "XLU"), ("Energy", "XLE"),
)
MARKET_OFFENSE = ("XLK", "XLY", "XLC")
MARKET_DEFENSE = ("XLP", "XLU", "XLV")
# (name, ETF, State Street publishes its holdings file) -- the rest are theme ETFs with no member file Nova reads.
MARKET_INDUSTRIES = (
    ("Biotech", "XBI", True), ("Crypto stocks", "WGMI", False), ("Quantum", "QTUM", False),
    ("Nuclear & uranium", "URA", False), ("Semiconductors", "SMH", False), ("AI & robotics", "BOTZ", False),
    ("Software", "IGV", False), ("China internet", "KWEB", False), ("Airlines", "JETS", False),
    ("Regional banks", "KRE", True), ("Gold miners", "GDX", False), ("Homebuilders", "XHB", True),
    ("Solar", "TAN", False), ("Cannabis", "MSOS", False), ("Oil & gas producers", "XOP", True),
)
MARKET_NO_MEMBER_FILE_WHY = "no member list for this ETF"
MARKET_HOLDINGS_URL = ("https://www.ssga.com/library-content/products/fund-data/etfs/us/"
                       "holdings-daily-us-en-{ticker}.xlsx")
MARKET_HOLDINGS_MAX_BYTES = 4_000_000
# A kept holdings file older than this is not used when State Street cannot be read (a weekend and a failed day).
MARKET_HOLDINGS_MAX_AGE_SEC = 5 * 86400.0
MARKET_BIGGEST_PER_SECTOR = 5                    # the "Biggest names" rows and the 7 D / 30 D leader pool
MARKET_LEADER_POOL = 5
MARKET_TOP_CARDS = 6
MARKET_TOP_ROWS = 5
# IBKR's large-cap gainers scan (marketCapAbove is in millions of USD, IB wire units).
MARKET_MOVERS_SCAN = MappingProxyType({
    "scanCode": "TOP_PERC_GAIN", "marketCapAbove": 5_000, "abovePrice": 5.0, "stockTypeFilter": "CORP",
})
MARKET_MOVERS_ROWS = 50

# -- the day read -----------------------------------------------------------------------------------------------------
MARKET_DAY_READ_BULLISH_NET = 3                  # green - red at or above: bullish
MARKET_DAY_READ_BEARISH_NET = 3                  # red - green at or above: bearish
MARKET_DAY_READ_MIN_KNOWN = 3                    # fewer known checks: no verdict
MARKET_DAY_READ_FUTURES_GREEN = 3                # of ES, NQ, RTY, YM up: green; down: red
MARKET_DAY_READ_BREADTH_RATIO = 1.5              # advancing / declining at or above: green; at or below 1/x: red
MARKET_DAY_READ_VIX_PCT = 3.0                    # VIX down this much or more: green; up: red
MARKET_DAY_READ_SMALL_CAPS_PT = 0.25             # RTY - ES at or above: green; at or below minus: red
MARKET_DAY_READ_RUNNERS_X = 1.25                 # runners over their average: green at x, red at 1/x
MARKET_DAY_READ_GAPPERS_GREEN_PCT = 60.0         # gappers holding their open: green at or above
MARKET_DAY_READ_GAPPERS_RED_PCT = 40.0           # red at or below
MARKET_DAY_READ_GAPPERS_MIN = 3                  # fewer gappers seen: unknown

# -- the small-cap climate (leaderboard store, ADR 023) ---------------------------------------------------------------
MARKET_CLIMATE_THRESHOLDS = MappingProxyType({"up20": 0.20, "up50": 0.50, "up100": 1.00})   # fractions
MARKET_CLIMATE_RANK_MAX = 50                     # one lens on recorded and rebuilt days: the board's first 50
MARKET_CLIMATE_RECORDED_BOARD = "gainers"
MARKET_CLIMATE_REBUILT_BOARD = "market"
# Rebuilt days rank every listed stock's minute bars and run ~40% hotter than IBKR's scan: left out of the lens.
MARKET_CLIMATE_USE_REBUILT = False
MARKET_CLIMATE_GAPPER_MIN = 0.20                 # an open gap of 20%+ is a gapper
MARKET_CLIMATE_BASELINE_DAYS_1D = 20             # 1 D: the same minute on the prior 20 covered sessions
MARKET_CLIMATE_BASELINE_DAYS = 60                # 7 D / 30 D: the per-session average of the prior 60
MARKET_CLIMATE_CHART_SESSIONS = 21
MARKET_CLIMATE_HOT_X = 1.25
MARKET_CLIMATE_COLD_X = 0.75
MARKET_CLIMATE_TOP = 3
MARKET_CLIMATE_HALT_SOURCE = "nasdaq_trade_halt_rss"
MARKET_UNCLASSIFIED = "Unclassified"

# -- events -----------------------------------------------------------------------------------------------------------
MARKET_EVENTS_DAYS_AHEAD = 2                     # today and the next two calendar days
MARKET_EVENTS_MAX = 6
MARKET_BEA_URL = "https://apps.bea.gov/API/signup/release_dates.json"
MARKET_BEA_RELEASES = MappingProxyType({         # BEA release name -> the page's title
    "Gross Domestic Product": "GDP",
    "Personal Income and Outlays": "PCE inflation and spending",
})
MARKET_HTTP_TIMEOUT_SEC = 20.0
MARKET_HTTP_USER_AGENT = "Nova-desk/1.0 (market board)"
# BLS blocks scripts without a contact email, so its 2026 schedule is copied here from
# https://www.bls.gov/schedule/2026/{10,11,12}_sched_list.htm (read 2026-10-13); ET times.
MARKET_BLS_RELEASES = (
    ("2026-10-14T08:30", "CPI", "Consumer Price Index for September"),
    ("2026-10-15T08:30", "PPI", "Producer Price Index for September"),
    ("2026-10-30T08:30", "Employment Cost Index", "Third quarter 2026"),
    ("2026-11-03T10:00", "JOLTS", "Job openings for September"),
    ("2026-11-06T08:30", "Jobs report", "Employment Situation for October"),
    ("2026-11-10T08:30", "CPI", "Consumer Price Index for October"),
    ("2026-11-13T08:30", "PPI", "Producer Price Index for October"),
    ("2026-12-01T10:00", "JOLTS", "Job openings for October"),
    ("2026-12-04T08:30", "Jobs report", "Employment Situation for November"),
    ("2026-12-10T08:30", "CPI", "Consumer Price Index for November"),
    ("2026-12-15T08:30", "PPI", "Producer Price Index for November"),
)
# FOMC decisions (statement 14:00 ET on the meeting's second day), from
# https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm (read 2026-10-12).
MARKET_FOMC_DECISIONS = (
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28",
    "2026-12-09",
)
MARKET_FOMC_TIME_ET = "14:00"
# SIFMA's US bond-market recommendations, from https://www.sifma.org/resources/general/holiday-schedule/
# (read 2026-10-13). Only the days the NYSE is open matter on the page; early closes are 14:00 ET.
MARKET_BOND_CLOSED = MappingProxyType({"2026-10-12": "Columbus Day", "2026-11-11": "Veterans Day"})
MARKET_BOND_EARLY_CLOSE = MappingProxyType({
    "2026-11-27": "Day after Thanksgiving", "2026-12-24": "Christmas Eve", "2026-12-31": "New Year's Eve",
})
MARKET_BOND_EARLY_CLOSE_ET = "14:00"
