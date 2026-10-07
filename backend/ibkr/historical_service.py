"""Paced IBKR historical fetch service (ADR 012).

The only production owner of ``reqHistoricalData`` scheduling. HTTP chart
reads come from ``bars_store``; this module replenishes the store and pushes
``bars_patch`` when a fill lands.

Priority: open_chart > warm > background. Background is shed when an open
chart is in flight or the pacing budget is tight -- not queued behind it. A
pair whose last fetch IBKR did not answer is shed for every priority until its
backoff passes (``historical_failures``, #555); the pane's retry asks again.

Nothing here may occupy the IB connect-loop: every pacing wait reschedules via
``call_later`` (never ``sleep``-then-send) and every ``bars_store`` call is a
SQLite round trip handed to a worker thread (ADR 010).
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from constants import (
    CHART_DEFAULT_BARS,
    IBKR_BAR_DURATION,
    IBKR_HISTORICAL_MAX_CONCURRENT,
)
from ibkr import historical_failures
from ibkr.historical_derive import DERIVE_FROM_1MIN, derive_from_1min
from ibkr.historical_pacing import HistoricalPacing
from ibkr.loop_supervisor import assert_ib_loop

logger = logging.getLogger(__name__)

Priority = Literal["open_chart", "warm", "background"]
# The pacing key of a regular-hours daily request (ADR 040): not a chart timeframe, so it never dedupes
# against the desk's extended-hours daily bars.
RTH_DAILY_KEY = "1Day:rth"
# ADR 048's SSR read: the same daily bars with extended hours, kept apart from the chart's own key.
ALL_DAILY_KEY = "1Day:all"
_ET = ZoneInfo("America/New_York")


class HistoricalBusy(Exception):
    """Interactive historical work is using the budget."""


class HistoricalShed(Exception):
    """Background/warm work dropped so an open chart (or pacing) can proceed."""


_open_chart_depth = 0
_sem: asyncio.Semaphore | None = None
_inflight: dict[tuple[str, str], asyncio.Task] = {}
_pacing = HistoricalPacing()


def reset_for_testing() -> None:
    global _open_chart_depth, _sem
    _open_chart_depth = 0
    _sem = None
    leftover = list(_inflight.values())
    _inflight.clear()
    _pacing.reset()
    historical_failures.reset()
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
    stored = await asyncio.to_thread(bars_store.read, symbol, timeframe, limit)
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

    backoff = historical_failures.backoff_remaining(symbol, timeframe)
    if backoff > 0:
        # IBKR did not answer this pair moments ago. Re-sending now would spend
        # the budget on the same silence; the pane's retry asks again later.
        raise HistoricalShed(f"IBKR did not answer; next try in {backoff:.1f}s")

    duration = IBKR_BAR_DURATION.get(timeframe) or ""
    wait = _pacing.wait_seconds(symbol, timeframe, duration)
    if wait > 0 and priority != "open_chart":
        logger.info(
            "historical fill shed %s %s: pacing wait %.1fs priority=%s",
            symbol, timeframe, wait, priority,
        )
        raise HistoricalShed(f"pacing wait {wait:.1f}s")
    if wait > 0:
        logger.info(
            "historical fill rescheduled %s %s: wait %.1fs priority=%s",
            symbol, timeframe, wait, priority,
        )
        _reschedule_after_wait(symbol, timeframe, limit, priority, wait)
        raise HistoricalShed(f"pacing wait {wait:.1f}s")

    task = asyncio.create_task(
        _run_fetch(symbol, timeframe, limit, priority),
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
) -> dict[str, Any]:
    global _open_chart_depth
    import bars_store
    from ibkr import bars as ibkr_bars
    from ticker_bars_push import broadcast_bars_patch

    if priority == "open_chart":
        _open_chart_depth += 1
    try:
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
                # Raising releases the semaphore before the wait, so a paced
                # open_chart cannot hold a hist slot idle.
                logger.info(
                    "historical fill rescheduled %s %s: wait %.1fs priority=%s (in flight)",
                    symbol, timeframe, extra, priority,
                )
                _reschedule_after_wait(symbol, timeframe, limit, priority, extra)
                raise HistoricalShed(f"pacing wait {extra:.1f}s")
            _pacing.record(symbol, timeframe, duration)
            try:
                result = await ibkr_bars.fetch_bars_async(
                    symbol,
                    timeframe,
                    limit,
                    interactive=(priority == "open_chart"),
                )
            except HTTPException as exc:
                if historical_failures.remembered(exc.status_code):
                    historical_failures.note(symbol, timeframe, str(exc.detail))
                raise
            historical_failures.clear(symbol, timeframe)
            coverage = {
                **bars_store.coverage_from_bars(result.get("bars") or [], filling=False),
                **historical_failures.coverage_fields(symbol, timeframe),
            }
            result = {**result, "coverage": coverage}
            await asyncio.to_thread(bars_store.write_payload, result)
            if timeframe == "1Min":
                await _persist_derived(symbol, result)
            try:
                broadcast_bars_patch(symbol, result)
            except Exception:
                logger.debug("bars_patch failed for %s %s", symbol, timeframe)
            return result
    finally:
        if priority == "open_chart":
            _open_chart_depth = max(0, _open_chart_depth - 1)


async def request_daily_bars(symbol: str, duration: str, *, use_rth: bool) -> list[dict[str, Any]]:
    """IBKR's daily TRADES bars, ``[{date, open, high, low, close}]`` oldest first (ADR 040, ADR 048).

    ``use_rth``: the regular session's bars, whose close is the official one, never the last
    after-hours trade the desk's stored daily bars end on; without it, the whole 04:00-20:00 day,
    today's bar running to now (the SSR read takes its low). Background priority, paced like every
    other historical request: ``HistoricalShed`` while an open chart is loading or pacing asks for a
    wait, and the caller asks again later. Nothing is stored or pushed. Must run on the IB connect-loop.
    """
    assert_ib_loop()
    from ib_async import Stock

    from constants import IBKR_HISTORICAL_BACKGROUND_TIMEOUT_SEC
    from ibkr import client as _client

    sym = symbol.upper()
    key = RTH_DAILY_KEY if use_rth else ALL_DAILY_KEY
    if open_chart_busy():
        raise HistoricalShed("open chart has priority")
    if _pacing.wait_seconds(sym, key, duration) > 0:
        raise HistoricalShed("pacing asks for a wait")
    ib = _client.get_ib()
    if ib is None:
        raise ConnectionError("IBKR is not connected")
    async with _semaphore():
        if _pacing.wait_seconds(sym, key, duration) > 0:
            raise HistoricalShed("pacing asks for a wait")
        _pacing.record(sym, key, duration)
        qualified = await ib.qualifyContractsAsync(Stock(sym, "SMART", "USD"))
        contract = next((c for c in qualified or [] if c is not None), None)
        if contract is None:
            raise ValueError(f"IBKR could not qualify {sym}")
        rows = await ib.reqHistoricalDataAsync(
            contract, endDateTime="", durationStr=duration, barSizeSetting="1 day", whatToShow="TRADES",
            useRTH=use_rth, formatDate=1, keepUpToDate=False, timeout=IBKR_HISTORICAL_BACKGROUND_TIMEOUT_SEC,
        )
    out: list[dict[str, Any]] = []
    for r in rows or []:
        when = r.date.astimezone(_ET).date() if isinstance(r.date, datetime) else r.date
        bar = {k: _bar_price(getattr(r, k, None)) for k in ("open", "high", "low", "close")}
        if bar["close"] is not None:  # a bar without a close is no session; a missing low reads unknown
            out.append({"date": when.isoformat(), **bar})
    return out


def _bar_price(value: Any) -> float | None:
    price = float(value) if isinstance(value, (int, float)) else math.nan
    return price if math.isfinite(price) and price > 0 else None


async def request_rth_daily_closes(symbol: str, duration: str) -> list[tuple[str, float]]:
    """``(session date, close)`` of IBKR's regular-hours daily TRADES bars, oldest first (ADR 040)."""
    return [(bar["date"], bar["close"]) for bar in await request_daily_bars(symbol, duration, use_rth=True)]


