"""Sim practice ledger -- place/cancel against the loaded replay. Never talks to IBKR.

Fills follow `sim.fill_model` and are always estimates: each filled row carries
``fill_estimated=True`` and a ``fill_basis`` so the desk can tell a practice fill
from a historical print (architecture/practice-fills.md).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from constants_sim import (
    SIM_MODE_LABEL,
    SIM_ORDER_TYPE_CODE,
    SIM_STARTING_BUYING_POWER,
    SIM_STARTING_CASH,
)
from sim import fill_model, practice

logger = logging.getLogger(__name__)

_next_id = 1
_working: dict[int, dict[str, Any]] = {}
_closed: list[dict[str, Any]] = []
_positions: dict[str, dict[str, float]] = {}
_marks: dict[str, float] = {}
_cash = SIM_STARTING_CASH
_realized = 0.0


def reset_for_tests() -> None:
    global _next_id, _cash, _realized
    _next_id = 1
    _working.clear()
    _closed.clear()
    _positions.clear()
    _marks.clear()
    _cash = SIM_STARTING_CASH
    _realized = 0.0


def _refused(error: str, code: str | None) -> dict[str, Any]:
    return {"ok": False, "order_id": None, "error": error, "mode": SIM_MODE_LABEL, "reason_code": code}


def place(
    symbol: str,
    side: str,
    qty: float,
    order_type: str = "MKT",
    limit_price: float | None = None,
    stop_price: float | None = None,
    outside_rth: bool = False,
    order_id: int | None = None,
    protective: bool = False,
) -> dict[str, Any]:
    """Place a practice order on the loaded replay.

    ``protective`` (flatten / kill) may close an existing position whose replay
    is no longer loaded: a MKT order then fills at the last known mark, so the
    practice desk can always get flat (ADR 018).
    """
    del outside_rth  # a replay has no session gate; practice orders are always live
    sym = (symbol or "").strip().upper()
    side_u = (side or "").upper()
    typ = (order_type or "MKT").upper()
    if typ not in fill_model.SUPPORTED_ORDER_TYPES:
        return _refused("Practice orders support MKT, LMT and STP", SIM_ORDER_TYPE_CODE)
    ok, reason, code = practice.admission(sym)
    at_mark = not ok and protective and typ == "MKT" and _closes_position(sym, side_u, float(qty))
    if not ok and not at_mark:
        return _refused(reason, code)
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
        "limit_price": float(limit_price) if limit_price is not None else None,
        "stop_price": float(stop_price) if stop_price is not None else None,
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
        "placed_ts": practice.playhead_ts(),
        "fill_estimated": True,
        "fill_basis": None,
    }
    _working[oid] = row
    if at_mark:
        avg = float(_positions[sym].get("avg_cost") or 0)
        _fill(row, fill_model.Fill(_marks.get(sym, avg), fill_model.BASIS_LAST_MARK))
    else:
        _try_fill_now(row)
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
    return {"ok": True, "error": None, "verified_gone": True, "mode": SIM_MODE_LABEL}


def replace(
    order_id: int,
    limit_price: float | None = None,
    stop_price: float | None = None,
) -> dict[str, Any]:
    row = _working.get(int(order_id))
    if row is None:
        return {"ok": False, "error": f"order {order_id} not open"}
    if limit_price is not None:
        row["limit_price"] = float(limit_price)
    if stop_price is not None:
        row["stop_price"] = float(stop_price)
    row["updated_at"] = _now_iso()
    row["placed_ts"] = practice.playhead_ts()
    _try_fill_now(row)
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
    out: list[dict[str, Any]] = []
    for sym, pos in _positions.items():
        qty = float(pos.get("qty") or 0)
        if abs(qty) < 1e-9:
            continue
        avg = float(pos.get("avg_cost") or 0)
        mark = _mark(sym, avg)
        out.append({
            "symbol": sym,
            "qty": qty,
            "avg_cost": avg,
            "market_price": mark,
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


def try_fill_working(symbol: str, prints: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Match resting orders for ``symbol`` against later replay prints, oldest first."""
    filled: list[dict[str, Any]] = []
    for ts, price in prints:
        _marks[symbol] = price
        for row in list(_working.values()):
            if row["symbol"] != symbol or ts <= float(row.get("placed_ts") or 0):
                continue
            fill = fill_model.on_print(
                row["side"], row["order_type"], price,
                limit=row.get("limit_price"), stop=row.get("stop_price"),
            )
            if fill is not None:
                _fill(row, fill)
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


def _closes_position(symbol: str, side: str, qty: float) -> bool:
    held = float((_positions.get(symbol) or {}).get("qty") or 0)
    if side == "SELL":
        return held > 1e-9 and qty <= held + 1e-9
    return held < -1e-9 and qty <= -held + 1e-9


def _mark(symbol: str, fallback: float) -> float:
    live = practice.reference(symbol).last
    if live is not None:
        _marks[symbol] = live
        return live
    return _marks.get(symbol, fallback)


def _try_fill_now(row: dict[str, Any]) -> None:
    fill = fill_model.at_placement(
        row["side"], row["order_type"], practice.reference(row["symbol"]),
        limit=row.get("limit_price"), stop=row.get("stop_price"),
    )
    if fill is not None:
        _fill(row, fill)


def _fill(row: dict[str, Any], fill: fill_model.Fill) -> None:
    qty = float(row["qty"])
    row["filled_qty"] = qty
    row["remaining_qty"] = 0.0
    row["avg_fill_price"] = float(fill.price)
    row["fill_basis"] = fill.basis
    row["status"] = "Filled"
    row["filled_at"] = _now_iso()
    row["updated_at"] = row["filled_at"]
    row["held_until"] = None
    _marks[str(row["symbol"])] = float(fill.price)
    _apply_position(str(row["symbol"]), str(row["side"]).upper(), qty, float(fill.price))
    _working.pop(int(row["order_id"]), None)
    _closed.append(dict(row))
    notify_watch(int(row["order_id"]), row)


def _apply_position(symbol: str, side: str, qty: float, price: float) -> None:
    global _cash, _realized
    pos = _positions.setdefault(symbol, {"qty": 0.0, "avg_cost": 0.0, "realized": 0.0})
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
