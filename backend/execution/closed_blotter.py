"""Merge IB closed-order replay with the ADR 007 ledger (Orders Today)."""
from __future__ import annotations

from datetime import datetime, timezone

from constants import (
    IBKR_CLOSED_ORDERS_LIMIT_DEFAULT,
    SESSION_PREMARKET_START_MIN_ET,
)
from constants_ibkr import IBKR_CLOSED_ORDER_STATUSES
from market import ET, session_key_et

_PLACE_OPS = frozenset({"place", "bracket"})


def session_start_ts(now: datetime | None = None) -> float:
    """Unix time of 04:00 ET on the current trading-session date."""
    key = session_key_et(now)
    start = datetime.strptime(key, "%Y-%m-%d").replace(
        tzinfo=ET,
        hour=SESSION_PREMARKET_START_MIN_ET // 60,
        minute=SESSION_PREMARKET_START_MIN_ET % 60,
        second=0,
        microsecond=0,
    )
    return start.timestamp()


def load_session_ledger() -> list[dict]:
    from execution.store_facts import list_session_placed

    return list_session_placed(since_ts=session_start_ts())


def overlay_closed_orders(
    ib_rows: list[dict],
    *,
    ledger_rows: list[dict] | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Heal IB orderId/qty zeros from Nova-placed ledger rows."""
    cap = IBKR_CLOSED_ORDERS_LIMIT_DEFAULT if limit is None else max(1, int(limit))
    ledger = [
        row for row in (ledger_rows if ledger_rows is not None else load_session_ledger())
        if _usable_ledger(row)
    ]
    unused = list(ledger)
    out: list[dict] = []
    for ib in ib_rows:
        match = _take_match(ib, unused)
        if match is None:
            row = dict(ib)
            row["source"] = "ib_recovered"
            out.append(row)
        else:
            out.append(_merge_ib_ledger(ib, match))
    for leftover in unused:
        out.append(_row_from_ledger(leftover))
    out.sort(key=_sort_key, reverse=True)
    return out[:cap]


def _usable_ledger(row: dict) -> bool:
    if str(row.get("source") or "") == "benchmark":
        return False
    if str(row.get("operation") or "") not in _PLACE_OPS:
        return False
    if not str(row.get("symbol") or "").strip():
        return False
    if str(row.get("status") or "") == "filled":
        return True
    return str(row.get("broker_status") or "") in IBKR_CLOSED_ORDER_STATUSES


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ledger_side(row: dict) -> str:
    payload = row.get("payload") or {}
    return str(payload.get("side") or row.get("side") or "").strip().upper()


def _requested_qty_from_ledger(row: dict) -> float | None:
    """Requested size (sent_qty). Never a fill."""
    payload = row.get("payload") or {}
    for key in ("sent_qty", "qty"):
        qty = _as_float(payload.get(key))
        if qty is not None and qty > 0:
            return qty
    filled = _filled_qty_from_ledger(row)
    return filled if filled > 0 else None


def _filled_qty_from_ledger(row: dict) -> float:
    """Real fill size only. sent_qty / limit are never a fill."""
    filled = _as_float(row.get("filled_qty"))
    if filled is not None and filled > 0:
        return filled
    return 0.0


def _commission_from_ledger(row: dict) -> float | None:
    if row.get("commission") is None:
        return None
    return _as_float(row.get("commission"))


def _take_match(ib: dict, unused: list[dict]) -> dict | None:
    perm = _as_int(ib.get("perm_id"))
    if perm > 0:
        for i, led in enumerate(unused):
            if _as_int(led.get("perm_id")) == perm:
                return unused.pop(i)
    oid = _as_int(ib.get("order_id"))
    if oid > 0:
        for i, led in enumerate(unused):
            if _as_int(led.get("order_id")) == oid:
                return unused.pop(i)
        return None
    symbol = str(ib.get("symbol") or "").strip().upper()
    side = str(ib.get("side") or "").strip().upper()
    if not symbol:
        return None
    ranked = [
        (i, led)
        for i, led in enumerate(unused)
        if str(led.get("symbol") or "").strip().upper() == symbol
        and _ledger_side(led) in (side, "")
    ]
    if not ranked:
        return None
    ranked.sort(key=lambda item: float(item[1].get("created_ts") or 0))
    return unused.pop(ranked[0][0])


def _merge_ib_ledger(ib: dict, led: dict) -> dict:
    out = dict(ib)
    led_oid = _as_int(led.get("order_id"))
    if _as_int(out.get("order_id")) <= 0 and led_oid > 0:
        out["order_id"] = led_oid
    perm = _as_int(out.get("perm_id")) or _as_int(led.get("perm_id"))
    out["perm_id"] = perm if perm > 0 else out.get("perm_id")
    req = _requested_qty_from_ledger(led)
    if (_as_float(out.get("qty")) or 0) <= 0 and req:
        out["qty"] = req
    led_filled = _filled_qty_from_ledger(led)
    ib_filled = _as_float(out.get("filled_qty")) or 0.0
    if ib_filled <= 0 and led_filled > 0:
        out["filled_qty"] = led_filled
        out["remaining_qty"] = max(float(out.get("qty") or 0) - led_filled, 0.0)
        avg = _as_float(led.get("avg_fill_price"))
        if out.get("avg_fill_price") in (None, 0, 0.0) and avg:
            out["avg_fill_price"] = avg
    if out.get("commission") in (None, 0, 0.0):
        comm = _commission_from_ledger(led)
        if comm is not None:
            out["commission"] = comm
    if not str(out.get("symbol") or "").strip():
        out["symbol"] = str(led.get("symbol") or "").upper()
    out["source"] = "nova"
    out["execution_id"] = led.get("id")
    return out


def _iso_from_ts(ts: float) -> str | None:
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def _row_from_ledger(led: dict) -> dict:
    payload = led.get("payload") or {}
    qty = _requested_qty_from_ledger(led) or 0.0
    filled = _filled_qty_from_ledger(led)
    side = _ledger_side(led) or "BUY"
    if side not in ("BUY", "SELL"):
        side = "BUY"
    status = str(led.get("broker_status") or "")
    ledger_filled = str(led.get("status") or "") == "filled" and filled > 0
    if ledger_filled:
        status = "Filled"
    elif status not in IBKR_CLOSED_ORDER_STATUSES:
        status = "Filled" if filled > 0 else (status or "Inactive")
    iso = _iso_from_ts(float(led.get("created_ts") or 0))
    perm = _as_int(led.get("perm_id"))
    return {
        "order_id": _as_int(led.get("order_id")),
        "perm_id": perm if perm > 0 else None,
        "symbol": str(led.get("symbol") or "").upper(),
        "side": side,
        "qty": qty,
        "filled_qty": filled,
        "remaining_qty": max(qty - filled, 0.0),
        "order_type": str(payload.get("order_type") or "MKT"),
        "limit_price": payload.get("requested_price"),
        "stop_price": None,
        "avg_fill_price": _as_float(led.get("avg_fill_price")) if filled > 0 else None,
        "outside_rth": False,
        "status": status,
        "submitted_at": iso,
        "updated_at": iso,
        "filled_at": iso if filled > 0 else None,
        "held_until": None,
        "source": "nova",
        "execution_id": led.get("id"),
        "commission": _commission_from_ledger(led),
    }


def _sort_key(row: dict) -> tuple:
    return (
        str(row.get("submitted_at") or ""),
        _as_int(row.get("order_id")),
    )
