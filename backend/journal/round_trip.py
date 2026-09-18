"""Write a journal trade when a Nova-placed symbol position returns to flat."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_SKIP_SOURCES = frozenset({"benchmark", "ib_recovered"})
_PLACE_OPS = frozenset({"place", "bracket"})


@dataclass(frozen=True)
class FillEvent:
    symbol: str
    side: str
    qty: float
    price: float
    ts: float
    execution_id: str
    operation: str = "place"
    source: str = "manual"
    parent_order_id: int | None = None
    setup: str | None = None


@dataclass
class OpenCycle:
    symbol: str
    direction: int
    opened_ts: float
    open_execution_id: str
    parent_order_id: int | None
    operation: str
    setup: str | None
    increase_qty: float = 0.0
    increase_notional: float = 0.0
    decrease_qty: float = 0.0
    decrease_notional: float = 0.0
    net_qty: float = 0.0
    last_execution_id: str = ""
    execution_ids: list[str] = field(default_factory=list)


_open: dict[str, OpenCycle] = {}
_seen: set[tuple[str, str]] = set()


def reset_for_tests() -> None:
    _open.clear()
    _seen.clear()


def open_cycles() -> dict[str, OpenCycle]:
    return _open


def close_key_for(cycle: OpenCycle, close_execution_id: str) -> str:
    symbol = cycle.symbol
    parent = int(cycle.parent_order_id or 0)
    if cycle.operation == "bracket" or parent > 0:
        return f"{symbol}|bracket|{parent}"
    return f"{symbol}|{cycle.open_execution_id}|{close_execution_id}"


def apply_fill(
    event: FillEvent,
    *,
    persist: bool = True,
    record_risk: bool = False,
) -> dict | None:
    """Apply one fill. When net qty hits 0, optionally write a journal row."""
    if not _usable(event):
        return None
    dedup = (event.execution_id, event.side)
    if dedup in _seen:
        return None
    _seen.add(dedup)

    signed = event.qty if event.side == "BUY" else -event.qty
    cycle = _open.get(event.symbol)
    written: dict | None = None
    leftover = 0.0
    leftover_sign = 0

    if cycle is None or cycle.net_qty == 0:
        _open[event.symbol] = _new_cycle(event, signed)
        return None

    same_way = (signed > 0 and cycle.net_qty > 0) or (signed < 0 and cycle.net_qty < 0)
    if same_way:
        _add(cycle, event, abs(signed))
        return None

    close_qty = min(abs(cycle.net_qty), event.qty)
    _reduce(cycle, event, close_qty)
    leftover = event.qty - close_qty
    leftover_sign = 1 if event.side == "BUY" else -1
    if abs(cycle.net_qty) > 1e-9:
        return None

    written = _close_cycle(cycle, event, persist=persist, record_risk=record_risk)
    _open.pop(event.symbol, None)
    if leftover > 1e-9:
        flip = FillEvent(
            symbol=event.symbol,
            side=event.side,
            qty=leftover,
            price=event.price,
            ts=event.ts,
            execution_id=event.execution_id,
            operation=event.operation,
            source=event.source,
            parent_order_id=event.parent_order_id,
            setup=event.setup,
        )
        _seen.discard((event.execution_id, event.side))
        _open[event.symbol] = _new_cycle(flip, leftover_sign * leftover)
        _seen.add((event.execution_id, event.side))
    return written


def rebuild_from_ledger(*, since_ts: float | None = None) -> int:
    """Replay this session's fills into open cycles; persist missing closes."""
    reset_for_tests()
    from execution.closed_blotter import session_start_ts
    from execution.store_facts import list_session_fills

    start = float(since_ts if since_ts is not None else session_start_ts())
    written = 0
    for row in list_session_fills(since_ts=start):
        for event in events_from_ledger_row(row):
            trade = apply_fill(event, persist=True, record_risk=False)
            if trade is not None:
                written += 1
    return written


