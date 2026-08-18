"""IBKR historical pacing budget -- the constraints TWS actually enforces.

Official limits (interactivebrokers.github.io/tws-api/historical_limitations.html):
- 60 historical requests in any 10-minute window
- 6+ requests for the same contract / exchange / tick type within 2 seconds
- identical request repeated within 15 seconds
- 50 simultaneous open historical requests (Nova caps well below that)

This module is a clock + counters. It does not talk to IB.
"""
from __future__ import annotations

import time
from collections import defaultdict

from constants import (
    IBKR_HISTORICAL_IDENTICAL_COOLDOWN_SEC,
    IBKR_HISTORICAL_PACE_MAX,
    IBKR_HISTORICAL_PACE_WINDOW_SEC,
    IBKR_HISTORICAL_SAME_CONTRACT_MAX,
    IBKR_HISTORICAL_SAME_CONTRACT_WINDOW_SEC,
)


class HistoricalPacing:
    """Sliding-window token budget for ``reqHistoricalData`` sends."""

    def __init__(self, now_fn=time.monotonic):
        self._now = now_fn
        self._all: list[float] = []
        self._contract: dict[str, list[float]] = defaultdict(list)
        self._identical: dict[tuple[str, str, str], float] = {}

    def reset(self) -> None:
        self._all.clear()
        self._contract.clear()
        self._identical.clear()

    def _prune(self, now: float) -> None:
        cutoff = now - float(IBKR_HISTORICAL_PACE_WINDOW_SEC)
        self._all = [t for t in self._all if t > cutoff]
        ccut = now - float(IBKR_HISTORICAL_SAME_CONTRACT_WINDOW_SEC)
        for key, times in list(self._contract.items()):
            kept = [t for t in times if t > ccut]
            if kept:
                self._contract[key] = kept
            else:
                del self._contract[key]
        stale = [
            ident
            for ident, ts in self._identical.items()
            if now - ts >= float(IBKR_HISTORICAL_IDENTICAL_COOLDOWN_SEC)
        ]
        for ident in stale:
            del self._identical[ident]

    def wait_seconds(self, symbol: str, timeframe: str, duration: str) -> float:
        """Seconds until a send is legal. 0 means send now."""
        now = float(self._now())
        self._prune(now)
        waits: list[float] = []
        if len(self._all) >= int(IBKR_HISTORICAL_PACE_MAX):
            waits.append(self._all[0] + float(IBKR_HISTORICAL_PACE_WINDOW_SEC) - now)
        contract_times = self._contract.get(symbol.upper(), [])
        if len(contract_times) >= int(IBKR_HISTORICAL_SAME_CONTRACT_MAX):
            waits.append(
                contract_times[0] + float(IBKR_HISTORICAL_SAME_CONTRACT_WINDOW_SEC) - now
            )
        last = self._identical.get((symbol.upper(), timeframe, duration))
        if last is not None:
            waits.append(last + float(IBKR_HISTORICAL_IDENTICAL_COOLDOWN_SEC) - now)
        if not waits:
            return 0.0
        return max(0.0, max(waits))

    def record(self, symbol: str, timeframe: str, duration: str) -> None:
        """Call immediately before the IB send."""
        now = float(self._now())
        self._prune(now)
        self._all.append(now)
        self._contract[symbol.upper()].append(now)
        self._identical[(symbol.upper(), timeframe, duration)] = now
