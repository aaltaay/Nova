"""Build the execution-ledger reserve payload (forensic snapshot)."""
from __future__ import annotations

from typing import Any

from execution.models import ExecutionCommand
from ibkr import safety as _safety


def _cmd_qty(cmd: ExecutionCommand) -> float | None:
    if cmd.qty is not None:
        return float(cmd.qty)
    if cmd.shares is not None:
        return float(cmd.shares)
    return None


def build_reserve_payload(
    cmd: ExecutionCommand,
    *,
    requested_qty: float | None,
    sent_qty: float | None,
    requested_price: float | None,
    measurement: dict[str, Any],
    forced_one_share: bool,
    venue: str | None = None,
    view_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Snapshot intent vs send, spend gates, and short_entry at reserve time."""
    qty = sent_qty if sent_qty is not None else _cmd_qty(cmd)
    return {
        "setup": cmd.setup,
        "venue": venue,  # resolved execution door, independent of IBKR Gateway label
        "order_type": cmd.order_type,
        "side": (cmd.side or "").upper() or None,
        "qty": qty,
        "requested_qty": requested_qty,
        "sent_qty": sent_qty if sent_qty is not None else qty,
        "forced_one_share": bool(forced_one_share)
        and cmd.operation in ("place", "bracket"),
        "short_entry": bool(cmd.short_entry),
        "intent": getattr(cmd, "intent", None),
        "origin": getattr(cmd, "origin", None),   # who in Nova sent it ("Sent by")
        "target_venue": getattr(cmd, "target_venue", None),   # a kill switch cancel aimed at a venue
        "tif": cmd.tif if cmd.operation in ("place", "bracket") else None,
        "requested_price": requested_price,
        "reference_price": (
            cmd.reference_price
            if cmd.reference_price is not None
            else requested_price
        ),
        "orders_enabled": bool(_safety.orders_enabled()),
        "live_trading_confirmed": bool(_safety.live_trading_confirmed()),
        "short_enabled": bool(_safety.short_enabled()),
        "gateway_mode": _safety.gateway_mode(),
        "measurement": measurement,
        # ADR 045: what the operator's screen showed, and the gate's measures of it.
        "view": getattr(cmd, "view", None),
        "view_check": view_check,
    }
