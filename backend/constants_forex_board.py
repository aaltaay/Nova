"""The Forex page's tunables, its currencies and the size of the market (ADR 062).

Owner: backend/forex_board/. Mirrors: frontend/src/forex_board/constants.ts (periods). The market's size is the BIS
Triennial Central Bank Survey's (April 2025 daily averages, final results June 2026) -- published every three years,
not live, and shown as such. Every other number on the page is IBKR's: spot forex on IDEALPRO and CME currency futures.

maintainer: one-concern the Forex page's constants table: the BIS survey's figures and the 19 currencies' contracts
"""
from __future__ import annotations

from types import MappingProxyType

FOREX_ENV = "NOVA_FOREX_BOARD"                   # "0" turns the page's reads off
FOREX_WARM_ENV = "NOVA_FOREX_BOARD_WARM"         # "0": reads only while the page is open (no background cadence)
FOREX_SCHEMA_VERSION = 1
FOREX_PERIODS = ("1D", "7D", "30D")
FOREX_PERIOD_DAYS = MappingProxyType({"7D": 5, "30D": 21})       # completed FX days back
FOREX_ERR_BAD_PARAM = "FOREX_BAD_PARAM"
FOREX_PACE_KIND = "forex"                        # the pacing book's name for this page (capacity strip: History)
FOREX_TZ = "America/New_York"
FOREX_DAY_START_HOUR_ET = 17                     # the FX day runs 17:00 to 17:00 New York, Sunday to Friday
FOREX_SESSION_LOCAL = ("08:00", "17:00")         # a city's session: 08:00-17:00 on its own clock

# -- who is looking, and how often each read runs -------------------------------------------------------------------
FOREX_WANTED_SEC = 30.0                          # a board read keeps the reads going this long
FOREX_TICK_SEC = 1.0                             # the reader's sleep when nothing was due and the page is open
FOREX_IDLE_WAIT_SEC = 15.0                       # ... and when nobody looks
FOREX_RETRY_SEC = 120.0                          # a failed read is tried again after this
FOREX_SHED_RETRY_SEC = 30.0                      # the historical service or the line budget said "later"
FOREX_REFUSED_RETRY_SEC = 6 * 3600.0             # an instrument IBKR refused is not asked again before this
FOREX_QUOTES_TTL_SEC = 60.0                      # the spot quotes (a line held for a moment) while the page shows
FOREX_IDLE_QUOTES_TTL_SEC = 600.0                # ... while nobody looks
FOREX_FLOW_TTL_SEC = 600.0                       # each future's one-minute bars while the page shows
FOREX_IDLE_FLOW_TTL_SEC = 1800.0                 # ... while nobody looks (never in the desk's own hours, below)
FOREX_FINAL_READ_LAG_SEC = 120.0                 # an hour's (or a day's) last bar is in IBKR's history this long after
FOREX_STALE_MAX_SEC = 3 * 86400.0                # a read's last answer is shown at most this long after it (a weekend)
# Nobody looking: no read from the open to the close of the US regular session, the desk's own hours (ET minutes).
FOREX_QUIET_FROM_MIN_ET = 9 * 60 + 30
FOREX_QUIET_TO_MIN_ET = 16 * 60

