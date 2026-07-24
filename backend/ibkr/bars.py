"""IBKR historical OHLCV bars for the ticker chart.

Returns the same shape as ``bars.fetch_bars`` (Alpaca) so the frontend chart
needs no provider-specific code. Used when ``discovery_provider=ibkr`` so
candles match IBKR live quotes instead of sparse Alpaca IEX bars.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from fastapi import HTTPException

from constants import (
    CHART_DEFAULT_BARS,
    CHART_DEFAULT_TIMEFRAME,
    CHART_MAX_BARS,
    CHART_TIMEFRAMES,
    IBKR_BAR_DURATION,
    IBKR_BAR_SIZE,
    IBKR_HISTORICAL_BACKGROUND_TIMEOUT_SEC,
    IBKR_HISTORICAL_TIMEOUT_SEC,
    IBKR_HISTORICAL_USE_RTH,
    IBKR_HISTORICAL_WHAT_TO_SHOW,
)
from ibkr import client as _client
from ibkr.errors import describe_exc, is_transient_historical_failure
from ibkr.historical_gate import HistoricalBusy, historical_slot
from metrics.op_metrics import timed

logger = logging.getLogger(__name__)

_Stock = None


def _load_ib_types() -> bool:
    global _Stock
    if _Stock is not None:
        return True
    try:
        from ib_async import Stock
        _Stock = Stock
        return True
    except ImportError:
        return False


def _bar_time_iso(bar_date: datetime | date | str) -> str:
    """Normalize IB bar date to ISO-8601 UTC with Z (matches Alpaca ``t``)."""
    if isinstance(bar_date, str):
        if bar_date.endswith("Z") or "+" in bar_date[10:]:
            return bar_date
        return f"{bar_date}Z" if "T" in bar_date else f"{bar_date}T00:00:00Z"
    if isinstance(bar_date, datetime):
        if bar_date.tzinfo is None:
            bar_date = bar_date.replace(tzinfo=timezone.utc)
        else:
            bar_date = bar_date.astimezone(timezone.utc)
        return bar_date.isoformat().replace("+00:00", "Z")
    if isinstance(bar_date, date):
        return f"{bar_date.isoformat()}T00:00:00Z"
    raise TypeError(f"Unsupported IB bar date type: {type(bar_date)!r}")


def _normalize_bars(raw_bars, limit: int) -> list[dict]:
    bars: list[dict] = []
    for b in raw_bars:
        try:
            bars.append({
                "t": _bar_time_iso(b.date),
                "o": float(b.open),
                "h": float(b.high),
                "l": float(b.low),
                "c": float(b.close),
                "v": int(b.volume) if b.volume is not None else 0,
            })
        except (TypeError, ValueError, AttributeError) as exc:
            logger.debug("IBKR bar skip: %s", exc)
    if len(bars) > limit:
        bars = bars[-limit:]
    return bars


async def fetch_bars_async(
    symbol: str,
    timeframe: str = CHART_DEFAULT_TIMEFRAME,
    limit: int = CHART_DEFAULT_BARS,
    *,
    interactive: bool = False,
) -> dict:
    """Fetch OHLCV bars via ``reqHistoricalDataAsync``. Same shape as Alpaca bars.

    ``interactive=True`` for the open ticker chart — takes priority over
    background setups_stream fetches (see ``historical_gate``).
    """
    if timeframe not in CHART_TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe '{timeframe}'. Valid values: {list(CHART_TIMEFRAMES)}",
        )
    bar_size = IBKR_BAR_SIZE.get(timeframe)
    duration = IBKR_BAR_DURATION.get(timeframe)
    if not bar_size or not duration:
        raise HTTPException(status_code=400, detail=f"No IBKR mapping for timeframe '{timeframe}'")

    if not _load_ib_types():
        raise HTTPException(status_code=503, detail="ib_async not installed")

    ib = _client.get_ib()
    if ib is None:
        raise HTTPException(status_code=503, detail="IBKR not connected")

    limit = max(1, min(limit, CHART_MAX_BARS))
    timeout = IBKR_HISTORICAL_TIMEOUT_SEC if interactive else IBKR_HISTORICAL_BACKGROUND_TIMEOUT_SEC
    contract = _Stock(symbol.upper(), "SMART", "USD")

    try:
        async with historical_slot(interactive=interactive):
            try:
                qualified = await ib.qualifyContractsAsync(contract)
                if not qualified:
                    raise HTTPException(status_code=404, detail=f"Could not qualify contract for {symbol}")
                contract = qualified[0]
            except HTTPException:
                raise
            except Exception as exc:
                desc = describe_exc(exc)
                logger.error("IBKR: qualify failed for bars %s: %s", symbol, desc, exc_info=True)
                raise HTTPException(status_code=502, detail=f"IBKR qualify failed: {desc}") from exc

            try:
                async with timed("ibkr.historical_bars"):
                    raw = await ib.reqHistoricalDataAsync(
                        contract,
                        endDateTime="",
                        durationStr=duration,
                        barSizeSetting=bar_size,
                        whatToShow=IBKR_HISTORICAL_WHAT_TO_SHOW,
                        useRTH=IBKR_HISTORICAL_USE_RTH,
                        formatDate=1,
                        keepUpToDate=False,
                        timeout=timeout,
                    )
            except HTTPException:
                raise
            except Exception as exc:
                desc = describe_exc(exc)
                if is_transient_historical_failure(exc):
                    logger.warning(
                        "IBKR: historical bars transient for %s %s: %s", symbol, timeframe, desc,
                    )
                else:
                    logger.error(
                        "IBKR: historical bars failed for %s %s: %s",
                        symbol, timeframe, desc, exc_info=True,
                    )
                raise HTTPException(
                    status_code=502, detail=f"IBKR historical data failed: {desc}",
                ) from exc
    except HistoricalBusy as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    bars = _normalize_bars(raw or [], limit)
    return {"symbol": symbol.upper(), "timeframe": timeframe, "bars": bars, "source": "ibkr"}
