"""The gate: the feed's base URL from ``NOVA_FOLLOW_FEED_URL``, or None (the default: the feature is off)."""
from __future__ import annotations

import logging
import os
from urllib.parse import urlsplit

from followed_traders.constants_followed import FOLLOWED_FEED_URL_ENV

logger = logging.getLogger(__name__)
_warned: set[str] = set()


def feed_url() -> str | None:
    """The feed's base URL without a trailing slash; None when unset or not an http(s) URL (logged once)."""
    raw = (os.environ.get(FOLLOWED_FEED_URL_ENV) or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        if raw not in _warned:
            _warned.add(raw)
            logger.warning("%s is not an http(s) URL; the followed traders page stays off", FOLLOWED_FEED_URL_ENV)
        return None
    return raw.rstrip("/")


def enabled() -> bool:
    return feed_url() is not None
