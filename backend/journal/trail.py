"""Closed-trade / session activity trail (D-046).

Read model over journal.trades + the execution ledger. No writes, no IB
calls, no invented P/L or commissions. Wall-clock stamps only
(created_ts / updated_ts / opened_ts / closed_ts) -- never filled_ns.

Owner: journal.trail. Invalidation: journal trade writes + ledger facts.
"""
from __future__ import annotations

from constants import (
    EXECUTION_METRICS_QUERY_LIMIT,
    JOURNAL_TRAIL_DEFAULT_LIMIT,
)

_SKIP_SOURCES = frozenset({"benchmark", "ib_recovered"})
_KIND_ORDER = {
    "place": 0,
    "flatten": 1,
    "fill": 2,
    "commission": 3,
    "cancel": 4,
    "replace": 5,
    "close": 6,
}


def _as_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_ts(value: object) -> float | None:
    number = _as_float(value)
    if number is None or number <= 0:
        return None
    return number


def _symbol(value: object) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def _payload(row: dict) -> dict:
    raw = row.get("payload")
    return raw if isinstance(raw, dict) else {}


def _command_kind(row: dict) -> str:
    from journal.flatten_close import is_flatten_ledger_row

    if is_flatten_ledger_row(row):
        return "flatten"
    op = str(row.get("operation") or "")
    if op in ("cancel", "replace"):
        return op
    return "place"


def _row_qty(row: dict) -> float | None:
    filled = _as_float(row.get("filled_qty"))
    if filled is not None:
        return filled
    payload = _payload(row)
    return _as_float(payload.get("sent_qty") if payload.get("sent_qty") is not None else payload.get("qty"))


def _base_event(row: dict, *, kind: str, ts: float | None) -> dict:
    payload = _payload(row)
    return {
        "kind": kind,
        "ts": ts,
        "execution_id": str(row.get("id") or "") or None,
        "symbol": _symbol(row.get("symbol")),
        "operation": row.get("operation"),
        "source": row.get("source"),
        "side": str(payload.get("side") or "").upper() or None,
        "qty": _row_qty(row),
        "price": None,
        "commission": None,
        "pnl": None,
        "status": row.get("status"),
        "broker_status": row.get("broker_status"),
        "order_id": row.get("order_id"),
    }


def events_from_ledger_row(row: dict | None) -> list[dict]:
    """Command + fill + stored CommissionReport for one ledger row."""
    if not row:
        return []
    if str(row.get("source") or "") in _SKIP_SOURCES:
        return []
    if not str(row.get("id") or "").strip():
        return []
    created = _as_ts(row.get("created_ts"))
    updated = _as_ts(row.get("updated_ts")) or created
    events = [_base_event(row, kind=_command_kind(row), ts=created)]
    filled = _as_float(row.get("filled_qty"))
    if filled is not None and filled > 0:
        fill = _base_event(row, kind="fill", ts=updated)
        fill["qty"] = filled
        fill["price"] = _as_float(row.get("avg_fill_price"))
        events.append(fill)
    from journal.net_pnl import reported_commission

    commission = reported_commission(row.get("commission"))
    if commission is not None:
        fee = _base_event(row, kind="commission", ts=updated)
        fee["commission"] = commission
        fee["qty"] = filled
        events.append(fee)
    return events


def _sort_events(events: list[dict], fill_ids: list[str] | None = None) -> list[dict]:
    rank = {exec_id: index for index, exec_id in enumerate(fill_ids or [])}
    return sorted(
        events,
        key=lambda event: (
            float(event.get("ts") or 0),
            rank.get(str(event.get("execution_id") or ""), 99),
            _KIND_ORDER.get(str(event.get("kind") or ""), 9),
        ),
    )


def _last_ts(item: dict) -> float:
    stamps = [float(event.get("ts") or 0) for event in item.get("events") or []]
    stamps.append(float(item.get("closed_ts") or 0))
    stamps.append(float(item.get("opened_ts") or 0))
    return max(stamps) if stamps else 0.0


def _pnl_basis(trade: dict) -> str | None:
    notes = str(trade.get("notes") or "")
    if "net of CommissionReport" in notes:
        return "net"
    if "gross of commissions" in notes:
        return "gross"
    return None


