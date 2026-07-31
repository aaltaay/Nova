"""Parse IB Warning 399 held-until timestamps from Trade.log entries."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

_HELD_UNTIL_RE = re.compile(
    r"until\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(US/Eastern|America/New_York)",
    re.IGNORECASE,
)


def held_until_iso_from_trade(trade) -> str | None:
    """Return ISO-8601 UTC when IB says the order waits for RTH, else None."""
    log = getattr(trade, "log", None) or []
    for entry in reversed(list(log)):
        msg = str(getattr(entry, "message", "") or "")
        m = _HELD_UNTIL_RE.search(msg)
        if not m:
            continue
        local = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        tz_name = "America/New_York"
        aware = local.replace(tzinfo=ZoneInfo(tz_name))
        return aware.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def held_until_iso_from_message(message: str) -> str | None:
    """Test helper / direct parse of a Warning 399 message body."""
    class _Fake:
        log = [type("E", (), {"message": message})()]

    return held_until_iso_from_trade(_Fake())
