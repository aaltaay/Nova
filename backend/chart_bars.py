"""Provider-aware chart bars facade.

When discovery is IBKR, chart bars come from IBKR only — never silently from
Alpaca. Alpaca is used only when discovery_provider is explicitly alpaca.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from bars import fetch_bars as fetch_alpaca_bars
from constants import (
    CHART_DEFAULT_BARS,
    CHART_DEFAULT_TIMEFRAME,
    IBKR_HISTORICAL_TIMEOUT_SEC,
)
from ibkr import client as _ibkr_client
from ibkr.errors import bars_failure_detail, describe_exc, is_transient_historical_failure

logger = logging.getLogger(__name__)


def fetch_chart_bars(
    symbol: str,
    timeframe: str = CHART_DEFAULT_TIMEFRAME,
    limit: int = CHART_DEFAULT_BARS,
    *,
    discovery_provider: str,
    interactive: bool = False,
) -> dict:
    """Return ``{symbol, timeframe, bars, source}`` from the active discovery feed.

    Single-feed rule: when ``discovery_provider == \"ibkr\"``, IBKR must succeed
    (Gateway connected + historical data). There is no silent Alpaca fallback —
    callers get HTTP 503 so the UI cannot mix IBKR quotes with Alpaca candles.

    ``interactive=True`` for the open ticker chart (priority over setups_stream).
    """
    symbol = symbol.upper()
    if discovery_provider == "ibkr":
        if not _ibkr_client.is_connected():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Chart bars require IB Gateway (discovery=ibkr). "
                    "Connect Gateway — Nova will not fall back to Alpaca."
                ),
            )
        # Allow a little headroom beyond the IB request timeout for qualify + lock wait.
        run_timeout = IBKR_HISTORICAL_TIMEOUT_SEC + (5.0 if interactive else 2.0)
        try:
            from ibkr import bars as _ibkr_bars
            result = _ibkr_client.run_coro(
                _ibkr_bars.fetch_bars_async(
                    symbol, timeframe, limit, interactive=interactive,
                ),
                timeout=run_timeout,
            )
        except HTTPException:
            raise
        except Exception as exc:
            detail = bars_failure_detail(symbol, exc)
            if is_transient_historical_failure(exc):
                # Expected under Gateway load / overnight cancels — warning, not Sentry ERROR spam.
                logger.warning("IBKR bars transient failure for %s: %s", symbol, describe_exc(exc))
            else:
                logger.error("IBKR bars failed for %s: %s", symbol, describe_exc(exc), exc_info=True)
            raise HTTPException(status_code=503, detail=detail) from exc
        if not isinstance(result, dict) or "bars" not in result:
            raise HTTPException(
                status_code=503,
                detail=f"IBKR chart bars returned unexpected shape for {symbol}",
            )
        result.setdefault("source", "ibkr")
        return result

    payload = fetch_alpaca_bars(symbol, timeframe, limit)
    payload.setdefault("source", "alpaca")
    return payload
