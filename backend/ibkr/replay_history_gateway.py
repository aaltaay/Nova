"""Read-only, separately identified Gateway connection for replay acquisition.

Fetch-only adapter: the SIM downloader (backend/sim/history_download.py) owns
pagination, pacing and persistence. Live port first, paper when live is dark.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from constants_ibkr import IBKR_HOST, IBKR_LIVE_PORT, IBKR_PAPER_PORT
from constants_sim import (
    SIM_HISTORY_CLIENT_ID, SIM_HISTORY_CONNECT_TIMEOUT_SEC, SIM_HISTORY_GATEWAY_UNREACHABLE,
    SIM_HISTORY_PAGE_SIZE, SIM_HISTORY_REQUEST_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)


def candidate_ports() -> list[int]:
    live = int(os.environ.get("IBKR_LIVE_PORT", str(IBKR_LIVE_PORT)))
    paper = int(os.environ.get("IBKR_PAPER_PORT", str(IBKR_PAPER_PORT)))
    return list(dict.fromkeys([live, paper]))


class ReplayHistoryGateway:
    def __init__(self, client_id: int = SIM_HISTORY_CLIENT_ID):
        self.ib = None
        self.contract = None
        self.client_id = client_id

    async def open(self, symbol):
        from ib_async import IB, Stock, StartupFetch
        host = os.environ.get("IBKR_HOST", IBKR_HOST)
        failures = []
        for port in candidate_ports():
            self.ib = IB()
            self.ib.RaiseRequestErrors = True
            try:
                await self.ib.connectAsync(
                    host, port, clientId=self.client_id, readonly=True,
                    fetchFields=StartupFetch(0), timeout=SIM_HISTORY_CONNECT_TIMEOUT_SEC,
                )
                break
            except (ConnectionError, OSError, TimeoutError) as exc:
                logger.warning("Historical replay: Gateway port %s unavailable: %s", port, exc)
                failures.append(f"{port}: {exc or type(exc).__name__}")
                self.ib.disconnect()
        else:
            raise ConnectionError(f"{SIM_HISTORY_GATEWAY_UNREACHABLE} (" + "; ".join(failures) + ")")
        qualified = await self.ib.qualifyContractsAsync(Stock(symbol, "SMART", "USD"))
        if len(qualified) != 1:
            raise ValueError("Ticker could not be uniquely qualified by IBKR")
        self.contract = qualified[0]
        return {k: getattr(self.contract, k) for k in
                ("conId", "symbol", "localSymbol", "secType", "exchange", "primaryExchange", "currency")}

    async def trades(self, cursor):
        ticks = await self.ib.reqHistoricalTicksAsync(
            self.contract, datetime.fromtimestamp(cursor, timezone.utc), "",
            SIM_HISTORY_PAGE_SIZE, "TRADES", False, False,
        )
        return [dict(ts=int(t.time.timestamp()), symbol=self.contract.symbol,
                     price=float(t.price), size=float(t.size), exchange=t.exchange,
                     conditions=t.specialConditions,
                     past_limit=t.tickAttribLast.pastLimit,
                     unreported=t.tickAttribLast.unreported) for t in ticks]

    async def bars(self, job) -> list[dict]:
        rows = await self.ib.reqHistoricalDataAsync(
            self.contract, endDateTime=datetime.fromtimestamp(job["end_ts"], timezone.utc),
            durationStr="1 D", barSizeSetting="1 min", whatToShow="TRADES", useRTH=False,
            formatDate=2, timeout=SIM_HISTORY_REQUEST_TIMEOUT_SEC,
        )
        if not rows:
            raise ValueError("IBKR returned no historical candles for this session")
        bars = [dict(t=r.date.astimezone(timezone.utc).isoformat(), o=r.open,
                     h=r.high, l=r.low, c=r.close, v=float(r.volume)) for r in rows
                if job["start_ts"] <= r.date.timestamp() < job["end_ts"]]
        if not bars:
            raise ValueError("No candles fall inside the requested window")
        return bars

    def close(self):
        if self.ib is not None:
            self.ib.disconnect()