async def _persist_derived(symbol: str, one_min: dict[str, Any]) -> None:
    import bars_store
    from ticker_bars_push import broadcast_bars_patch

    source_bars = one_min.get("bars") or []
    for tf in DERIVE_FROM_1MIN:
        derived = derive_from_1min(source_bars, tf)
        if not derived:
            continue
        existing = await asyncio.to_thread(
            bars_store.read, symbol, tf, CHART_DEFAULT_BARS,
        )
        existing_n = len((existing or {}).get("bars") or [])
        if existing_n > int(len(derived) * 1.2):
            continue
        payload = {
            "symbol": symbol,
            "timeframe": tf,
            "bars": derived,
            "source": "ibkr",
            "coverage": {
                **bars_store.coverage_from_bars(
                    derived, filling=True, derived_from="1Min",
                ),
                # The derived pane's own fetch may still be failing (#555).
                **historical_failures.coverage_fields(symbol, tf),
            },
        }
        await asyncio.to_thread(bars_store.write_payload, payload)
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
    """Re-queue an open_chart fill once pacing frees the request.

    Every wait reschedules -- the 10-minute bucket debt and the short
    same-contract / identical-request windows alike. Awaiting the wait here
    instead would keep the fill parked on the IB connect-loop holding a hist
    semaphore slot while ``reqMktData`` L1 ticks share that loop.
    ``request_bars`` re-checks pacing on wake.
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
        except HTTPException as exc:
            # Stated IBKR failures (a timeout, an error answer): nothing was
            # stored or pushed, the pane stays "filling" and its retry asks
            # again; `historical_failures` holds the reason for `/bars`.
            logger.warning(
                "historical fill failed %s %s: %s", symbol, timeframe, exc.detail,
            )
        except Exception:
            logger.warning(
                "historical fill failed %s %s", symbol, timeframe, exc_info=True,
            )

    spawn_ib(f"bars.fill.{symbol}.{timeframe}", lambda: _job())
