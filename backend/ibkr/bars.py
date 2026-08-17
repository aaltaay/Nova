"""IBKR historical OHLCV bars for the ticker chart.

Returns the same shape as ``bars.fetch_bars`` (Alpaca) so the frontend chart
needs no provider-specific code. Used when ``discovery_provider=ibkr`` so
candles match IBKR live quotes instead of sparse Alpaca IEX bars.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone

from fastapi import HTTPException

from constants import (
    CHART_DEFAULT_BARS,
    CHART_DEFAULT_TIMEFRAME,
    CHART_MAX_BARS,
    CHART_TIMEFRAMES,
    IBKR_10SEC_FETCH_BARS,
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
from metrics.op_metrics import record, timed

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

    ``interactive=True`` for the open ticker chart -- takes priority over
    background setups_stream fetches (see ``historical_gate``).

    Fresh TTL cache + single-flight live in ``bars_cache`` (never serves expired).
    """
    from ibkr import bars_cache

    # 10Sec: always store/return the full 4h window (default 500 would trim ~83 min).
    if timeframe == "10Sec":
        limit = max(limit, IBKR_10SEC_FETCH_BARS)
    limit = max(1, min(limit, CHART_MAX_BARS))
    return await bars_cache.get_or_fetch(
        symbol,
        timeframe,
        limit,
        interactive=interactive,
        fetch_fn=_fetch_bars_uncached,
    )


async def _fetch_bars_uncached(
    symbol: str,
    timeframe: str,
    limit: int,
    *,
    interactive: bool = False,
) -> dict:
    """IB Gateway historical fetch (no cache). Called only on cache miss."""
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
        raise HTTPException(
            status_code=503,
            detail=_client.unavailable_detail("IBKR bars"),
        )

    # Defense: cache path already clamps in fetch_bars_async; keep uncached path honest.
    if timeframe == "10Sec":
        limit = max(limit, IBKR_10SEC_FETCH_BARS)

    timeout = IBKR_HISTORICAL_TIMEOUT_SEC if interactive else IBKR_HISTORICAL_BACKGROUND_TIMEOUT_SEC
    contract = _Stock(symbol.upper(), "SMART", "USD")
    raw = None
    slot_wait_s = 0.0
    fetch_s = 0.0

    try:
        wait_started = time.perf_counter_ns()
        async with historical_slot(interactive=interactive):
            # First line after acquire -- wait time is lock queue only.
            slot_wait_ns = time.perf_counter_ns() - wait_started
            record("ibkr.historical_slot_wait", slot_wait_ns)
            slot_wait_s = slot_wait_ns / 1_000_000_000
            fetch_started = time.perf_counter()
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
            finally:
                fetch_s = time.perf_counter() - fetch_started
    except HistoricalBusy as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    bars = _normalize_bars(raw or [], limit)
    logger.info(
        "IBKR bars timing %s %s slot_wait=%.1fs fetch=%.1fs bars=%d",
        symbol.upper(), timeframe, slot_wait_s, fetch_s, len(bars),
    )
    return {"symbol": symbol.upper(), "timeframe": timeframe, "bars": bars, "source": "ibkr"}


async def warm_symbol_bars(
    symbol: str,
    timeframes: tuple[str, ...] | list[str] | None = None,
) -> None:
    """Prefetch grid timeframes into the TTL cache.

    Ticker WS no longer calls this -- a parallel warm raced Trader `/bars`
    and got `run_coro` cancelled at 25s. Kept for explicit/ops use.
    """
    from constants import IBKR_BARS_WARM_TIMEFRAMES

    symbol = symbol.upper()
    tfs = tuple(timeframes) if timeframes else IBKR_BARS_WARM_TIMEFRAMES
    for tf in tfs:
        try:
            await fetch_bars_async(
                symbol, tf, CHART_DEFAULT_BARS, interactive=True,
            )
        except Exception as exc:
            logger.debug("IBKR bars warm skipped for %s %s: %s", symbol, tf, exc)
