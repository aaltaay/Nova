"""The Global page's tunables and its markets (ADR 060).

Owner: backend/global_board/. Mirrors: frontend/src/global_board/constants.ts (periods, regions). Every number on the
page is IBKR's: each market's index, its index future and its US-listed country ETF are IBKR contracts, and each
market's hours are its exchange's published regular session in its own time zone.
"""
from __future__ import annotations

from types import MappingProxyType

GLOBAL_ENV = "NOVA_GLOBAL_BOARD"                 # "0" turns the page's reads off
GLOBAL_WARM_ENV = "NOVA_GLOBAL_BOARD_WARM"       # "0": reads only while the page is open (no background cadence)
GLOBAL_SCHEMA_VERSION = 1
GLOBAL_PERIODS = ("1D", "7D", "30D")
GLOBAL_PERIOD_SESSIONS = MappingProxyType({"7D": 5, "30D": 21})
GLOBAL_ERR_BAD_PARAM = "GLOBAL_BAD_PARAM"
GLOBAL_PACE_KIND = "global"                      # the pacing book's name for this page (capacity strip: History)

# -- who is looking, and how often each read runs -------------------------------------------------------------------
GLOBAL_WANTED_SEC = 30.0                         # a board read keeps the reads going this long
GLOBAL_TICK_SEC = 1.0                            # the reader's sleep when nothing was due and the page is open
GLOBAL_IDLE_WAIT_SEC = 15.0                      # ... and when nobody looks
GLOBAL_RETRY_SEC = 120.0                         # a failed read is tried again after this
GLOBAL_SHED_RETRY_SEC = 30.0                     # the historical service or the line budget said "later"
GLOBAL_REFUSED_RETRY_SEC = 6 * 3600.0            # an instrument IBKR refused is not asked again before this
GLOBAL_FLOW_TTL_SEC = 300.0                      # an open market's flow while the page shows
GLOBAL_IDLE_FLOW_TTL_SEC = 900.0                 # ... while nobody looks (never in the desk's own hours, below)
GLOBAL_QUOTES_TTL_SEC = 60.0                     # the index quotes (a line held for a moment) while the page shows
GLOBAL_IDLE_QUOTES_TTL_SEC = 600.0               # ... while nobody looks
GLOBAL_STALE_MAX_SEC = 2 * 86400.0               # a read's last answer is shown at most this long after it
# Nobody looking: no read from the open to the close of the US regular session, the desk's own hours (ET minutes).
GLOBAL_QUIET_FROM_MIN_ET = 9 * 60 + 30
GLOBAL_QUIET_TO_MIN_ET = 16 * 60

# -- IBKR budget: Global reads last (ADR 060 decision 5) -------------------------------------------------------------
GLOBAL_HISTORY_HEADROOM = 30                     # no historical request while this few of the 10-minute 60 are left:
#   charts, the short check, the TraderTV exits and LULD (20) come first; the Market page stops at the same 30, so
#   the two take turns. At 40 the Market page's warm reads kept Global waiting for good (operator, 2026-10-20).
GLOBAL_YIELD_HEADROOM = 40                       # ... while the Market page shows and this one does not: the page
#   on screen goes first (and while this one shows, the Market page is not on screen).
GLOBAL_HISTORY_GAP_SEC = 2.0                     # between two of this page's historical requests, the Market page's
#   own pace (MARKET_HISTORY_GAP_SEC), so neither takes every request the window frees.
GLOBAL_IBKR_TIMEOUT_SEC = 8.0                    # a contract qualify
GLOBAL_HISTORY_TIMEOUT_SEC = 60.0                # one historical request, end to end through the bridge
GLOBAL_FLOW_BAR = "1 min"
GLOBAL_FLOW_DURATION = "2 D"                     # the session shown and the one before it (the move's prior close)
GLOBAL_DAILY_DURATION = "3 M"                    # 21 sessions back and room for holidays
GLOBAL_FX_DURATION = "5 D"

# -- the read and the flags ------------------------------------------------------------------------------------------
GLOBAL_READ_MIN_FLOWS = 4                        # fewer markets with a flow in dollars: no verdict
GLOBAL_READ_NET_PCT = 5.0                        # the world's pressure at or past this: money in / money out
GLOBAL_READ_REGION_PCT = 5.0                     # rotation: one region at or past +this, another at or past -this
GLOBAL_MIXED_PRESSURE_PCT = 5.0                  # a market's pressure and move disagree only past both of these
GLOBAL_MIXED_MOVE_PCT = 0.15
GLOBAL_SUN_HOURS = 24

# -- kept across restarts (global_board/keep.py) ---------------------------------------------------------------------
GLOBAL_KEEP_DIR = "global-board"
GLOBAL_KEEP_FILE = "global-store.json"
GLOBAL_KEEP_SAVE_SEC = 60.0
GLOBAL_KEEP_MAX_AGE_SEC = 2 * 86400.0

GLOBAL_REGIONS = MappingProxyType({
    "americas": "Americas",
    "europe": "Europe",
    "middle_east_africa": "Middle East & Africa",
    "asia_pacific": "Asia-Pacific",
})

