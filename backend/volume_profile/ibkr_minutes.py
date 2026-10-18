"""IBKR's 1-minute TRADES bars of one past regular session: yesterday's profile when the chart store lacks it (ADR 058).

One historical request in the one budget ``historical_service`` keeps (60 in 10 minutes, five a contract in 2 s, no
identical request in 15 s), at background priority: none is sent while an open chart loads, while pacing asks for a
wait, or with ``IBKR_HISTORY_TRADING_RESERVE`` or fewer requests left of the 10 minutes -- checked again once it holds
its slot. ``HistoricalShed`` then, and the desk asks again later. Nothing waits on the connect-loop (ADR 010), and
nothing is stored: the bars become a profile and are dropped.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from constants_ibkr import IBKR_HISTORY_TRADING_RESERVE
from constants_volume_profile import VP_RTH_CLOSE_MIN, VP_RTH_DURATION
from ibkr.historical_service import HistoricalShed, budget, open_chart_busy
from ibkr.loop_supervisor import assert_ib_loop
from volume_profile.profile import Bar

PACING_KEY = "bars:1min:TRADES:rth"
_ET = ZoneInfo("America/New_York")


def _blocked(symbol: str, day: date) -> str | None:
    """Why the request may not go now, or None."""
    if open_chart_busy():
        return "an open chart is loading"
    pacing, _slots = budget()
    if pacing.wait_seconds(symbol, PACING_KEY, day.isoformat()) > 0:
        return "IBKR's historical pacing asks for a wait"
    snap = pacing.snapshot()
    if snap["window_max"] - snap["window_used"] <= IBKR_HISTORY_TRADING_RESERVE:
        return f"{IBKR_HISTORY_TRADING_RESERVE} or fewer historical requests left: kept for open charts and the short check"
    return None


async def session_minutes(symbol: str, day: date, *, timeout: float) -> list[Bar]:
    """``day``'s 09:30-16:00 ET 1-minute TRADES bars, oldest first, ``t`` each minute's start in epoch seconds.
    ``HistoricalShed`` when the budget says not now; ``ValueError`` when IBKR has no such stock. Must run on the IB
    connect-loop."""
    assert_ib_loop()
    from ib_async import Stock

    from ibkr import client as _client

    sym = (symbol or "").strip().upper()
    why = _blocked(sym, day)
    if why:
        raise HistoricalShed(why)
    ib = _client.get_ib()
    if ib is None:
        raise ConnectionError("IBKR is not connected")
    qualified = await ib.qualifyContractsAsync(Stock(sym, "SMART", "USD"))
    contract = next((c for c in qualified or [] if c is not None), None)
    if contract is None:
        raise ValueError(f"IBKR could not qualify {sym}")
    close = time(VP_RTH_CLOSE_MIN // 60, VP_RTH_CLOSE_MIN % 60)
    end = datetime.combine(day, close, tzinfo=_ET).astimezone(timezone.utc)
    pacing, slots = budget()
    async with slots:
        why = _blocked(sym, day)            # again, in the slot: a chart may have opened meanwhile
        if why:
            raise HistoricalShed(why)
        pacing.record(sym, PACING_KEY, day.isoformat())
        rows = await ib.reqHistoricalDataAsync(
            contract, endDateTime=end, durationStr=VP_RTH_DURATION, barSizeSetting="1 min", whatToShow="TRADES",
            useRTH=True, formatDate=2, keepUpToDate=False, timeout=timeout,
        )
    out: list[Bar] = []
    for r in rows or []:
        if not isinstance(r.date, datetime):
            continue
        out.append(Bar(t=r.date.timestamp(), o=float(r.open), h=float(r.high), l=float(r.low), c=float(r.close),
                       v=float(r.volume or 0)))
    return out
