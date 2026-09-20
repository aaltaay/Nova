"""Capture stream/timeframe aliases."""


def _normalize_timeframe(timeframe: str) -> tuple[str, str] | None:
    """``("bars_1m", "1m")`` for any accepted spelling, else ``None``."""
    tf = (timeframe or "").strip().lower().replace(" ", "")
    if tf in ("10s", "10sec", "10"):
        return "bars_10s", "10s"
    if tf in ("1m", "1min", "1minute"):
        return "bars_1m", "1m"
    if tf in ("5m", "5min", "5minute"):
        return "bars_5m", "5m"
    if tf in ("1d", "1day", "day", "daily"):
        return "bars_1d", "1d"
    return None