# IBKR's forex pair for a currency, and whether its price is US dollars per unit (EUR.USD) or units per dollar.
GLOBAL_FX_PAIRS = MappingProxyType({
    "EUR": ("EURUSD", True), "GBP": ("GBPUSD", True), "AUD": ("AUDUSD", True),
    "CAD": ("USDCAD", False), "CHF": ("USDCHF", False), "JPY": ("USDJPY", False),
    "HKD": ("USDHKD", False), "KRW": ("USDKRW", False), "INR": ("USDINR", False),
})

MON_FRI = (0, 1, 2, 3, 4)
SUN_THU = (6, 0, 1, 2, 3)


def _idx(symbol: str, exchange: str, currency: str, label: str) -> MappingProxyType:
    return MappingProxyType({"symbol": symbol, "exchange": exchange, "currency": currency, "label": label})


def _fut(symbol: str, exchange: str, currency: str, label: str, multiplier: str = "",
         also: tuple[str, ...] = ()) -> MappingProxyType:
    """An index future, read through IBKR's continuous-future definition (the multiplier tells a full contract
    from its mini on the same exchange). IBKR names a future by its underlying (DAX, N225), not always by the
    exchange's own code; ``also`` lists other names asked, in order, when IBKR does not know ``symbol``."""
    return MappingProxyType({"symbol": symbol, "exchange": exchange, "currency": currency, "label": label,
                             "multiplier": multiplier, "also": also})


def _market(id_: str, name: str, exchange: str, city: str, region: str, lat: float, lon: float, tz: str,
            segments: tuple, etf: str, *, days: tuple = MON_FRI, calendar: str = "clock",
            index: MappingProxyType | None = None, future: MappingProxyType | None = None) -> MappingProxyType:
    return MappingProxyType({
        "id": id_, "name": name, "exchange": exchange, "city": city, "region": region, "lat": lat, "lon": lon,
        "tz": tz, "segments": segments, "days": days, "calendar": calendar, "index": index, "future": future,
        "etf": etf,
    })


# Regular sessions, local time; a lunch pause splits a day into two segments.
GLOBAL_MARKETS = (
    _market("us", "United States", "NYSE + Nasdaq", "New York", "americas", 40.71, -74.01, "America/New_York",
            (("09:30", "16:00"),), "SPY", calendar="nyse",
            index=_idx("SPX", "CBOE", "USD", "S&P 500"), future=_fut("ES", "CME", "USD", "S&P 500 futures")),
    _market("ca", "Canada", "TSX", "Toronto", "americas", 43.65, -79.38, "America/Toronto",
            (("09:30", "16:00"),), "EWC",
            index=_idx("TSX", "TSE", "CAD", "S&P/TSX Composite"),
            # IBKR's underlying for the Montreal Exchange's SXF is TSE60; "SXF" asked as a TSE60 underlying: "200: No
            # security definition" on the operator's desk (2026-10-20). 200 = the full contract, not the SXM mini.
            future=_fut("TSE60", "CDE", "CAD", "S&P/TSX 60 futures", "200", also=("SXF",))),
    _market("br", "Brazil", "B3", "São Paulo", "americas", -23.55, -46.63, "America/Sao_Paulo",
            (("10:00", "17:00"),), "EWZ"),
    _market("uk", "United Kingdom", "LSE", "London", "europe", 51.51, -0.09, "Europe/London",
            (("08:00", "16:30"),), "EWU",
            index=_idx("Z", "ICEEU", "GBP", "FTSE 100"), future=_fut("Z", "ICEEU", "GBP", "FTSE 100 futures")),
    _market("fr", "France", "Euronext Paris", "Paris", "europe", 48.86, 2.35, "Europe/Paris",
            (("09:00", "17:30"),), "EWQ",
            index=_idx("CAC40", "MONEP", "EUR", "CAC 40"),
            future=_fut("CAC40", "MONEP", "EUR", "CAC 40 futures", "10")),
    _market("de", "Germany", "Xetra", "Frankfurt", "europe", 50.11, 8.68, "Europe/Berlin",
            (("09:00", "17:30"),), "EWG",
            index=_idx("DAX", "EUREX", "EUR", "DAX"), future=_fut("DAX", "EUREX", "EUR", "DAX futures", "25")),
    _market("ch", "Switzerland", "SIX", "Zurich", "europe", 47.37, 8.54, "Europe/Zurich",
            (("09:00", "17:30"),), "EWL",
            index=_idx("SMI", "EUREX", "CHF", "SMI"), future=_fut("SMI", "EUREX", "CHF", "SMI futures", "10")),
    _market("sa", "Saudi Arabia", "Tadawul", "Riyadh", "middle_east_africa", 24.71, 46.68, "Asia/Riyadh",
            (("10:00", "15:00"),), "KSA", days=SUN_THU),
    _market("za", "South Africa", "JSE", "Johannesburg", "middle_east_africa", -26.20, 28.05,
            "Africa/Johannesburg", (("09:00", "17:00"),), "EZA"),
    _market("in", "India", "NSE", "Mumbai", "asia_pacific", 19.07, 72.88, "Asia/Kolkata",
            (("09:15", "15:30"),), "INDA", index=_idx("NIFTY50", "NSE", "INR", "Nifty 50")),
    _market("cn", "China", "SSE + SZSE", "Shanghai", "asia_pacific", 31.23, 121.47, "Asia/Shanghai",
            (("09:30", "11:30"), ("13:00", "15:00")), "ASHR",
            index=_idx("XINA50", "SGX", "USD", "FTSE China A50"),
            future=_fut("XINA50", "SGX", "USD", "FTSE China A50 futures")),
    _market("hk", "Hong Kong", "HKEX", "Hong Kong", "asia_pacific", 22.28, 114.16, "Asia/Hong_Kong",
            (("09:30", "12:00"), ("13:00", "16:00")), "EWH",
            index=_idx("HSI", "HKFE", "HKD", "Hang Seng"),
            future=_fut("HSI", "HKFE", "HKD", "Hang Seng futures", "50")),
    _market("tw", "Taiwan", "TWSE", "Taipei", "asia_pacific", 25.03, 121.56, "Asia/Taipei",
            (("09:00", "13:30"),), "EWT"),
    _market("kr", "South Korea", "KRX", "Seoul", "asia_pacific", 37.57, 126.98, "Asia/Seoul",
            (("09:00", "15:30"),), "EWY",
            index=_idx("K200", "KSE", "KRW", "KOSPI 200"),
            future=_fut("K200", "KSE", "KRW", "KOSPI 200 futures", "250000")),
    _market("jp", "Japan", "JPX", "Tokyo", "asia_pacific", 35.68, 139.77, "Asia/Tokyo",
            (("09:00", "11:30"), ("12:30", "15:30")), "EWJ",
            index=_idx("N225", "OSE.JPN", "JPY", "Nikkei 225"),
            future=_fut("N225", "OSE.JPN", "JPY", "Nikkei 225 futures", "1000")),
    _market("au", "Australia", "ASX", "Sydney", "asia_pacific", -33.87, 151.21, "Australia/Sydney",
            (("10:00", "16:00"),), "EWA",
            index=_idx("XJO", "ASX", "AUD", "S&P/ASX 200"), future=_fut("AP", "SNFE", "AUD", "SPI 200 futures")),
)

