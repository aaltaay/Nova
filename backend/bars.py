"""
Fetch OHLCV bars from Alpaca for a single symbol.
Used by the /api/ticker/{symbol}/bars endpoint to power the frontend chart.
"""
import logging
from datetime import date, timedelta

import requests
from fastapi import HTTPException

from alpaca import ALPACA_DATA_URL as _DATA_URL, _alpaca_headers, _get_feed
from constants import (
    CHART_DEFAULT_BARS,
    CHART_DEFAULT_TIMEFRAME,
    CHART_LOOKBACK_DAYS,
    CHART_MAX_BARS,
    CHART_TIMEFRAMES,
)

logger = logging.getLogger(__name__)


def fetch_bars(
    symbol: str,
    timeframe: str = CHART_DEFAULT_TIMEFRAME,
    limit: int = CHART_DEFAULT_BARS,
) -> dict:
    """Return OHLCV bars for `symbol` from Alpaca.

    Response shape:
        {
            "symbol": "AAPL",
            "timeframe": "5Min",
            "bars": [{"t": "2024-01-02T09:30:00Z", "o": 185.0, "h": 186.2,
                      "l": 184.8, "c": 185.9, "v": 123456}, ...]
        }

    Raises HTTP 400 for unknown timeframes, HTTP 503 if Alpaca keys are absent.
    """
    if timeframe not in CHART_TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe '{timeframe}'. Valid values: {list(CHART_TIMEFRAMES)}",
        )

    headers = _alpaca_headers()
    if not headers:
        raise HTTPException(status_code=503, detail="Alpaca API keys not configured")

    limit = max(1, min(limit, CHART_MAX_BARS))
    lookback = CHART_LOOKBACK_DAYS.get(timeframe, 365)
    start_date = (date.today() - timedelta(days=lookback)).isoformat()

    try:
        resp = requests.get(
            f"{_DATA_URL}/v2/stocks/{symbol}/bars",
            headers=headers,
            params={
                "timeframe": timeframe,
                "start": start_date,
                "limit": limit,
                "feed": _get_feed(),
                # Fetch newest bars first so the limit doesn't truncate today's
                # premarket / after-hours data.  The result is reversed below so
                # the frontend (lightweight-charts) receives ascending order.
                "sort": "desc",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.warning("bars fetch network error for %s: %s", symbol, exc)
        raise HTTPException(status_code=502, detail="Network error fetching bars") from exc

    if resp.status_code == 422:
        raise HTTPException(status_code=400, detail=f"Alpaca rejected request: {resp.text[:200]}")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")
    if resp.status_code != 200:
        logger.warning("bars API returned %s for %s: %s", resp.status_code, symbol, resp.text[:200])
        raise HTTPException(status_code=502, detail=f"Alpaca returned {resp.status_code}")

    raw_bars: list[dict] = resp.json().get("bars") or []

    # Reverse to chronological (ascending) order for the frontend chart.
    bars = [
        {
            "t": b["t"],
            "o": b.get("o"),
            "h": b.get("h"),
            "l": b.get("l"),
            "c": b.get("c"),
            "v": b.get("v"),
        }
        for b in reversed(raw_bars)
    ]

    return {"symbol": symbol, "timeframe": timeframe, "bars": bars}
