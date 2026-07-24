"""Execution command + receipt models (ADR 007 data contract)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Operation = Literal["place", "bracket", "cancel", "replace"]
Source = Literal[
    "manual",
    "approve",
    "auto_paper",
    "kill",
    "cancel_working",
    "flatten",
    "benchmark",
]


@dataclass(frozen=True)
class ExecutionCommand:
    """Normalized order mutation. All broker spends enter through this shape."""

    operation: Operation
    idempotency_key: str
    source: Source
    symbol: str | None = None
    side: str | None = None
    qty: float | None = None
    order_type: str = "MKT"
    limit_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    entry_price: float | None = None
    outside_rth: bool = False
    order_id: int | None = None
    setup: str | None = None
    shares: int | None = None
    skip_risk: bool = False
    skip_concurrency: bool = False
    reference_price: float | None = None
    client_timing: dict[str, Any] | None = None
    backend_ingress_wall_ns: int | None = None

    def normalized_symbol(self) -> str | None:
        return self.symbol.upper() if self.symbol else None


@dataclass
class StageTimings:
    """Monotonic-ns deltas from request received (backend entry)."""

    received_ns: int
    validation_completed_ns: int | None = None
    persisted_ns: int | None = None
    broker_sent_ns: int | None = None
    broker_ack_ns: int | None = None
    filled_ns: int | None = None

    def ms_from_received(self, mark_ns: int | None) -> float | None:
        if mark_ns is None or mark_ns < self.received_ns:
            return None
        return (mark_ns - self.received_ns) / 1_000_000.0

    def to_dict(self) -> dict[str, float | None]:
        return {
            "validation_ms": self.ms_from_received(self.validation_completed_ns),
            "persisted_ms": self.ms_from_received(self.persisted_ns),
            "broker_sent_ms": self.ms_from_received(self.broker_sent_ns),
            "broker_ack_ms": self.ms_from_received(self.broker_ack_ns),
            "filled_ms": self.ms_from_received(self.filled_ns),
        }


@dataclass
class ExecutionReceipt:
    ok: bool
    execution_id: str
    operation: Operation
    source: Source
    idempotency_key: str
    error: str | None = None
    reason_code: str | None = None
    mode: str | None = None
    symbol: str | None = None
    order_id: int | None = None
    parent_order_id: int | None = None
    target_order_id: int | None = None
    stop_order_id: int | None = None
    broker_status: str | None = None
    duplicate: bool = False
    timings: StageTimings | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.timings is not None:
            d["timings"] = self.timings.to_dict()
            d["timings_ns"] = {
                "received_ns": self.timings.received_ns,
                "validation_completed_ns": self.timings.validation_completed_ns,
                "persisted_ns": self.timings.persisted_ns,
                "broker_sent_ns": self.timings.broker_sent_ns,
                "broker_ack_ns": self.timings.broker_ack_ns,
                "filled_ns": self.timings.filled_ns,
            }
        return d

    def legacy_place_dict(self) -> dict[str, Any]:
        """Shape expected by existing /api/ibkr/order callers."""
        return {
            "ok": self.ok,
            "order_id": self.order_id,
            "error": self.error,
            "mode": self.mode,
            "execution_id": self.execution_id,
            "duplicate": self.duplicate,
            "timings": self.timings.to_dict() if self.timings else None,
            "broker_status": self.broker_status,
            "parent_order_id": self.parent_order_id,
            "target_order_id": self.target_order_id,
            "stop_order_id": self.stop_order_id,
            "measurement": self.payload.get("measurement"),
        }
