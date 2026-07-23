"""
Alpaca client helpers and provider configuration.

Owns: ``_env``, ``_alpaca_headers``, active feed/discovery-provider state.

Extracted from ``main.py`` to be a stable, import-safe leaf module with no
circular dependencies — importable by any module without triggering a full
``main.py`` load.

Callers that previously accessed these via ``import main as _main`` can now
import directly from this module, eliminating the lazy-import boilerplate.
"""
from __future__ import annotations

import logging
import os

from constants import (
    DATA_FEED_DEFAULT,
    DATA_FEED_OPTIONS,
    DISCOVERY_PROVIDER_DEFAULT,
    DISCOVERY_PROVIDER_OPTIONS,
)

logger = logging.getLogger(__name__)

ALPACA_DATA_URL = "https://data.alpaca.markets"


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name, default)
    if v is None:
        return None
    return v.strip().strip("'\"")


def _alpaca_headers() -> dict[str, str] | None:
    api_key = _env("APCA_API_KEY_ID")
    api_secret = _env("APCA_API_SECRET_KEY")
    if not api_key or not api_secret:
        return None
    return {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}


# ── Active data feed tracking ─────────────────────────────────────────────────
# Tracks which feed is actually in use (may differ from configured if fallback fires).
_active_feed: str = ""   # set on first _get_feed() call
_feed_fell_back: bool = False  # True if SIP→IEX fallback was triggered this session


def _get_feed() -> str:
    """Return the active Alpaca data feed (iex or sip).

    Priority: _active_feed (runtime) > env ALPACA_DATA_FEED > DATA_FEED_DEFAULT.
    """
    global _active_feed
    if _active_feed:
        return _active_feed
    raw = (_env("ALPACA_DATA_FEED") or DATA_FEED_DEFAULT).lower()
    if raw not in DATA_FEED_OPTIONS:
        raw = DATA_FEED_DEFAULT
    _active_feed = raw
    return _active_feed


def _set_feed(feed: str) -> None:
    """Change the active data feed at runtime (e.g. from Settings or auto-fallback)."""
    global _active_feed, _feed_fell_back
    feed = feed.lower()
    if feed not in DATA_FEED_OPTIONS:
        feed = DATA_FEED_DEFAULT
    _active_feed = feed
    _feed_fell_back = False  # reset fallback flag when user explicitly changes
    logger.info("Data feed set to '%s'", _active_feed)


def _try_fallback_to_iex(context: str) -> bool:
    """If currently on SIP and a subscription error occurs, fall back to IEX.

    Returns True if the fallback was applied (caller should retry), False otherwise.
    """
    global _active_feed, _feed_fell_back
    if _active_feed == "sip" and not _feed_fell_back:
        logger.warning(
            "SIP feed rejected (%s) — falling back to IEX. "
            "Change feed in Settings or set ALPACA_DATA_FEED=sip if your plan supports it.",
            context,
        )
        _active_feed = "iex"
        _feed_fell_back = True
        return True
    return False


# ── Discovery provider (IBKR-only product lock) ───────────────────────────────
# Product surface is IBKR-only. Stale env/Settings values of "alpaca" coerce to
# ibkr. Alpaca scanner adapters remain importable for tests/emergency only.
_active_discovery_provider: str = ""


def _normalize_discovery_provider(provider: str | None) -> str:
    raw = (provider or DISCOVERY_PROVIDER_DEFAULT).strip().lower()
    if raw not in DISCOVERY_PROVIDER_OPTIONS:
        if raw and raw != DISCOVERY_PROVIDER_DEFAULT:
            logger.warning(
                "Discovery provider '%s' is not allowed — coercing to '%s'",
                raw,
                DISCOVERY_PROVIDER_DEFAULT,
            )
        return DISCOVERY_PROVIDER_DEFAULT
    return raw


def _get_discovery_provider() -> str:
    global _active_discovery_provider
    if _active_discovery_provider:
        return _active_discovery_provider
    raw = _normalize_discovery_provider(_env("NOVA_DISCOVERY_PROVIDER"))
    _active_discovery_provider = raw
    return _active_discovery_provider


def _set_discovery_provider(provider: str) -> None:
    global _active_discovery_provider
    _active_discovery_provider = _normalize_discovery_provider(provider)
    logger.info("Discovery provider set to '%s'", _active_discovery_provider)
