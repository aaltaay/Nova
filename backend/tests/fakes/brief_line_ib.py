"""An IB stand-in for ``ibkr.brief_lines``: ib_async's pooled tickers and its one-subscription-per-contract rule.

``ticks`` maps a conId to the fields IBKR sends after ``delay``, or to ``[(delay, fields), ...]`` when they arrive
in steps (a stock's quote before its last trade).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from ib_async import Contract, Ticker


class FakeIB:
    def __init__(self, ticks: dict[int, dict | list] | None = None, delay: float = 0.02):
        self.ticks = ticks or {}
        self.delay = delay
        self.pool: dict[int, Ticker] = {}
        self.live: dict[int, SimpleNamespace] = {}
        self.generic: dict[int, str] = {}
        self.cancelled: list[int] = []
        self.open_now = 0
        self.open_max = 0
        self.wrapper = SimpleNamespace(subscriptions=SimpleNamespace(find_market_data=self._find))

    def _find(self, con_id, kind):
        return self.live.get(con_id)

    def reqMktData(self, contract, generic_ticks="", *_args):
        held = self.live.get(contract.conId)
        if held is not None:
            return held.ticker
        ticker = self.pool.setdefault(contract.conId, Ticker(contract=contract))
        self.live[contract.conId] = SimpleNamespace(ticker=ticker)
        self.generic[contract.conId] = generic_ticks
        self.open_now += 1
        self.open_max = max(self.open_max, self.open_now)
        steps = self.ticks.get(contract.conId)
        if isinstance(steps, dict):
            steps = [(self.delay, steps)]
        loop = asyncio.get_running_loop()
        for delay, fields in steps or []:
            loop.call_later(delay, lambda f=fields: [setattr(ticker, k, v) for k, v in f.items()])
        return ticker

    def cancelMktData(self, contract):
        self.live.pop(contract.conId)
        self.cancelled.append(contract.conId)
        self.open_now -= 1

    def hold(self, contract, **fields) -> Ticker:
        """The desk already streams ``contract``: its line and ticker."""
        ticker = Ticker(contract=contract)
        for k, v in fields.items():
            setattr(ticker, k, v)
        self.live[contract.conId] = SimpleNamespace(ticker=ticker)
        return ticker


def contracts(n: int) -> list[Contract]:
    return [Contract(conId=i + 1, symbol=f"S{i + 1}") for i in range(n)]


def stock_qualifier(symbols_to_ids: dict[str, int] | None = None):
    """``qualifyContractsAsync`` answering each symbol with a stock contract (conIds 1, 2, ... or the map's)."""
    async def qualify(*stocks):
        return [Contract(conId=(symbols_to_ids or {}).get(s.symbol, i + 1), symbol=s.symbol, secType="STK")
                for i, s in enumerate(stocks)]
    return qualify
