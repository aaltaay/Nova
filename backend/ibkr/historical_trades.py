"""IBKR's trades of the minutes before a moment, paged and paced (ADR 012; ADR 047 amendment 2026-10-13).

``recent_trades`` reads ``reqHistoricalTicks`` (TRADES) back from ``end`` until it covers ``back_sec`` or has
read ``max_pages`` pages of IBKR's 1,000 ticks. When the pages stop short (a busy stock), one more request reads
IBKR's 1-minute TRADES bars of the minutes they did not reach: each bar's average price and trade count. LULD's
live worker asks it once when it starts following a stock mid-session, so the band shows without five minutes of
Nova's own tape (``luld/backfill.py``).

Each page is a historical request in the one budget ``historical_service`` keeps (60 in 10 minutes, five a
contract in 2 s, no identical request in 15 s): no page is sent while an open chart loads, while pacing asks for a
wait, or when it would leave fewer than ``headroom`` requests of the 10 minutes -- checked again once a request holds
its slot, since a chart may open, or other requests spend the budget, while it waits for one. Before the first page that raises
``HistoricalShed`` and the caller asks again later; after it, the pages stop and what was read comes back marked
incomplete. Nothing waits on the connect-loop (ADR 010), nothing is stored.

Prices set by a print follow Nova's one rule (``sale_conditions.sets_price``), as on the live tape. A tick's time is
IBKR's whole second.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from ibkr.historical_service import HistoricalShed, budget, open_chart_busy
from ibkr.loop_supervisor import assert_ib_loop
from sale_conditions import sets_price

logger = logging.getLogger(__name__)
PAGE_TICKS = 1000                 # IBKR's most per reqHistoricalTicks
PACING_KEY = "ticks:TRADES"
BARS_KEY = "bars:1min:TRADES"


class UnknownContract(ValueError):
    """IBKR qualified no US stock for the symbol: there is no such ticker (still a ValueError, as before)."""


def _blocked(symbol: str, page_end: float, headroom: int, key: str = PACING_KEY) -> str | None:
    """Why the next request may not go now, or None."""
    if open_chart_busy():
        return "an open chart is loading"
    pacing, _slots = budget()
    if pacing.wait_seconds(symbol, key, f"{page_end:.0f}") > 0:
        return "IBKR's historical pacing asks for a wait"
    snap = pacing.snapshot()
    if snap["window_max"] - snap["window_used"] <= headroom:
        return f"fewer than {headroom + 1} historical requests left in IBKR's 10-minute budget"
    return None


def _row(tick: Any) -> dict[str, Any]:
    attrib = getattr(tick, "tickAttribLast", None)
    unreported = bool(getattr(attrib, "unreported", False))
    conditions = getattr(tick, "specialConditions", None) or ""
    return {"ts": float(tick.time.timestamp()), "price": float(tick.price), "exchange": getattr(tick, "exchange", "") or "",
            "conditions": conditions, "sets_price": sets_price(conditions, unreported=unreported)}


async def recent_trades(symbol: str, end: float, back_sec: float, *, max_pages: int, headroom: int,
                        timeout: float) -> dict[str, Any]:
    """Every trade from ``end - back_sec`` up to (not including) IBKR's second ``end``, oldest first:
    ``{trades: [{ts, price, exchange, conditions, sets_price}], since, complete, pages, minutes, minutes_note}``.
    ``since`` is how far back they reach (``end - back_sec`` when ``complete``). ``minutes`` are IBKR's 1-minute bars
    from ``end - back_sec`` to ``since`` when the trades stop short: ``[{ts, average, count}]``, ``ts`` the minute's
    start; ``minutes_note`` says why there are none. ``UnknownContract`` when IBKR has no such stock. Must run on the
    IB connect-loop."""
    assert_ib_loop()
    from ib_async import Stock

    from ibkr import client as _client

    sym = (symbol or "").strip().upper()
    end = float(int(end))
    start = end - back_sec
    why = _blocked(sym, end, headroom)
    if why:
        raise HistoricalShed(why)
    ib = _client.get_ib()
    if ib is None:
        raise ConnectionError("IBKR is not connected")
    qualified = await ib.qualifyContractsAsync(Stock(sym, "SMART", "USD"))
    contract = next((c for c in qualified or [] if c is not None), None)
    if contract is None:
        raise UnknownContract(f"IBKR could not qualify {sym}")
    pacing, slots = budget()
    rows: list[dict[str, Any]] = []
    page_end, pages, complete = end, 0, False
    while pages < max_pages:
        async with slots:
            why = _blocked(sym, page_end, headroom)     # again, in the slot: a chart may have opened meanwhile
            if why:
                if not pages:
                    raise HistoricalShed(why)
                break                               # keep the pages read; the rest is unread, so incomplete
            pacing.record(sym, PACING_KEY, f"{page_end:.0f}")
            try:
                ticks = await asyncio.wait_for(ib.reqHistoricalTicksAsync(
                    contract, "", datetime.fromtimestamp(page_end, timezone.utc), PAGE_TICKS, "TRADES", False, False,
                ), timeout=timeout)
            except asyncio.TimeoutError:
                if not pages:
                    raise
                break                       # keep the pages read; the rest is unread, so incomplete
        pages += 1
        # Pages meet inside a second: the later page keeps its share of it and the earlier drops its own, so no
        # trade counts twice (a part of one second may be missed).
        got = [r for r in (_row(t) for t in ticks or []) if r["ts"] < page_end and r["price"] > 0]
        if not got:
            complete = True                 # nothing earlier: the window had no more trades
            break
        rows[:0] = got
        page_end = got[0]["ts"]
        if page_end <= start or len(ticks) < PAGE_TICKS:
            complete = True
            break
    kept = [r for r in rows if r["ts"] > start]
    since = start if complete else (kept[0]["ts"] if kept else end)
    minutes: list[dict[str, Any]] = []
    note = None
    if not complete and kept:
        note = _blocked(sym, since, headroom, BARS_KEY)
        if note is None:
            try:
                minutes = await _minutes(ib, contract, sym, start, since, end, headroom, timeout)
            except HistoricalShed as exc:
                note = str(exc)
            except Exception as exc:  # the trades stand without them; the note says why
                note = f"IBKR's 1-minute bars were not read ({type(exc).__name__}: {exc})"
                logger.info("LULD backfill: %s for %s", note, sym)
    return {"trades": kept, "since": since, "complete": complete, "pages": pages, "minutes": minutes,
            "minutes_note": note}


async def _minutes(ib: Any, contract: Any, sym: str, start: float, since: float, end: float, headroom: int,
                   timeout: float) -> list[dict[str, Any]]:
    """IBKR's 1-minute TRADES bars that overlap ``start`` to ``since``, up to ``end``: ``[{ts, average, count}]``.
    ``HistoricalShed`` when, once it holds its slot, an open chart or the budget says not now."""
    pacing, slots = budget()
    async with slots:
        why = _blocked(sym, since, headroom, BARS_KEY)
        if why:
            raise HistoricalShed(why)
        pacing.record(sym, BARS_KEY, f"{since:.0f}")
        bars = await ib.reqHistoricalDataAsync(
            contract, endDateTime=datetime.fromtimestamp(end, timezone.utc), durationStr=f"{int(end - start) + 60} S",
            barSizeSetting="1 min", whatToShow="TRADES", useRTH=False, formatDate=2, timeout=timeout,
        )
    out = []
    for bar in bars or []:
        ts = bar.date.timestamp() if isinstance(bar.date, datetime) else None
        if ts is not None and start - 60 < ts < since and bar.barCount > 0 and bar.average > 0:
            out.append({"ts": ts, "average": float(bar.average), "count": int(bar.barCount)})
    return out
