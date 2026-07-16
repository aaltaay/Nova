"""Scanner discovery / movers ports — no concrete broker SDKs."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DiscoveryPort(Protocol):
    """Premarket / gapper universe discovery for the active price feed."""

    def get_gappers(self) -> list[dict]: ...


@runtime_checkable
class MoversPort(Protocol):
    """Market-hours top gainers / losers for the active price feed."""

    def get_gainers(self) -> list[dict]: ...

    def get_losers(self) -> list[dict]: ...
