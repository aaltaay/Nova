"""schema_version helpers for dated cache JSON and named persist files.

Owner: this module (version map) + the writer named in each prefix comment.
Invalidation: unknown version is refuse-loud; missing version is legacy v0
(accepted and stamped on the next write). Session-dated files also key off
``date`` / ``session_key_et``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# One constant per dated prefix so a future bump does not migrate every table.
GAPPERS_SCHEMA_VERSION = 1
GAINERS_SCHEMA_VERSION = 1
LOSERS_SCHEMA_VERSION = 1
MOVERS_SCHEMA_VERSION = 1
AFTERHOURS_SCHEMA_VERSION = 1
LARGE_CAP_SCHEMA_VERSION = 1
HOD_MOMO_ALERTS_SCHEMA_VERSION = 1
HOD_MOMO_HIGHS_SCHEMA_VERSION = 1
NEWS_CATALYSTS_SCHEMA_VERSION = 1
HOD_MOMO_BLOCKLIST_SCHEMA_VERSION = 1
SESSION_FOCUS_SCHEMA_VERSION = 1
ALERTS_CHANNELS_SCHEMA_VERSION = 1

PREFIX_SCHEMA_VERSION: dict[str, int] = {
    "gappers": GAPPERS_SCHEMA_VERSION,
    "gainers": GAINERS_SCHEMA_VERSION,
    "losers": LOSERS_SCHEMA_VERSION,
    "movers": MOVERS_SCHEMA_VERSION,
    "afterhours": AFTERHOURS_SCHEMA_VERSION,
    "large_cap": LARGE_CAP_SCHEMA_VERSION,
    "hod-momo": HOD_MOMO_ALERTS_SCHEMA_VERSION,
    "hod-momo-highs": HOD_MOMO_HIGHS_SCHEMA_VERSION,
    "news-catalysts": NEWS_CATALYSTS_SCHEMA_VERSION,
}


def version_for_prefix(prefix: str) -> int:
    return PREFIX_SCHEMA_VERSION.get(prefix, 1)


def stamp_schema(payload: dict[str, Any], version: int) -> dict[str, Any]:
    return {**payload, "schema_version": version}


def accept_schema(
    data: dict[str, Any],
    expected: int,
    *,
    name: str,
    log: logging.Logger | None = None,
) -> dict[str, Any] | None:
    """Return *data* if usable, else None.

    Missing ``schema_version`` is a legacy file -- accept (migrate on write).
    Unknown / unreadable versions refuse loud so a future shape cannot load
    half-parsed rows.
    """
    log = log or logger
    raw = data.get("schema_version")
    if raw is None:
        return data
    try:
        version = int(raw)
    except (TypeError, ValueError):
        log.warning("%s: refusing persist file with unreadable schema_version=%r", name, raw)
        return None
    if version != expected:
        log.warning(
            "%s: refusing persist file with unknown schema_version=%s (expected %s)",
            name,
            version,
            expected,
        )
        return None
    return data
