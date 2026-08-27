"""Paced IBKR historical fetch service (ADR 012).

The only production owner of ``reqHistoricalData`` scheduling. HTTP chart
reads come from ``bars_store``; this module replenishes the store and pushes
``bars_patch`` when a fill lands.

Priority: open_chart > warm > background. Background is shed when an open
chart is in flight or the pacing budget is tight -- not queued behind it.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from constants import (
    CHART_DEFAULT_BARS,
    IBKR_BAR_DURATION,
    IBKR_HISTORICAL_MAX_CONCURRENT,
    IBKR_HISTORICAL_IDENTICAL_COOLDOWN_SEC,
    IBKR_HISTORICAL_SAME_CONTRACT_WINDOW_SEC,
)
from ibkr.historical_derive import DERIVE_FROM_1MIN, derive_from_1min
from ibkr.historical_pacing import HistoricalPacing
from ibkr.loop_supervisor import assert_ib_loop

logger = logging.getLogger(__name__)

Priority = Literal["open_chart", "warm", "background"]


class HistoricalBusy(Exception):
    """Interactive historical work is using the budget."""


class HistoricalShed(Exception):
    """Background/warm work dropped so an open chart (or pacing) can proceed."""


_open_chart_depth = 0
_sem: asyncio.Semaphore | None = None
_inflight: dict[tuple[str, str], asyncio.Task] = {}
_pacing = HistoricalPacing()
# Short IB windows (same-contract 2s, identical-request 15s) may be slept on the
# IB loop. The 10-minute global bucket must reschedule, not sleep-then-send.
_SHORT_PACING_WAIT_SEC = max(
    float(IBKR_HISTORICAL_SAME_CONTRACT_WINDOW_SEC),
    float(IBKR_HISTORICAL_IDENTICAL_COOLDOWN_SEC),
)


def reset_for_testing() -> None:
    global _open_chart_depth, _sem
    _open_chart_depth = 0
    _sem = None
    leftover = list(_inflight.values())
    _inflight.clear()
    _pacing.reset()
    for task in leftover:
        if not task.done():
            task.cancel()


def open_chart_busy() -> bool:
    return _open_chart_depth > 0


def pacing_snapshot() -> dict:
    """Read-only view of the 60-req/10-min budget (see ``historical_pacing.py``)."""
    return _pacing.snapshot()


def _semaphore() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(int(IBKR_HISTORICAL_MAX_CONCURRENT))
    return _sem


def _trim(payload: dict[str, Any], limit: int) -> dict[str, Any]:
    bars = list(payload.get("bars") or [])
    if limit < len(bars):
        bars = bars[-limit:]
    out = {**payload, "bars": bars}
    return out


async def request_bars(
    symbol: str,
    timeframe: str,
    limit: int,
    *,
    priority: Priority = "background",
) -> dict[str, Any]:
    """Deduped paced fetch. Must run on the IB connect-loop."""
    assert_ib_loop()
    import bars_store

    symbol = symbol.upper()
    stored = bars_store.read(symbol, timeframe, limit)
    stored_n = len((stored or {}).get("bars") or [])
    if (
        stored
        and bars_store.store_series_complete(timeframe, stored_n)
        and bars_store.is_coverage_fresh(stored.get("coverage"), timeframe)
        and not (stored.get("coverage") or {}).get("filling")
    ):
        return stored

    key = (symbol, timeframe)
    existing = _inflight.get(key)
    if existing is not None:
        if priority == "background" and open_chart_busy():
            logger.info(
                "historical fill shed %s %s: open chart has priority (inflight)",
                symbol, timeframe,
            )
            if stored and stored.get("bars"):
                return stored
            raise HistoricalShed("open chart has priority")
        result = await asyncio.shield(existing)
        return _trim(result, limit)

    if priority == "background" and open_chart_busy():
        logger.info("historical fill shed %s %s: open chart has priority", symbol, timeframe)
        if stored and stored.get("bars"):
            return stored
        raise HistoricalShed("open chart has priority")

    duration = IBKR_BAR_DURATION.get(timeframe) or ""
    wait = _pacing.wait_seconds(symbol, timeframe, duration)
    if wait > 0 and priority != "open_chart":
        logger.info(
            "historical fill shed %s %s: pacing wait %.1fs priority=%s",
            symbol, timeframe, wait, priority,
        )
        raise HistoricalShed(f"pacing wait {wait:.1f}s")
    if wait > 0 and wait > _SHORT_PACING_WAIT_SEC:
        logger.info(
            "historical fill rescheduled %s %s: wait %.1fs priority=%s",
            symbol, timeframe, wait, priority,
        )
        _reschedule_after_wait(symbol, timeframe, limit, priority, wait)
        raise HistoricalShed(f"pacing wait {wait:.1f}s")
    if wait > 0:
        logger.info(
            "historical fill deferred %s %s: wait %.1fs priority=%s",
            symbol, timeframe, wait, priority,
        )

    task = asyncio.create_task(
        _run_fetch(symbol, timeframe, limit, priority, wait),
        name=f"hist.{priority}.{symbol}.{timeframe}",
    )
    _inflight[key] = task

    def _drop(done: asyncio.Task) -> None:
        if _inflight.get(key) is done:
            del _inflight[key]

    task.add_done_callback(_drop)
    result = await asyncio.shield(task)
    return _trim(result, limit)


async def _run_fetch(
    symbol: str,
    timeframe: str,
    limit: int,
    priority: Priority,
    wait: float,
) -> dict[str, Any]:
    global _open_chart_depth
    import bars_store
    from ibkr import bars as ibkr_bars
    from ticker_bars_push import broadcast_bars_patch

    if priority == "open_chart":
        _open_chart_depth += 1
    try:
        if wait > 0:
            await asyncio.sleep(min(wait, 16.0))
        async with _semaphore():
            duration = IBKR_BAR_DURATION.get(timeframe) or ""
            extra = _pacing.wait_seconds(symbol, timeframe, duration)
            if extra > 0:
                if priority != "open_chart":
                    logger.info(
                        "historical fill shed %s %s: pacing wait %.1fs (in flight)",
                        symbol, timeframe, extra,
                    )
                    raise HistoricalShed(f"pacing wait {extra:.1f}s")
                if extra > _SHORT_PACING_WAIT_SEC:
                    logger.info(
                        "historical fill rescheduled %s %s: wait %.1fs priority=%s (in flight)",
                        symbol, timeframe, extra, priority,
                    )
                    _reschedule_after_wait(symbol, timeframe, limit, priority, extra)
                    raise HistoricalShed(f"pacing wait {extra:.1f}s")
                logger.info(
                    "historical fill deferred %s %s: wait %.1fs priority=%s (in flight)",
                    symbol, timeframe, extra, priority,
                )
                await asyncio.sleep(extra)
            _pacing.record(symbol, timeframe, duration)
            result = await ibkr_bars.fetch_bars_async(
                symbol,
                timeframe,
                limit,
                interactive=(priority == "open_chart"),
            )
            coverage = bars_store.coverage_from_bars(
                result.get("bars") or [], filling=False,
            )
            result = {**result, "coverage": coverage}
            bars_store.write_payload(result)
            if timeframe == "1Min":
                _persist_derived(symbol, result)
            try:
                broadcast_bars_patch(symbol, result)
            except Exception:
                logger.debug("bars_patch failed for %s %s", symbol, timeframe)
            return result
    finally:
        if priority == "open_chart":
            _open_chart_depth = max(0, _open_chart_depth - 1)


def _persist_derived(symbol: str, one_min: dict[str, Any]) -> None:
    import bars_store
    from ticker_bars_push import broadcast_bars_patch

    source_bars = one_min.get("bars") or []
    for tf in DERIVE_FROM_1MIN:
        derived = derive_from_1min(source_bars, tf)
        if not derived:
            continue
        existing = bars_store.read(symbol, tf, CHART_DEFAULT_BARS)
        existing_n = len((existing or {}).get("bars") or [])
        if existing_n > int(len(derived) * 1.2):
            continue
        payload = {
            "symbol": symbol,
            "timeframe": tf,
            "bars": derived,
            "source": "ibkr",
            "coverage": bars_store.coverage_from_bars(
                derived, filling=True, derived_from="1Min",
            ),
        }
        bars_store.write_payload(payload)
        try:
            broadcast_bars_patch(symbol, payload)
        except Exception:
            logger.debug("derived bars_patch failed for %s %s", symbol, tf)


def _reschedule_after_wait(
    symbol: str,
    timeframe: str,
    limit: int,
    priority: Priority,
    wait: float,
) -> None:
    """Re-queue an open_chart fill when the 10-min bucket frees a token.

    Sleeping hundreds of seconds on the IB connect-loop would stall L1 ticks.
    call_later keeps the loop free; request_bars re-checks pacing on wake.
    """
    from ibkr.loop_supervisor import get_loop

    loop = get_loop()
    if loop is None or not loop.is_running():
        return

    def _again() -> None:
        try:
            schedule_fill(symbol, timeframe, limit, priority=priority)
        except Exception:
            logger.debug("rescheduled fill failed to spawn %s %s", symbol, timeframe)

    loop.call_later(max(0.5, float(wait)), _again)


def schedule_fill(
    symbol: str,
    timeframe: str,
    limit: int,
    *,
    priority: Priority = "open_chart",
) -> None:
    """Fire-and-forget fill on the IB loop. No-op if the supervisor is down."""
    from ibkr.loop_supervisor import is_started, spawn_ib

    if not is_started():
        return

    async def _job() -> None:
        try:
            await request_bars(symbol, timeframe, limit, priority=priority)
        except HistoricalShed as exc:
            logger.info("historical fill shed %s %s: %s", symbol, timeframe, exc)
        except Exception:
            logger.warning(
                "historical fill failed %s %s", symbol, timeframe, exc_info=True,
            )

    spawn_ib(f"bars.fill.{symbol}.{timeframe}", lambda: _job())