def notify_watch_filled(watch: object) -> None:
    """Telemetry hook: apply a completed watch fill to the builder."""
    execution_id = str(getattr(watch, "execution_id", "") or "")
    if execution_id:
        from execution.store import get_by_id
        from journal.flatten_close import is_flatten_ledger_row, on_flatten_fill_recorded

        row = get_by_id(execution_id)
        if is_flatten_ledger_row(row):
            on_flatten_fill_recorded(execution_id)
            return
    qty = getattr(watch, "last_filled_qty", None)
    price = getattr(watch, "last_avg_fill", None)
    if not execution_id or qty is None or float(qty) <= 0 or not price:
        return
    from execution.store import get_by_id

    row = get_by_id(execution_id)
    if row is None:
        return
    if str(row.get("operation") or "") == "bracket":
        return
    payload = row.get("payload") or {}
    side = str(getattr(watch, "side", None) or payload.get("side") or "").upper()
    parent_raw = row.get("parent_order_id")
    try:
        parent = int(parent_raw) if parent_raw not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        parent = None
    event = FillEvent(
        symbol=str(row.get("symbol") or "").upper(),
        side=side,
        qty=float(qty),
        price=float(price),
        ts=float(row.get("created_ts") or time.time()),
        execution_id=execution_id,
        operation=str(row.get("operation") or "place"),
        source=str(row.get("source") or ""),
        parent_order_id=parent,
        setup=str(payload.get("setup") or "") or None,
    )
    apply_fill(event, persist=True, record_risk=True)


def events_from_ledger_row(row: dict) -> list[FillEvent]:
    source = str(row.get("source") or "")
    operation = str(row.get("operation") or "")
    if source in _SKIP_SOURCES or operation not in _PLACE_OPS:
        return []
    payload = row.get("payload") or {}
    symbol = str(row.get("symbol") or "").strip().upper()
    qty = _as_float(row.get("filled_qty"))
    price = _as_float(row.get("avg_fill_price"))
    side = str(payload.get("side") or row.get("side") or "").upper()
    if not symbol or qty is None or qty <= 0 or price is None or price <= 0:
        return []
    if side not in ("BUY", "SELL"):
        return []
    parent_raw = row.get("parent_order_id")
    try:
        parent = int(parent_raw) if parent_raw not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        parent = None
    if operation == "bracket":
        from execution.evidence_store import list_for_execution

        evidence_events = _events_from_evidence(
            row, list_for_execution(str(row.get("id") or ""))
        )
        if len(evidence_events) < 2:
            return []
        return evidence_events
    return [
        FillEvent(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            ts=float(row.get("created_ts") or 0.0),
            execution_id=str(row.get("id") or ""),
            operation=operation,
            source=source,
            parent_order_id=parent,
            setup=str(payload.get("setup") or "") or None,
        )
    ]


def _usable(event: FillEvent) -> bool:
    if event.source in _SKIP_SOURCES:
        return False
    if event.operation not in _PLACE_OPS:
        return False
    if event.side not in ("BUY", "SELL"):
        return False
    if not event.symbol or event.qty <= 0 or event.price <= 0:
        return False
    if not event.execution_id:
        return False
    return True


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _new_cycle(event: FillEvent, signed: float) -> OpenCycle:
    qty = abs(signed)
    direction = 1 if signed > 0 else -1
    return OpenCycle(
        symbol=event.symbol,
        direction=direction,
        opened_ts=event.ts,
        open_execution_id=event.execution_id,
        parent_order_id=event.parent_order_id,
        operation=event.operation,
        setup=event.setup,
        increase_qty=qty,
        increase_notional=qty * event.price,
        net_qty=signed,
        last_execution_id=event.execution_id,
        execution_ids=[event.execution_id] if event.execution_id else [],
    )