def _close_event(trade: dict) -> dict:
    from journal.net_pnl import reported_commission

    return {
        "kind": "close",
        "ts": _as_ts(trade.get("closed_ts")) or _as_ts(trade.get("opened_ts")),
        "execution_id": None,
        "symbol": _symbol(trade.get("symbol")),
        "operation": None,
        "source": "journal",
        "side": trade.get("side"),
        "qty": _as_float(trade.get("qty")),
        "price": _as_float(trade.get("exit_price")),
        "commission": reported_commission(trade.get("commission")),
        "pnl": trade.get("pnl"),
        "status": "closed",
        "broker_status": None,
        "order_id": None,
    }


def cycle_from_trade(trade: dict) -> dict:
    """One closed journal row plus any ledger events named in fill_ids."""
    from execution.store import get_by_id
    from journal.net_pnl import fill_ids_of, reported_commission

    fill_ids = fill_ids_of(trade)
    events: list[dict] = []
    seen: set[str] = set()
    for exec_id in fill_ids:
        if exec_id in seen:
            continue
        seen.add(exec_id)
        events.extend(events_from_ledger_row(get_by_id(exec_id)))
    commission = reported_commission(trade.get("commission"))
    return {
        "id": f"trade:{trade.get('id')}",
        "kind": "closed",
        "trade_id": trade.get("id"),
        "symbol": _symbol(trade.get("symbol")),
        "side": trade.get("side"),
        "qty": _as_float(trade.get("qty")),
        "entry_price": _as_float(trade.get("entry_price")),
        "exit_price": _as_float(trade.get("exit_price")),
        "pnl": trade.get("pnl"),
        "commission": commission,
        "pnl_basis": _pnl_basis(trade),
        "opened_ts": _as_ts(trade.get("opened_ts")),
        "closed_ts": _as_ts(trade.get("closed_ts")),
        "close_key": trade.get("close_key"),
        "notes": trade.get("notes"),
        "events": _sort_events(events, fill_ids) + [_close_event(trade)],
        "fill_ids": fill_ids,
    }


def _open_groups(attached_ids: set[str], *, fetch_limit: int, symbol: str | None) -> list[dict]:
    from execution.store import list_recent

    leftover: dict[str, list[dict]] = {}
    for row in list_recent(fetch_limit):
        exec_id = str(row.get("id") or "")
        if not exec_id or exec_id in attached_ids:
            continue
        if str(row.get("source") or "") in _SKIP_SOURCES:
            continue
        name = _symbol(row.get("symbol"))
        if not name:
            continue
        if symbol and name != symbol:
            continue
        leftover.setdefault(name, []).extend(events_from_ledger_row(row))
    groups: list[dict] = []
    for name, events in leftover.items():
        ordered = _sort_events(events)
        if not ordered:
            continue
        groups.append(
            {
                "id": f"open:{name}",
                "kind": "open",
                "trade_id": None,
                "symbol": name,
                "side": None,
                "qty": None,
                "entry_price": None,
                "exit_price": None,
                "pnl": None,
                "commission": None,
                "pnl_basis": None,
                "opened_ts": ordered[0].get("ts"),
                "closed_ts": None,
                "close_key": None,
                "notes": None,
                "events": ordered,
                "fill_ids": [
                    event["execution_id"]
                    for event in ordered
                    if event.get("execution_id")
                ],
            }
        )
    return groups


def recent_trail(
    *,
    limit: int = JOURNAL_TRAIL_DEFAULT_LIMIT,
    symbol: str | None = None,
    include_mock: bool = False,
) -> dict:
    """Newest-first closed cycles plus unattached session ledger events."""
    from journal.db import init_db
    from journal.store import get_closed_trades

    init_db()
    cap = max(1, min(int(limit), EXECUTION_METRICS_QUERY_LIMIT))
    needle = _symbol(symbol)
    cycles: list[dict] = []
    attached: set[str] = set()
    for trade in get_closed_trades(include_mock=include_mock):
        if needle and _symbol(trade.get("symbol")) != needle:
            continue
        cycle = cycle_from_trade(trade)
        cycles.append(cycle)
        attached.update(str(i) for i in cycle.get("fill_ids") or [])
    fetch = min(EXECUTION_METRICS_QUERY_LIMIT, max(cap * 4, 50))
    items = cycles + _open_groups(attached, fetch_limit=fetch, symbol=needle)
    items.sort(key=_last_ts, reverse=True)
    clipped = items[:cap]
    return {
        "count": len(clipped),
        "includes_mock_data": include_mock,
        "items": clipped,
    }
