"""The Congress page's tunables, sources and words (ADR 066; shapes in architecture/schema/congress.md)."""
from __future__ import annotations

CONGRESS_SCHEMA_VERSION = 1
CONGRESS_ENV = "NOVA_CONGRESS"                       # "0" runs nothing and the page says it is off

# --- the agreement (5 U.S.C. § 13107(c)), in the words the Senate's eFD page shows -------------------------------
CONGRESS_CONSENT_CITE = "Ethics in Government Act of 1978, 5 U.S.C. § 13107(c) (formerly 5 U.S.C. app. § 105(c))"
CONGRESS_CONSENT_TEXT = (
    "It shall be unlawful for any person to obtain or use a report: for any unlawful purpose; for any commercial "
    "purpose, other than by news and communications media for dissemination to the general public; for determining "
    "or establishing the credit rating of any individual; or for use, directly or indirectly, in the solicitation of "
    "money for any political, charitable, or other purpose. The Attorney General may bring a civil action against any "
    "person who obtains or uses a report for any purpose prohibited in paragraph (1) of this subsection. The court in "
    "which such action is brought may assess against such person a penalty in any amount not to exceed $10,000. Such "
    "remedy shall be in addition to any other remedy available under statutory or common law."
)

# --- where things are kept (under paths.cache_dir()) ---------------------------------------------------------------
CONGRESS_DIR = "congress"
CONGRESS_STORE_FILE = "filings.sqlite3"
CONGRESS_STORE_VERSION = 1                           # PRAGMA user_version of filings.sqlite3
CONGRESS_CONSENT_FILE = "consent.json"
CONGRESS_ROSTER_FILE = "roster.json"
CONGRESS_PHOTOS_DIR = "photos"
CONGRESS_PHOTO_MISSES_FILE = "misses.json"
CONGRESS_PARSER_VERSION = {"house": 1, "senate": 1}  # a report read by an older parser is read again

# --- sources -------------------------------------------------------------------------------------------------------
CONGRESS_USER_AGENT = "Nova-desk/1.0 (congress page; +https://github.com/aaltaay/Nova)"
CONGRESS_HOUSE_INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
CONGRESS_HOUSE_PDF_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc}.pdf"
CONGRESS_HOUSE_SITE = "https://disclosures-clerk.house.gov/FinancialDisclosure"
CONGRESS_HOUSE_PAPER_PREFIXES = ("8", "9")           # a DocID of a scanned paper report: listed, never downloaded
CONGRESS_SENATE_BASE = "https://efdsearch.senate.gov"
CONGRESS_SENATE_HOME = "/search/home/"
CONGRESS_SENATE_SEARCH = "/search/report/data/"
CONGRESS_SENATE_PTR_TYPE = "[11]"                    # eFD's report type id of a Periodic Transaction Report
CONGRESS_SENATE_PAGE = 100
CONGRESS_SENATE_OVERLAP_DAYS = 14                    # a later read starts this long before the last one
CONGRESS_ROSTER_BASE = "https://unitedstates.github.io/congress-legislators/"
CONGRESS_ROSTER_CURRENT = "legislators-current.json"
CONGRESS_ROSTER_HISTORICAL = "legislators-historical.json"
CONGRESS_COMMITTEES = "committees-current.json"
CONGRESS_COMMITTEE_MEMBERS = "committee-membership-current.json"
CONGRESS_PHOTO_URLS = (
    "https://unitedstates.github.io/images/congress/225x275/{bioguide}.jpg",
    "https://bioguide.congress.gov/bioguide/photo/{letter}/{bioguide}.jpg",
)
CONGRESS_TERRITORIES = ("AS", "DC", "GU", "MP", "PR", "VI")   # non-voting delegates: listed apart, not seated
CONGRESS_HOUSE_SEATS = 435
CONGRESS_SENATE_SEATS = 100

# --- pace ----------------------------------------------------------------------------------------------------------
CONGRESS_REQUEST_GAP_SEC = 1.0                       # between any two requests the reader sends
CONGRESS_HTTP_TIMEOUT_SEC = 60.0
CONGRESS_MAX_PDF_BYTES = 8 * 1024 * 1024
CONGRESS_MAX_PHOTO_BYTES = 2 * 1024 * 1024
CONGRESS_POLL_SEC = 3600.0                           # the House index and the Senate search
CONGRESS_RETRY_SEC = 900.0                           # after a failed read
CONGRESS_IDLE_WAIT_SEC = 60.0                        # the reader's sleep with nothing due
CONGRESS_SESSION_GAP_SEC = 3.0                       # 09:30-16:00 ET on a weekday: also this long between reports
CONGRESS_ROSTER_MAX_AGE_SEC = 24 * 3600.0
CONGRESS_HISTORICAL_MAX_AGE_SEC = 7 * 24 * 3600.0
CONGRESS_PHOTO_RETRY_SEC = 7 * 24 * 3600.0
CONGRESS_YEARS_KEPT = 2                              # the current calendar year and the one before

# --- what the page shows -------------------------------------------------------------------------------------------
CONGRESS_PERIODS = ("ytd", "90d", "30d")
CONGRESS_PERIOD_DAYS = {"90d": 90, "30d": 30}
CONGRESS_FILTERS = ("all", "house", "senate", "buys", "sells", "options", "late")
CONGRESS_LATE_DAYS = 45                              # the STOCK Act's outer limit
CONGRESS_JUST_REPORTED = 12
CONGRESS_MOST_TRADED = 8
CONGRESS_MOST_ACTIVE = 5
CONGRESS_ACTIVE_DAYS = 120
CONGRESS_ACTIVE_WEEKS = 26
CONGRESS_MEMBER_WEEKS = 52
CONGRESS_LAG_BUCKET_DAYS = 5
CONGRESS_LAG_BUCKETS = 25                            # the last one is 120 days and more
CONGRESS_MAX_MEMBERS_PARAM = 600
CONGRESS_TICKER_MAX_TRADES = 500
CONGRESS_GIFT_WORDS = r"contribution|donor[- ]advised|gift|donat"

# --- errors --------------------------------------------------------------------------------------------------------
CONGRESS_ERR_BAD_PARAM = "CONGRESS_BAD_PARAM"
CONGRESS_ERR_UNKNOWN_MEMBER = "CONGRESS_UNKNOWN_MEMBER"
CONGRESS_ERR_NO_PHOTO = "CONGRESS_NO_PHOTO"
