"""
Eastern-time market session helpers.

Extracted from main.py (backend-modularity.mdc target layout). Behavior is
unchanged — same premarket/regular/after-hours boundaries used by the scan
loop to decide which discovery function runs.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def now_et() -> datetime:
    return datetime.now(ET)


def in_premarket() -> bool:
    now = now_et()
    start = now.replace(hour=4, minute=0, second=0, microsecond=0)
    open_ = now.replace(hour=9, minute=30, second=0, microsecond=0)
    return start <= now < open_


def in_market_hours() -> bool:
    now = now_et()
    open_ = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_ <= now < close


def in_after_hours() -> bool:
    now = now_et()
    start = now.replace(hour=16, minute=0, second=0, microsecond=0)
    end = now.replace(hour=20, minute=0, second=0, microsecond=0)
    return start <= now < end
