"""Net P/L from price gross minus real IBKR CommissionReport dollars.

Never invent a fee from avg_cost - fill. Missing reports leave P/L gross.
Owner: journal.net_pnl. Invalidation: ledger executions.commission.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

GROSS_NOTE = "gross of commissions"
_NET_PREFIX = "net of CommissionReport"


def reported_commission(value: object) -> float | None:
    """Return a stored CommissionReport amount, or None when absent."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sum_reported_commissions(values: list[object]) -> float | None:
    """Sum only real reports. None if nothing was reported (do not treat as $0)."""
    total = 0.0
    found = False
    for raw in values:
        value = reported_commission(raw)
        if value is None:
            continue
        total += value
        found = True
    return total if found else None


def gross_pnl(side: str, qty: float, entry_price: float, exit_price: float) -> float:
    shares = float(qty)
    if str(side).lower() == "short":
        return (float(entry_price) - float(exit_price)) * shares
    return (float(exit_price) - float(entry_price)) * shares


def net_from_gross(gross: float, commission: float | None) -> float:
    """Subtract abs(report) when present. Missing report keeps gross."""
    if commission is None:
        return float(gross)
    return float(gross) - abs(float(commission))


def pnl_note(commission: float | None) -> str:
    if commission is None:
        return GROSS_NOTE
    return f"{_NET_PREFIX} ${abs(float(commission)):.2f}"


def dump_fill_ids(execution_ids: list[str]) -> str:
    cleaned = [str(i).strip() for i in execution_ids if str(i).strip()]
    return json.dumps(cleaned)


def parse_fill_ids(raw: object) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(i).strip() for i in raw if str(i).strip()]
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(i).strip() for i in parsed if str(i).strip()]


def ids_from_close_key(close_key: object) -> list[str]:
    parts = [p for p in str(close_key or "").split("|") if p]
    if len(parts) < 3:
        return []
    if parts[1] == "bracket":
        return []
    return [parts[1], parts[2]]


def fill_ids_of(trade: dict) -> list[str]:
    ids = parse_fill_ids(trade.get("fill_ids"))
    if ids:
        return list(ids)
    return ids_from_close_key(trade.get("close_key"))


def trade_includes_execution(trade: dict, execution_id: str) -> bool:
    exec_id = str(execution_id or "").strip()
    if not exec_id:
        return False
    if exec_id in fill_ids_of(trade):
        return True
    key = str(trade.get("close_key") or "")
    return exec_id in key.split("|")


def commissions_for_execution_ids(execution_ids: list[str]) -> float | None:
    from execution.store import get_by_id

    values: list[object] = []
    for exec_id in execution_ids:
        row = get_by_id(str(exec_id))
        if row is None:
            continue
        values.append(row.get("commission"))
    return sum_reported_commissions(values)


def close_notes(open_execution_id: str, close_execution_id: str, commission: float | None) -> str:
    return (
        f"Nova round trip {open_execution_id} -> {close_execution_id}; "
        f"{pnl_note(commission)}"
    )


def replace_pnl_note(notes: str, commission: float | None) -> str:
    suffix = pnl_note(commission)
    text = str(notes or "").strip()
    if "; " in text:
        head, _tail = text.rsplit("; ", 1)
        return f"{head}; {suffix}"
    if text:
        return f"{text}; {suffix}"
    return suffix


def build_close_payload(
    *,
    symbol: str,
    setup: str | None,
    side: str,
    qty: int,
    entry_price: float,
    exit_price: float,
    opened_ts: float,
    closed_ts: float,
    close_key: str,
    execution_ids: list[str],
    open_execution_id: str,
    close_execution_id: str,
) -> dict:
    """Journal row fields. pnl is net only when a CommissionReport exists."""
    gross = gross_pnl(side, qty, entry_price, exit_price)
    commission = commissions_for_execution_ids(execution_ids)
    return {
        "symbol": symbol,
        "setup": setup,
        "side": side,
        "qty": qty,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pnl": net_from_gross(gross, commission),
        "commission": commission,
        "fill_ids": dump_fill_ids(execution_ids),
        "opened_ts": opened_ts,
        "closed_ts": closed_ts,
        "notes": close_notes(open_execution_id, close_execution_id, commission),
        "is_mock": 0,
        "close_key": close_key,
        "adherent": None,
        "stop_price": None,
        "target_price": None,
        "tags": [],
    }


def apply_reported_commission(execution_id: str, *, adjust_risk: bool = True) -> dict | None:
    """Patch journal P/L when a CommissionReport lands after the close row."""
    exec_id = str(execution_id or "").strip()
    if not exec_id:
        return None
    from execution.store import get_by_id

    row = get_by_id(exec_id)
    if row is None or reported_commission(row.get("commission")) is None:
        return None

    from journal.db import init_db
    from journal.store import get_closed_trades

    init_db()
    updated: dict | None = None
    for trade in get_closed_trades(include_mock=True):
        if not trade_includes_execution(trade, exec_id):
            continue
        patched = _patch_trade_net(trade, exec_id, adjust_risk=adjust_risk)
        if patched is not None:
            updated = patched
    return updated


def _patch_trade_net(trade: dict, execution_id: str, *, adjust_risk: bool) -> dict | None:
    from journal.store import update_trade_net

    ids = fill_ids_of(trade)
    if execution_id not in ids:
        ids.append(execution_id)
    commission = commissions_for_execution_ids(ids)
    if commission is None:
        return None
    try:
        qty = float(trade["qty"])
        entry = float(trade["entry_price"])
        exit_px = float(trade["exit_price"])
    except (TypeError, ValueError, KeyError):
        return None
    if trade.get("exit_price") is None:
        return None
    gross = gross_pnl(str(trade.get("side") or "long"), qty, entry, exit_px)
    pnl = net_from_gross(gross, commission)
    old = trade.get("pnl")
    stored = update_trade_net(
        int(trade["id"]),
        pnl=pnl,
        commission=commission,
        notes=replace_pnl_note(str(trade.get("notes") or ""), commission),
        fill_ids=dump_fill_ids(ids),
    )
    if stored is None:
        return None
    if adjust_risk and old is not None:
        delta = float(pnl) - float(old)
        if abs(delta) > 1e-12:
            try:
                from strategy import risk as _risk

                _risk.record_trade_result(delta)
            except Exception:
                logger.exception(
                    "journal.net_pnl: risk delta failed for trade %s",
                    trade.get("id"),
                )
    return stored