def _add(cycle: OpenCycle, event: FillEvent, qty: float) -> None:
    cycle.increase_qty += qty
    cycle.increase_notional += qty * event.price
    cycle.net_qty += qty if event.side == "BUY" else -qty
    cycle.last_execution_id = event.execution_id
    _remember_fill(cycle, event.execution_id)


def _reduce(cycle: OpenCycle, event: FillEvent, qty: float) -> None:
    cycle.decrease_qty += qty
    cycle.decrease_notional += qty * event.price
    cycle.net_qty += qty if event.side == "BUY" else -qty
    cycle.last_execution_id = event.execution_id
    _remember_fill(cycle, event.execution_id)


def _remember_fill(cycle: OpenCycle, execution_id: str) -> None:
    if execution_id and execution_id not in cycle.execution_ids:
        cycle.execution_ids.append(execution_id)


def _close_cycle(
    cycle: OpenCycle,
    event: FillEvent,
    *,
    persist: bool,
    record_risk: bool,
) -> dict | None:
    qty = cycle.decrease_qty
    if qty <= 0 or cycle.increase_qty <= 0:
        return None
    from journal.net_pnl import build_close_payload

    _remember_fill(cycle, event.execution_id)
    row = build_close_payload(
        symbol=cycle.symbol,
        setup=cycle.setup,
        side="long" if cycle.direction > 0 else "short",
        qty=int(round(qty)),
        entry_price=cycle.increase_notional / cycle.increase_qty,
        exit_price=cycle.decrease_notional / qty,
        opened_ts=cycle.opened_ts,
        closed_ts=event.ts if event.ts else time.time(),
        close_key=close_key_for(cycle, event.execution_id),
        execution_ids=list(cycle.execution_ids),
        open_execution_id=cycle.open_execution_id,
        close_execution_id=event.execution_id,
    )
    if not persist:
        return row
    from journal.store import get_trade_by_id, record_trade

    trade_id = record_trade(
        symbol=row["symbol"],
        setup=row["setup"],
        side=row["side"],
        qty=row["qty"],
        entry_price=row["entry_price"],
        stop_price=None,
        target_price=None,
        exit_price=row["exit_price"],
        pnl=row["pnl"],
        adherent=None,
        opened_ts=row["opened_ts"],
        closed_ts=row["closed_ts"],
        notes=row["notes"],
        is_mock=False,
        close_key=row["close_key"],
        commission=row.get("commission"),
        fill_ids=row.get("fill_ids"),
    )
    if not trade_id:
        return None
    if record_risk:
        try:
            from strategy import risk as _risk

            _risk.record_trade_result(float(row["pnl"]))
        except Exception:
            logger.exception("journal.round_trip: risk update failed for %s", cycle.symbol)
    stored = get_trade_by_id(trade_id)
    return stored if stored is not None else {**row, "id": trade_id}


def _events_from_evidence(row: dict, fills: list[dict]) -> list[FillEvent]:
    by_side: dict[str, FillEvent] = {}
    payload = row.get("payload") or {}
    symbol = str(row.get("symbol") or "").upper()
    parent_raw = row.get("parent_order_id")
    try:
        parent = int(parent_raw) if parent_raw not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        parent = None
    for item in fills:
        side = str(item.get("evidence_side") or "").upper()
        qty = _as_float(item.get("cumulative_shares")) or _as_float(item.get("shares"))
        price = _as_float(item.get("average_fill_price")) or _as_float(item.get("price"))
        if side not in ("BUY", "SELL") or not qty or qty <= 0 or not price or price <= 0:
            continue
        by_side[side] = FillEvent(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            ts=float(row.get("created_ts") or 0.0),
            execution_id=str(row.get("id") or ""),
            operation="bracket",
            source=str(row.get("source") or ""),
            parent_order_id=parent,
            setup=str(payload.get("setup") or "") or None,
        )
    order = ("BUY", "SELL") if str(payload.get("side") or "").upper() != "SELL" else ("SELL", "BUY")
    return [by_side[side] for side in order if side in by_side]
