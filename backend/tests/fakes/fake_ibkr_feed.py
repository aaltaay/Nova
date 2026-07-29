"""Scriptable fake of the ib_async market-data surface used by ibkr/ticks.py.

Simulates one IB Gateway *connection*: ``reqMktData`` returns a FakeTicker
whose ``updateEvent`` the real ``ibkr.ticks`` module attaches to, and tests
drive ticks via ``feed.emit(...)``. A reconnect is simulated by swapping
``ibkr.client.get_ib`` to a NEW FakeIbkrFeed -- server-side streams from the
old connection are gone, so anything still attached to old tickers is dead.
"""
from __future__ import annotations

from typing import Any, Callable


class FakeTickerEvent:
    """Minimal += / -= / fire event matching ib_async's Event protocol."""

    def __init__(self) -> None:
        self._handlers: list[Callable] = []

    def __iadd__(self, handler: Callable) -> "FakeTickerEvent":
        self._handlers.append(handler)
        return self

    def __isub__(self, handler: Callable) -> "FakeTickerEvent":
        self._handlers.remove(handler)
        return self

    def fire(self, *args: Any) -> None:
        for handler in list(self._handlers):
            handler(*args)


class FakeTicker:
    """Attribute bag mirroring the ib_async Ticker fields ticks.py reads."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.last: float | None = None
        self.close: float | None = None
        self.high: float | None = None
        self.volume: float | None = None
        self.updateEvent = FakeTickerEvent()


class FakeIbkrFeed:
    """One fake connection's reqMktData surface + scripted tick emitter."""

    def __init__(self) -> None:
        self.tickers: dict[str, FakeTicker] = {}
        self.req_made: list[str] = []
        self.cancelled: list[str] = []

    async def qualifyContractsAsync(self, contract: Any) -> list[Any]:
        return [contract]

    def reqMktData(self, contract: Any, *_args: Any) -> FakeTicker:
        symbol = str(getattr(contract, "symbol", "")).upper()
        self.req_made.append(symbol)
        ticker = FakeTicker(symbol)
        self.tickers[symbol] = ticker
        return ticker

    def cancelMktData(self, contract: Any) -> None:
        self.cancelled.append(str(getattr(contract, "symbol", "")).upper())

    def emit(
        self,
        symbol: str,
        *,
        last: float | None = None,
        close: float | None = None,
        high: float | None = None,
        volume: float | None = None,
    ) -> None:
        """Push one L1 update through the real ticks.py handler chain."""
        ticker = self.tickers[symbol.upper()]
        if last is not None:
            ticker.last = last
        if close is not None:
            ticker.close = close
        if high is not None:
            ticker.high = high
        if volume is not None:
            ticker.volume = volume
        ticker.updateEvent.fire(ticker)