# -- IBKR budget: Forex reads last, taking turns (ADR 062 decision 5) ------------------------------------------------
FOREX_HISTORY_HEADROOM = 30                      # no historical request while this few of the 10-minute 60 are left:
#   charts, the short check, the TraderTV exits and LULD (20) come first; the Market and Global pages stop at the
#   same 30, so the three take turns.
FOREX_YIELD_HEADROOM = 40                        # ... while the Market or Global page shows and this one does not
FOREX_HISTORY_GAP_SEC = 2.0                      # between two of this page's historical requests
FOREX_IBKR_TIMEOUT_SEC = 8.0                     # a contract qualify
FOREX_HISTORY_TIMEOUT_SEC = 60.0                 # one historical request, end to end through the bridge
FOREX_HOURLY_BAR = "1 hour"
FOREX_HOURLY_DURATION = "4 D"                    # the FX day shown and the close before it, across a weekend
FOREX_DAILY_DURATION = "3 M"                     # 21 FX days back, 20 for the normal day, and room
FOREX_DAILY_KEEP = 70                            # daily rows kept per instrument
FOREX_FLOW_BAR = "1 min"
FOREX_FLOW_DURATION = "3 D"                      # the FX day shown and the future's close before it, over a weekend
FOREX_QUOTE_FRESH_SEC = 2 * FOREX_IDLE_QUOTES_TTL_SEC
FOREX_NORMAL_DAYS = 20                           # a normal day's range and futures volume: the last 20 completed

# -- the read, the flags ---------------------------------------------------------------------------------------------
FOREX_READ_MIN_PRICED = 8                        # fewer priced currencies: no read
FOREX_READ_GROUP_PCT = MappingProxyType({"1D": 0.15, "7D": 0.4, "30D": 0.8})
FOREX_READ_DOLLAR_PCT = MappingProxyType({"1D": 0.2, "7D": 0.5, "30D": 1.0})
FOREX_SAFE_HAVENS = ("JPY", "CHF")
FOREX_RISKIER = ("AUD", "NZD", "CAD", "NOK", "SEK", "MXN", "ZAR", "BRL")
FOREX_PEGGED = ("HKD",)                          # moves with the dollar: never named "rose most" / "fell most"
FOREX_MIXED_PRESSURE_PCT = 5.0                   # futures pressure and strength disagree only past both of these
FOREX_MIXED_STRENGTH_PCT = 0.15

# -- kept across restarts (forex_board/keep.py) ----------------------------------------------------------------------
FOREX_KEEP_DIR = "forex-board"
FOREX_KEEP_FILE = "forex-store.json"
FOREX_KEEP_SAVE_SEC = 60.0
FOREX_KEEP_MAX_AGE_SEC = 3 * 86400.0

# -- the market's size: BIS Triennial Central Bank Survey 2025 (the page's only numbers not IBKR's) ------------------
# Final results (June 2026 annex), daily averages in April 2025, US dollars. "Net-net" turnover (Tables 1, 25.2) for
# the total, the instruments and each currency; "net-gross" for where the dealers' desks are (Tables 1, 19).
FOREX_BIS = MappingProxyType({
    "as_of": "2025-04",
    "source": "BIS Triennial Central Bank Survey 2025",
    "url": "https://www.bis.org/statistics/rpfx25.htm",
})
FOREX_BIS_TOTAL_USD = 9_510.240e9
FOREX_BIS_EXCHANGE_TRADED_USD = 201e9            # memo: exchange-traded FX futures and options, every exchange
FOREX_BIS_INSTRUMENTS = (("FX swaps", 4_015.293e9), ("Spot", 2_951.766e9), ("Outright forwards", 1_747.311e9),
                         ("Options", 631.717e9), ("Currency swaps", 164.072e9))
FOREX_BIS_DESKS = (("UK", 4_742.575e9), ("US", 2_334.700e9), ("Singapore", 1_485.282e9), ("Hong Kong", 883.067e9),
                   ("Japan", 440.231e9), ("Germany", 386.077e9), ("Switzerland", 370.472e9), ("France", 242.217e9),
                   ("China", 235.050e9), ("Other", 1_437.443e9))
# Table 19's 2025 column summed by region (net-gross): Asia-Pacific, Europe (the UK in it), the Americas (the US in it)
FOREX_BIS_REGIONS_USD = MappingProxyType({"asia_pacific": 3_526e9, "europe": 6_247e9, "americas": 2_648e9})


def _spot(pair: str, per_usd: bool) -> MappingProxyType:
    """An IDEALPRO pair: ``EURUSD`` is dollars per euro (``per_usd`` False), ``USDJPY`` yen per dollar."""
    return MappingProxyType({"pair": pair, "quote": f"{pair[:3]}/{pair[3:]}", "per_usd": per_usd})


