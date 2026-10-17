"""Volume profile on the 5-minute chart (ADR 058, ``architecture/schema/volume-profile.md``).

Mirrors ``frontend/src/volume_profile/volumeProfileConstants.ts`` (``VP_ROWS``, ``VP_MIN_ROW``,
``VP_VALUE_AREA_PCT``): the desk draws what the backend builds.
"""
from __future__ import annotations

VP_SCHEMA_VERSION = 1
VP_SOURCE_BARS_1M = "bars_1m"

# The histogram: rows over the profile's price range, never thinner than a cent; the value area's share.
VP_ROWS = 400
VP_MIN_ROW = 0.01
VP_VALUE_AREA_PCT = 70.0

# ET minutes of day: today's default anchor and window, and yesterday's regular session.
VP_EXTENDED_OPEN_MIN = 4 * 60
VP_RTH_OPEN_MIN = 9 * 60 + 30
VP_RTH_CLOSE_MIN = 16 * 60
VP_EXTENDED_CLOSE_MIN = 20 * 60

# Most 1-minute bars one profile reads (the whole 04:00-20:00 day).
VP_MAX_MINUTES = 960
# Yesterday's session counts as held by the chart store from this many of its 390 minutes; fewer asks IBKR.
VP_SESSION_MIN_BARS = 370

# The one IBKR request (``volume_profile/ibkr_minutes.py``): the regular session's 1-minute TRADES bars.
VP_RTH_DURATION = "23400 S"
VP_IB_TIMEOUT_SEC = 20.0
# Profiles of past sessions kept in memory, per symbol and day.
VP_CACHE_MAX = 64
