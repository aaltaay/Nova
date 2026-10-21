"""The gate: the forecaster's loopback address and token from ``.env`` (ADR 065).

Read on every call, so a test (or an operator editing ``.env`` before a restart) is never served a stale value.
Unset is the default: Ahead answers ``not_set_up`` and no request leaves Nova. The token is a secret: it is never
logged, and ``client`` sends it only to the address this module has checked names this PC.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urlsplit

from constants_ahead import (
    AHEAD_LOOPBACK_HOSTS,
    AHEAD_TOKEN_ENV,
    AHEAD_URL_ENV,
    AHEAD_WORDS_TOKEN_UNSET,
    AHEAD_WORDS_URL_BAD,
    AHEAD_WORDS_URL_UNSET,
)

logger = logging.getLogger(__name__)
_warned: set[str] = set()


def _raw_url() -> str:
    return (os.environ.get(AHEAD_URL_ENV) or "").strip()


def _loopback(raw: str) -> bool:
    try:
        parts = urlsplit(raw)
        host = parts.hostname
        _ = parts.port  # a bad port raises here, and the address is refused
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc) and host in AHEAD_LOOPBACK_HOSTS


def base_url() -> str | None:
    """The forecaster's base URL without a trailing slash; None when unset or not on this PC (warned once)."""
    raw = _raw_url()
    if not raw:
        return None
    if not _loopback(raw):
        if raw not in _warned:
            _warned.add(raw)
            logger.warning("%s does not name this PC (127.0.0.1); Ahead stays off", AHEAD_URL_ENV)
        return None
    return raw.rstrip("/")


def token() -> str | None:
    """The shared token, or None when unset. Never logged."""
    return (os.environ.get(AHEAD_TOKEN_ENV) or "").strip() or None


def setup_problem() -> str | None:
    """Plain words for what is missing, or None when Ahead is set up."""
    if not _raw_url():
        return AHEAD_WORDS_URL_UNSET
    if base_url() is None:
        return AHEAD_WORDS_URL_BAD
    if token() is None:
        return AHEAD_WORDS_TOKEN_UNSET
    return None


def configured() -> bool:
    return setup_problem() is None
