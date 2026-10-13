"""Constants for the earnings and split marks on the daily charts (``chart_events``)."""
from __future__ import annotations

CHART_EVENTS_ENV = "NOVA_CHART_EVENTS"   # "0" turns the reads off (the route then says so)

# SEC EDGAR: the registrant's financial facts (XBRL), beside the submissions file the dilution read uses.
CHART_EVENTS_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
# SEC fair access allows 10 requests a second for the whole desk: the catalyst feed paces at up to 6.7 a
# second, the dilution read at one, and this read at one, so the three stay under 9.
CHART_EVENTS_SEC_MIN_GAP_SEC = 1.0

# A read is reused for its session day (until the next 04:00 ET), never longer than this.
CHART_EVENTS_TTL_SEC = 24 * 3600.0
CHART_EVENTS_TICKERS_TTL_SEC = 24 * 3600.0     # SEC's ticker -> CIK list, kept in memory this long
CHART_EVENTS_RETRY_SEC = (30.0, 120.0, 600.0)  # after a failed read: the 1st, 2nd, then every later wait
CHART_EVENTS_PENDING_MAX = 12                  # symbols waiting for a read; the oldest ask drops first
CHART_EVENTS_KEEP_SYMBOLS = 300                # reads kept in memory; the oldest drops first
CHART_EVENTS_YAHOO_TIMEOUT_SEC = 15.0          # yfinance has no timeout of its own
CHART_EVENTS_HISTORY_DAYS = 3660               # events older than about ten years are left out

# The filings an earnings mark stands on. A periodic report is one of these forms (an amendment is not
# a new report); a 6-K counts only when SEC's financial facts carry its accession (an interim report),
# since most 6-Ks are not results. A release is an 8-K whose items include 2.02, "Results of
# Operations and Financial Condition".
CHART_EVENTS_PERIODIC_FORMS = ("10-Q", "10-K", "20-F", "40-F", "10-QT", "10-KT")
CHART_EVENTS_ANNUAL_FORMS = ("10-K", "20-F", "40-F", "10-KT")
CHART_EVENTS_INTERIM_FORMS = ("6-K",)
CHART_EVENTS_RELEASE_FORM = "8-K"
CHART_EVENTS_RELEASE_ITEM = "2.02"
# A release came out on the day it gives (its own words, an 8-K's date of event) when that is this many days
# or fewer before its filing: an Item 2.02 8-K is due within four business days of the announcement.
CHART_EVENTS_RELEASE_STATED_DAYS = 6
# A release filed this many days after its report still brought it out (a 10-Q filed the day before the
# press release); the mark then sits on the report's day, the first public one.
CHART_EVENTS_RELEASE_AFTER_REPORT_DAYS = 5
# 6-Ks and Item 2.02 8-Ks are read this far back (``release_text.py``): one SEC request each, two more for
# one whose cover only says a press release is attached (its exhibit), kept by accession.
CHART_EVENTS_6K_SCAN_DAYS = 760              # the daily chart's 500 bars, about two years
CHART_EVENTS_6K_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
CHART_EVENTS_6K_CACHE_MAX = 20000             # readings kept in memory; a filing never changes
CHART_EVENTS_FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
CHART_EVENTS_EXHIBIT_RE = r"ex-?99"            # an exhibit 99 file in the filing's index (99.1 first)
CHART_EVENTS_6K_KEEP_EVERY = 10               # 6-Ks read between two answers kept while a scan runs
# A fact over fewer days than this is not a reporting period (a month, a stub).
CHART_EVENTS_MIN_PERIOD_DAYS = 80

# The facts read for each report, first match wins: (taxonomy, concept). Total revenue (``Revenues``)
# before revenue from contracts with customers, which leaves out lease, interest and other revenue.
CHART_EVENTS_REVENUE_CONCEPTS = (
    ("us-gaap", "Revenues"),
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
    ("us-gaap", "SalesRevenueNet"),
    ("us-gaap", "RevenuesNetOfInterestExpense"),
    ("ifrs-full", "Revenue"),
    ("ifrs-full", "RevenueFromContractsWithCustomers"),
)
CHART_EVENTS_NET_INCOME_CONCEPTS = (
    ("us-gaap", "NetIncomeLoss"),
    ("us-gaap", "ProfitLoss"),
    ("ifrs-full", "ProfitLossAttributableToOwnersOfParent"),
    ("ifrs-full", "ProfitLoss"),
)
CHART_EVENTS_EPS_CONCEPTS = (
    ("us-gaap", "EarningsPerShareBasic"),
    ("us-gaap", "EarningsPerShareBasicAndDiluted"),
    ("ifrs-full", "BasicEarningsLossPerShare"),
)
CHART_EVENTS_MONEY_UNIT = "USD"
CHART_EVENTS_EPS_UNIT = "USD/shares"

CHART_EVENTS_SOURCE_SEC = "sec"
CHART_EVENTS_SOURCE_YAHOO = "yahoo"
CHART_EVENTS_SOURCE_MASSIVE = "massive"
CHART_EVENTS_SOURCE_SEC_CONFIRMED = "sec_confirmed"

# Splits from the operator's Massive reference archive (``<NOVA_MARKET_DATA_DIR>/store/reference/splits.json``,
# 2016 on, announced splits too) and the splits SEC filings proved that it misses (``splits_confirmed.json``
# beside the leaderboard store, #772), beside Yahoo's history: on 150 tickers with Massive splits from 2024
# (2026-10-12), Yahoo listed 114 of 159 with the same day and ratio, put none on another day, and missed 43
# (OTC names, funds and stock dividends mostly, but also LAZR 1-for-15 and SING 1-for-100).
CHART_EVENTS_MASSIVE_SPLITS_FILE = ("store", "reference", "splits.json")
CHART_EVENTS_CONFIRMED_SPLITS_FILE = "splits_confirmed.json"
CHART_EVENTS_CONFIRMED_SPLITS_SCHEMA_VERSION = 1
# Two sources' splits within this many days with one ratio are one split.
CHART_EVENTS_SPLIT_MATCH_DAYS = 3
CHART_EVENTS_SPLIT_RATIO_TOLERANCE = 0.01
