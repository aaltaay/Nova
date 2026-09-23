"""Tunables for the listed-symbol directory behind the header ticker search.

Owner: ``symbol_directory.py`` (served by ``routes/symbols.py``).
"""
from __future__ import annotations

# Listings change a few times a day at most; one fetch serves the desk for hours.
SYMBOL_DIRECTORY_TTL_SEC = 6 * 3600.0
# After a failed fetch, wait this long before asking Alpaca again (the stale
# directory, if any, keeps being served meanwhile).
SYMBOL_DIRECTORY_RETRY_SEC = 120.0
SYMBOL_DIRECTORY_HTTP_TIMEOUT_SEC = 30.0
# Venues a desk symbol can be listed on. OTC is left out: IBKR market data for
# it is not what this desk trades, and it would triple the directory.
SYMBOL_DIRECTORY_EXCHANGES = ("NASDAQ", "NYSE", "AMEX", "ARCA", "BATS")
SYMBOL_DIRECTORY_SCHEMA_VERSION = 1
SYMBOL_DIRECTORY_SOURCE = "alpaca_assets"
SYMBOL_DIRECTORY_NO_KEYS_ERROR = "Alpaca keys are not configured (APCA_API_KEY_ID / APCA_API_SECRET_KEY)"