def _fut(symbol: str, code: str, multiplier: str, label: str, *, inverted: bool = False,
         also: tuple[str, ...] = ()) -> MappingProxyType:
    """A CME currency future through IBKR's continuous future: ``symbol`` IBKR's (``also`` other names asked, in order,
    when IBKR does not know it), ``code`` CME's, the multiplier telling the full contract from its mini. Priced in
    dollars per unit of the currency -- or, ``inverted``, a contract worth ``multiplier`` dollars priced in the
    currency per dollar (USD/CNH)."""
    return MappingProxyType({"symbol": symbol, "code": code, "exchange": "CME", "currency": "CNH" if inverted else "USD",
                             "multiplier": multiplier, "label": label, "inverted": inverted, "also": also})


def _cur(code: str, name: str, word: str, city: str, lat: float, lon: float, tz: str, bis_usd: float, rank: int,
         pair: str, pair_usd: float, spot: MappingProxyType | None = None,
         future: MappingProxyType | None = None) -> MappingProxyType:
    return MappingProxyType({
        "code": code, "name": name, "word": word, "city": city, "lat": lat, "lon": lon, "tz": tz,
        "bis_usd": bis_usd, "rank": rank, "pair": pair, "pair_usd": pair_usd, "spot": spot, "future": future,
    })


