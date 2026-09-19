"""Sim Fill -- place/cancel against the local tape. Never talks to IBKR."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from constants_sim import (
    SIM_MODE_LABEL,
    SIM_STARTING_BUYING_POWER,
    SIM_STARTING_CASH,
    SIM_SYMBOL,
)
from sim import market as _market

logger = logging.getLogger(__name__)

_next_id = 1
_working: dict[int, dict[str, Any]] = {}
_closed: list[dict[str, Any]] = []
_positions: dict[str, dict[str, float]] = {}
_cash = SIM_STARTING_CASH
_realized = 0.0


def reset_for_tests() -> None:
    global _next_id, _cash, _realized
    _next_id = 1
    _working.clear()
    _closed.clear()
    _positions.clear()
    _cash = SIM_STARTING_CASH
    _realized = 0.0


def place(
    symbol: str,
    side: str,
    qty: float,
    order_type: str = "MKT",
    limit_price: float | None = None,
    stop_price: float | None = None,
    outside_rth: bool = False,
    order_id: int | None = None,
) -> dict[str, Any]:
    del stop_price, outside_rth  # always live; trail/stop parked for sim
    sym = (symbol or "").strip().upper() or SIM_SYMBOL
    if sym != SIM_SYMBOL:
        return {
            "ok": False,
            "order_id": None,
            "error": "SIM v1 only serves SIM1",
            "mode": SIM_MODE_LABEL,
            "reason_code": "SIM_SYMBOL",
        }
    side_u = (side or "").upper()
    typ = (order_type or "MKT").upper()
    oid = int(order_id) if order_id is not None else _alloc_id()
    now = _now_iso()
    row = {
        "order_id": oid,
        "perm_id": oid,
        "symbol": sym,
        "side": side_u,
        "qty": float(qty),
        "filled_qty": 0.0,
        "remaining_qty": float(qty),
        "order_type": typ,
        "limit_price": float(limit_price) if limit_price else None,
        "stop_price": None,
        "avg_fill_price": None,
        "outside_rth": True,
        "status": "Submitted",
        "submitted_at": now,
        "updated_at": now,
        "filled_at": None,
        "held_until": None,
        "commission": 0.0,
        "source": "nova",
        "mode": SIM_MODE_LABEL,
        "nova_placed_at": now,
    }
    _working[oid] = row
    if typ == "MKT" or _limit_crosses(row, _market.last()):
        _fill(row, _fill_price(row))
    return {
        "ok": True,
        "order_id": oid,
        "error": None,
        "mode": SIM_MODE_LABEL,
        "nova_placed_at": now,
        "broker_status": row["status"],
    }


def cancel(order_id: int) -> dict[str, Any]:
    row = _working.pop(int(order_id), None)
    if row is None:
        return {"ok": False, "error": f"order {order_id} not open", "verified_gone": True}
    row["status"] = "Cancelled"
    row["updated_at"] = _now_iso()
    row["remaining_qty"] = float(row.get("qty") or 0) - float(row.get("filled_qty") or 0)
    _closed.append(row)
    return {
        "ok": True,
        "error": None,
        "verified_gone": True,
        "mode": SIM_MODE_LABEL,
    }


def replace(
    order_id: int,
    limit_price: float | None = None,
    stop_price: float | None = None,
) -> dict[str, Any]:
    del stop_price
    row = _working.get(int(order_id))
    if row is None:
        return {"ok": False, "error": f"order {order_id} not open"}
    if limit_price is not None:
        row["limit_price"] = float(limit_price)
    row["updated_at"] = _now_iso()
    if row.get("order_type") == "LMT" and _limit_crosses(row, _market.last()):
        _fill(row, float(row.get("limit_price") or _market.last()))
    return {
        "ok": True,
        "order_id": int(order_id),
        "error": None,
        "mode": SIM_MODE_LABEL,
        "nova_placed_at": row.get("submitted_at"),
        "broker_status": row.get("status"),
    }


def open_orders() -> list[dict[str, Any]]:
    return [dict(row) for row in _working.values()]


def closed_orders(limit: int | None = None) -> list[dict[str, Any]]:
    rows = list(reversed(_closed))
    if limit is not None:
        rows = rows[: max(1, int(limit))]
    return rows


def positions() -> list[dict[str, Any]]:
    mark = _market.last()
    out: list[dict[str, Any]] = []
    for sym, pos in _positions.items():
        qty = float(pos.get("qty") or 0)
        if abs(qty) < 1e-9:
            continue
        avg = float(pos.get("avg_cost") or 0)
        out.append({
            "symbol": sym,
            "qty": qty,
            "avg_cost": avg,
            "market_price": mark if sym == SIM_SYMBOL else mark,
            "market_value": round(qty * mark, 4),
            "unrealized_pnl": round((mark - avg) * qty, 4),
            "realized_pnl": float(pos.get("realized") or 0),
        })
    return out


def account_summary() -> dict[str, Any]:
    pos = positions()
    unreal = sum(float(p.get("unrealized_pnl") or 0) for p in pos)
    gpv = sum(abs(float(p.get("market_value") or 0)) for p in pos)
    net = _cash + sum(float(p.get("market_value") or 0) for p in pos)
    return {
        "connected": True,
        "mode": SIM_MODE_LABEL,
        "sim": True,
        "pending": False,
        "NetLiquidation": round(net, 2),
        "TotalCashValue": round(_cash, 2),
        "BuyingPower": round(max(0.0, SIM_STARTING_BUYING_POWER - gpv), 2),
        "UnrealizedPnL": round(unreal, 2),
        "RealizedPnL": round(_realized, 2),
        "GrossPositionValue": round(gpv, 2),
        "account_class": "margin",
        "AccountType": "SIM",
    }


def try_fill_working(last_px: float) -> list[dict[str, Any]]:
    """Match resting limits against the latest tape print. Returns filled rows."""
    filled: list[dict[str, Any]] = []
    for row in list(_working.values()):
        if row.get("order_type") != "LMT":
            continue
        if _limit_crosses(row, last_px):
            _fill(row, float(row.get("limit_price") or last_px))
            filled.append(dict(row))
    return filled


def notify_watch(order_id: int, row: dict[str, Any]) -> None:
    try:
        from execution import telemetry
    except Exception:
        logger.debug("SIM: telemetry import failed", exc_info=True)
        return
    watch = telemetry.watch_order(int(order_id))
    status = str(row.get("status") or "Submitted")
    filled_qty = float(row.get("filled_qty") or 0)
    remaining = float(row.get("remaining_qty") or 0)
    avg = row.get("avg_fill_price")
    watch.note_status(
        status,
        filled=filled_qty,
        remaining=remaining,
        average_fill_price=float(avg) if avg else None,
        perm_id=int(order_id),
        callback_perf_ns=time.perf_counter_ns(),
    )


def _alloc_id() -> int:
    global _next_id
    oid = _next_id
    _next_id += 1
    return oid


def _fill_price(row: dict[str, Any]) -> float:
    if row.get("order_type") == "LMT" and row.get("limit_price"):
        return float(row["limit_price"])
    if (row.get("side") or "").upper() == "BUY":
        return _market.ask()
    return _market.bid()


def _limit_crosses(row: dict[str, Any], last_px: float) -> bool:
    limit = row.get("limit_price")
    if limit is None:
        return False
    limit_f = float(limit)
    if (row.get("side") or "").upper() == "BUY":
        return last_px <= limit_f
    return last_px >= limit_f


def _fill(row: dict[str, Any], price: float) -> None:
    qty = float(row["qty"])
    side = str(row["side"]).upper()
    row["filled_qty"] = qty
    row["remaining_qty"] = 0.0
    row["avg_fill_price"] = float(price)
    row["status"] = "Filled"
    row["filled_at"] = _now_iso()
    row["updated_at"] = row["filled_at"]
    row["held_until"] = None
    _apply_position(str(row["symbol"]), side, qty, float(price))
    _working.pop(int(row["order_id"]), None)
    _closed.append(dict(row))
    notify_watch(int(row["order_id"]), row)


def _apply_position(symbol: str, side: str, qty: float, price: float) -> None:
    global _cash, _realized
    pos = _positions.setdefault(symbol, {"qty": 0.0, "avg_cost": 0.0, "realized": 0.0})
    signed = qty if side == "BUY" else -qty
    cur = float(pos["qty"])
    avg = float(pos["avg_cost"])
    if side == "BUY":
        _cash -= qty * price
        new_qty = cur + qty
        if new_qty > 1e-9:
            pos["avg_cost"] = ((avg * max(cur, 0.0)) + qty * price) / new_qty if cur >= 0 else price
        pos["qty"] = new_qty
        return
    _cash += qty * price
    if cur > 0:
        closed = min(qty, cur)
        pnl = (price - avg) * closed
        _realized += pnl
        pos["realized"] = float(pos["realized"]) + pnl
    pos["qty"] = cur - qty
    if abs(pos["qty"]) < 1e-9:
        pos["qty"] = 0.0
        pos["avg_cost"] = 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
