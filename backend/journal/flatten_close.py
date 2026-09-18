"""Journal a closed trade from a ledger flatten fill.

Local only: reads execution-ledger qty/price already stored. Never calls IB,
never invents P/L or commissions. Missing fill facts are a no-op.

Trigger: ``on_flatten_fill_recorded`` after a ``source=flatten`` row (executor
or bot flatten) has ``filled_qty`` + ``avg_fill_price``. Desk Close Position
stays ``source=manual`` (ADR 007) and uses the generic round-trip hook.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_FLATTEN_SOURCE = "flatten"
_FLAT_EPS = 1e-9


def is_flatten_ledger_row(row: dict | None) -> bool:
    if not row:
        return False
    if str(row.get("source") or "") == _FLATTEN_SOURCE:
        return True
    key = str(row.get("idempotency_key") or "")
    return key.startswith("flatten:") or key.startswith("bot:flatten:")


def on_flatten_fill_recorded(
    execution_id: str,
    *,
    since_ts: float | None = None,
) -> dict | None:
    """Replay this symbol's ledger fills and journal if the flatten flats it."""
    from execution.closed_blotter import session_start_ts
    from execution.store import get_by_id
    from execution.store_facts import list_session_fills
    from journal.db import init_db as init_journal
    from journal.round_trip import apply_fill, events_from_ledger_row, open_cycles

    exec_id = str(execution_id or "").strip()
    if not exec_id:
        return None
    init_journal()
    row = get_by_id(exec_id)
    if not is_flatten_ledger_row(row) or not _has_fill_facts(row):
        return None
    symbol = str((row or {}).get("symbol") or "").strip().upper()
    if not symbol:
        return None

    start = float(since_ts if since_ts is not None else session_start_ts())
    for prior in list_session_fills(since_ts=start):
        if str(prior.get("id") or "") == exec_id:
            continue
        if str(prior.get("symbol") or "").strip().upper() != symbol:
            continue
        for event in events_from_ledger_row(prior):
            apply_fill(event, persist=True, record_risk=False)

    cycle = open_cycles().get(symbol)
    if cycle is None or abs(float(cycle.net_qty)) < _FLAT_EPS:
        return None

    written = None
    for event in events_from_ledger_row(row):
        trade = apply_fill(event, persist=True, record_risk=True)
        if trade is not None:
            written = trade
    return written


def _has_fill_facts(row: dict | None) -> bool:
    if not row:
        return False
    qty = _as_float(row.get("filled_qty"))
    price = _as_float(row.get("avg_fill_price"))
    return qty is not None and qty > 0 and price is not None and price > 0


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