# The survey's 19 most traded currencies, biggest first (Table 25.2), each with its biggest pair (Tables 3.9-3.12),
# its IDEALPRO pair and its CME future. The rupee, won and Taiwan dollar are not expected on IDEALPRO, the real's spot
# neither: each is asked, and IBKR's answer is shown.
FOREX_CURRENCIES = (
    _cur("USD", "US dollar", "the dollar", "New York", 40.71, -74.01, "America/New_York", 8_472e9, 1,
         "EUR/USD", 1_970.331e9),
    _cur("EUR", "Euro", "the euro", "Frankfurt", 50.11, 8.68, "Europe/Berlin", 2_714e9, 2, "EUR/USD", 1_970.331e9,
         _spot("EURUSD", False), _fut("EUR", "6E", "125000", "Euro FX futures")),
    _cur("JPY", "Japanese yen", "the yen", "Tokyo", 35.68, 139.77, "Asia/Tokyo", 1_608e9, 3, "USD/JPY", 1_370.104e9,
         _spot("USDJPY", True), _fut("JPY", "6J", "12500000", "Japanese yen futures")),
    _cur("GBP", "British pound", "the pound", "London", 51.51, -0.09, "Europe/London", 967e9, 4, "GBP/USD",
         715.489e9, _spot("GBPUSD", False), _fut("GBP", "6B", "62500", "British pound futures")),
    _cur("CNY", "Chinese yuan", "the yuan", "Shanghai", 31.23, 121.47, "Asia/Shanghai", 817e9, 5, "USD/CNY",
         781.309e9, _spot("USDCNH", True),
         _fut("CNH", "CNH", "100000", "USD/offshore yuan futures", inverted=True)),
    _cur("CHF", "Swiss franc", "the franc", "Zurich", 47.37, 8.54, "Europe/Zurich", 601e9, 6, "USD/CHF", 455.180e9,
         _spot("USDCHF", True), _fut("CHF", "6S", "125000", "Swiss franc futures")),
    _cur("AUD", "Australian dollar", "the Australian dollar", "Sydney", -33.87, 151.21, "Australia/Sydney", 582e9, 7,
         "AUD/USD", 467.113e9, _spot("AUDUSD", False), _fut("AUD", "6A", "100000", "Australian dollar futures")),
    _cur("CAD", "Canadian dollar", "the Canadian dollar", "Toronto", 43.65, -79.38, "America/Toronto", 547e9, 8,
         "USD/CAD", 491.602e9, _spot("USDCAD", True), _fut("CAD", "6C", "100000", "Canadian dollar futures")),
    _cur("HKD", "Hong Kong dollar", "the Hong Kong dollar", "Hong Kong", 22.28, 114.16, "Asia/Hong_Kong", 367e9, 9,
         "USD/HKD", 346.691e9, _spot("USDHKD", True)),
    _cur("SGD", "Singapore dollar", "the Singapore dollar", "Singapore", 1.29, 103.85, "Asia/Singapore", 232e9, 10,
         "USD/SGD", 214.691e9, _spot("USDSGD", True)),
    _cur("INR", "Indian rupee", "the rupee", "Mumbai", 19.07, 72.88, "Asia/Kolkata", 185e9, 11, "USD/INR",
         181.313e9, _spot("USDINR", True)),
    _cur("KRW", "Korean won", "the won", "Seoul", 37.57, 126.98, "Asia/Seoul", 171e9, 12, "USD/KRW", 165.352e9,
         _spot("USDKRW", True)),
    _cur("SEK", "Swedish krona", "the krona", "Stockholm", 59.33, 18.07, "Europe/Stockholm", 158e9, 13, "USD/SEK",
         104.806e9, _spot("USDSEK", True)),
    _cur("NZD", "New Zealand dollar", "the New Zealand dollar", "Wellington", -41.29, 174.78, "Pacific/Auckland",
         147e9, 14, "NZD/USD", 118.687e9, _spot("NZDUSD", False),
         _fut("NZD", "6N", "100000", "New Zealand dollar futures")),
    _cur("MXN", "Mexican peso", "the peso", "Mexico City", 19.43, -99.13, "America/Mexico_City", 147e9, 15,
         "USD/MXN", 133.919e9, _spot("USDMXN", True),
         _fut("MXP", "6M", "500000", "Mexican peso futures", also=("MXN",))),
    _cur("NOK", "Norwegian krone", "the krone", "Oslo", 59.91, 10.75, "Europe/Oslo", 127e9, 16, "USD/NOK", 85.341e9,
         _spot("USDNOK", True)),
    _cur("TWD", "Taiwan dollar", "the Taiwan dollar", "Taipei", 25.03, 121.56, "Asia/Taipei", 116e9, 17, "USD/TWD",
         113.620e9, _spot("USDTWD", True)),
    _cur("BRL", "Brazilian real", "the real", "São Paulo", -23.55, -46.63, "America/Sao_Paulo", 90e9, 18, "USD/BRL",
         85.893e9, _spot("USDBRL", True), _fut("BRE", "6L", "100000", "Brazilian real futures", also=("BRL",))),
    _cur("ZAR", "South African rand", "the rand", "Johannesburg", -26.20, 28.05, "Africa/Johannesburg", 82e9, 19,
         "USD/ZAR", 74.940e9, _spot("USDZAR", True), _fut("ZAR", "6Z", "500000", "South African rand futures")),
)

# The sessions: Asia from the FX day's start (Sydney's 08:00) until London's 08:00, London until New York's 08:00,
# New York to the FX day's end -- each hour belongs to the newest region open. The tracks under Follow the sun are
# the cities' own hours: Sydney's 08:00 to Tokyo's 17:00, London's and New York's 08:00-17:00.
FOREX_SESSIONS = (
    MappingProxyType({"id": "asia", "name": "Asia", "desks": "asia_pacific", "desks_label": "desks in Asia",
                      "track_from": "Australia/Sydney", "track_to": "Asia/Tokyo"}),
    MappingProxyType({"id": "london", "name": "London", "desks": "UK", "desks_label": "UK desks",
                      "track_from": "Europe/London", "track_to": "Europe/London"}),
    MappingProxyType({"id": "new_york", "name": "New York", "desks": "US", "desks_label": "US desks",
                      "track_from": "America/New_York", "track_to": "America/New_York"}),
)
