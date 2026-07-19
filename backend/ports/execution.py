"""Execution port — broker mutations only (ADR 002 + ADR 007)."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ExecutionPort(Protocol):
    """Narrow broker mutation surface. Adapters must not invent paper→live forks."""

    def place(
        self,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "MKT",
        limit_price: float | None = None,
        stop_price: float | None = None,
        outside_rth: bool = False,
        order_id: int | None = None,
    ) -> dict: ...

    def place_bracket(
        self,
        symbol: str,
        side: str,
        qty: int,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> dict: ...

    def cancel(self, order_id: int) -> dict: ...

    def open_orders(self) -> list[dict]: ...