# -- each market's size: the one set of numbers on the page that is not IBKR's (ADR 060 amendment) ------------------
# "It's not reasonable not to see the size of each market. It doesn't have to be super accurate" (operator,
# 2026-10-20). An exchange's domestic market capitalisation -- its home companies' listed shares at their price --
# in US dollars, as its published source states it: monthly figures, not live, shown with their month and source.
# A newer month replaces a row here; a market without a published figure has none (never a guess).
GLOBAL_WFE = "World Federation of Exchanges"
GLOBAL_WFE_URL = "https://focus.world-exchanges.org/issue/march-2026/market-statistics"


def _size(as_of: str, source: str, url: str, *parts: tuple[str, float]) -> MappingProxyType:
    return MappingProxyType({"as_of": as_of, "source": source, "url": url,
                             "parts": tuple(MappingProxyType({"name": n, "usd": usd}) for n, usd in parts)})


GLOBAL_MARKET_SIZES = MappingProxyType({
    "us": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("NYSE", 29_477_188e6), ("Nasdaq", 38_537_621e6)),
    "ca": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("TMX Group", 4_704_097e6)),
    "br": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("B3", 902_687e6)),
    "uk": _size("2026-04", "Bloomberg (UK-listed stocks)",
                "https://www.bloomberg.com/news/articles/2026-04-16/ai-driven-demand-pushes-taiwan-s-market-cap-ahead-of-the-uk",
                ("London", 4.09e12)),
    "fr": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("Euronext (all its markets)", 7_589_718e6)),
    "de": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("Deutsche Börse", 2.73e12)),
    "ch": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("SIX", 2.48e12)),
    "sa": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("Saudi Exchange", 2_557_183e6)),
    "za": _size("2026-01", "JSE (R24.22 trillion)", "https://en.wikipedia.org/wiki/JSE_Limited", ("JSE", 1.48e12)),
    "in": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("NSE", 4.98e12)),
    "cn": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("Shanghai", 9_671_757e6), ("Shenzhen", 6.65e12)),
    "hk": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("HKEX", 6.50e12)),
    "tw": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("TWSE", 3.32e12)),
    "kr": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("Korea Exchange", 3_424_044e6)),
    "jp": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("Japan Exchange Group", 7_705_442e6)),
    "au": _size("2026-01", GLOBAL_WFE, GLOBAL_WFE_URL, ("ASX", 2_110_466e6)),
})

GLOBAL_US_ETF_SESSION = (("09:30", "16:00"),)    # a country ETF trades in the US regular session (NYSE calendar)
GLOBAL_US_TZ = "America/New_York"
