"""The market's kept headlines (`architecture/schema/agent-desk.md`)."""
from __future__ import annotations

MARKET_NEWS_ENV = "NOVA_MARKET_NEWS"             # 0 turns the feed off
MARKET_NEWS_DB_FILENAME = "market_news.sqlite3"
MARKET_NEWS_SCHEMA_VERSION = 1
MARKET_NEWS_POLL_SEC = 60.0
MARKET_NEWS_SQLITE_TIMEOUT_SEC = 5.0
MARKET_NEWS_WINDOW_SEC = 86400.0                 # a search looks back this far
