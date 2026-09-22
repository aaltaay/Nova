"""Merge IB closed-order replay with the ADR 007 ledger (Orders Today).

The execution ledger is one table for every venue, so the overlay is scoped
to the desk's own rows (QA V5 / C18 / C53, 2026-09-22). On Paper and Sim the
practice broker's ledger is the whole truth and nothing is joined or appended
-- four filled Paper orders used to be listed on Sim as "Inactive, filled 0",
and a practice id could join another venue's execution row. On Live only rows
whose ``mode`` stamp matches the Gateway session are eligible. The stamp is
what the send wrote: the venue for a practice send (``sim/execution.py``),
the Gateway port label for an IBKR send (``ibkr.client.account_mode``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from constants import (
    IBKR_CLOSED_ORDERS_LIMIT_DEFAULT,
    SESSION_PREMARKET_START_MIN_ET,
)
from constants_ibkr import IBKR_CLOSED_ORDER_STATUSES
from market import ET, session_key_et

logger = logging.getLogger(__name__)

_PLACE_OPS = frozenset({"place", "bracket"})
_GATEWAY_STAMPS = frozenset({"live", "paper"})
_PRACTICE_PAPER = "paper"
_PRACTICE_SIM = "sim"
# payload.order_type spellings whose requested_price is the limit / the stop.
_LIMIT_TYPES = frozenset({"LMT", "STPLMT", "LIMIT", "STOPLIMIT"})
_STOP_TYPES = frozenset({"STP", "TRAIL", "STOP", "TRAILINGSTOP"})


@dataclass(frozen=True)
class DeskLedger:
    """Which execution-ledger rows belong to the desk right now."""

    practice: bool
    #: The ``mode`` stamp of this desk's rows; None when it cannot be told.
    mode: str | None


def current_desk() -> DeskLedger:
    """The settled venue's ledger scope; Live reads the Gateway session's label."""
    try:
        from sim.mode import is_practice_venue, venue

        if is_practice_venue():
            return DeskLedger(practice=True, mode=venue())
        from ibkr import client as _client

        mode = _client.account_mode()
    except Exception:
        logger.exception("closed_blotter: desk venue unavailable -- no ledger rows joined")
        return DeskLedger(practice=False, mode=None)
    return DeskLedger(practice=False, mode=mode if mode in _GATEWAY_STAMPS else None)


def _practice_paper_stamps() -> set[tuple[int, str]]:
    """(order_id, nova_placed_at) of every Paper practice order, for the legacy-Gateway case.

    On Live over the by-hand paper Gateway (ADR 020) an IBKR send and a Paper
    practice send both stamp ``paper``; a practice row's ``nova_placed_at`` is
    the practice ledger's own stamp, so the pair tells them apart exactly.
    """
    try:
        from practice.broker import for_venue

        ledger = for_venue(_PRACTICE_PAPER).ledger
        rows = [*ledger.working_orders(), *ledger.closed_orders()]
    except Exception:
        logger.exception("closed_blotter: Paper practice ledger unreadable -- paper-stamped rows kept")
        return set()
    return {
        (_as_int(r.get("order_id")), str(r.get("nova_placed_at") or ""))
        for r in rows
        if _as_int(r.get("order_id")) > 0
    }


def ledger_rows_for_desk(rows: list[dict], desk: DeskLedger) -> list[dict]:
    """The execution rows this desk may join or list (none on a practice venue).

    A row with no stamp (older ledgers) stays eligible on Live, as before.
    """
    if desk.practice:
        return []
    practice_stamps: set[tuple[int, str]] | None = None
    out: list[dict] = []
    for row in rows:
        stamp = str(row.get("mode") or "").strip().lower()
        if stamp == _PRACTICE_SIM:
            continue
        if stamp in _GATEWAY_STAMPS and desk.mode is not None and stamp != desk.mode:
            continue
        if stamp == _PRACTICE_PAPER and desk.mode is None:
            continue
        if stamp == _PRACTICE_PAPER and desk.mode == _PRACTICE_PAPER:
            if practice_stamps is None:
                practice_stamps = _practice_paper_stamps()
            placed = str((row.get("payload") or {}).get("nova_placed_at") or "")
            if (_as_int(row.get("order_id")), placed) in practice_stamps:
                continue
        out.append(row)
    return out


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
    from execution.store_facts import list_session_place_overlay

    return list_session_place_overlay(since_ts=session_start_ts())


def overlay_closed_orders(
    ib_rows: list[dict],
    *,
    ledger_rows: list[dict] | None = None,
    limit: int | None = None,
    desk: DeskLedger | None = None,
) -> list[dict]:
    """Heal IB orderId/qty zeros from Nova-placed ledger rows of this desk.

    ``ib_rows`` are the venue broker's closed rows. On a practice venue they
    are the practice ledger's own and come back untouched (capped, newest
    first); ``desk`` defaults to the settled venue (``current_desk``).
    """
    cap = IBKR_CLOSED_ORDERS_LIMIT_DEFAULT if limit is None else max(1, int(limit))
    scope = desk if desk is not None else current_desk()
    if scope.practice:
        rows = [dict(row) for row in ib_rows]
        rows.sort(key=_sort_key, reverse=True)
        return rows[:cap]
    source = ledger_rows if ledger_rows is not None else load_session_ledger()
    ledger = [row for row in ledger_rows_for_desk(source, scope) if _matchable_ledger(row)]
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
        if _closed_ledger(leftover):
            out.append(_row_from_ledger(leftover))
    out.sort(key=_sort_key, reverse=True)
    return out[:cap]


def _place_ledger(row: dict) -> bool:
    if str(row.get("source") or "") == "benchmark":
        return False
    if str(row.get("operation") or "") not in _PLACE_OPS:
        return False
    return bool(str(row.get("symbol") or "").strip())


def _closed_ledger(row: dict) -> bool:
    """Closed leftover: filled or a terminal broker_status. Not working PreSubmitted."""
    if not _place_ledger(row):
        return False
    if str(row.get("status") or "") == "filled":
        return True
    return str(row.get("broker_status") or "") in IBKR_CLOSED_ORDER_STATUSES


def _has_broker_id(row: dict) -> bool:
    return _as_int(row.get("order_id")) > 0 or _as_int(row.get("perm_id")) > 0


def _matchable_ledger(row: dict) -> bool:
    """Join pool: closed rows, or still-PreSubmitted place rows with broker ids."""
    if _closed_ledger(row):
        return True
    return _place_ledger(row) and _has_broker_id(row)


def _usable_ledger(row: dict) -> bool:
    """Closed-only leftover admission. Join uses ``_matchable_ledger``."""
    return _closed_ledger(row)


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
        if _closed_ledger(led)
        and str(led.get("symbol") or "").strip().upper() == symbol
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
    if not str(out.get("submitted_at") or "").strip():
        from execution.nova_placed import ledger_placed_iso

        fallback = ledger_placed_iso(led)
        if fallback:
            out["submitted_at"] = fallback
    out["source"] = "nova"
    out["execution_id"] = led.get("id")
    return out


def _iso_from_ts(ts: float) -> str | None:
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def _leftover_status(led: dict, filled: float) -> str:
    """The row's closed status; a ledger fill is never "Inactive" (V5).

    The execution ledger's own ``filled`` wins unless the broker reported a
    different closed status and no fill size was recorded.
    """
    broker = str(led.get("broker_status") or "")
    closed_by_broker = broker in IBKR_CLOSED_ORDER_STATUSES
    if str(led.get("status") or "") == "filled" and (filled > 0 or not closed_by_broker):
        return "Filled"
    if closed_by_broker:
        return broker
    return "Filled" if filled > 0 else (broker or "Inactive")


def _leftover_prices(payload: dict) -> tuple[float | None, float | None]:
    """(limit, stop) from the one requested price the ledger keeps (C54).

    ``requested_price`` is the limit when there is one, else the stop (for a
    TRAIL, the trail amount): a stop is never shown as a limit.
    """
    kind = str(payload.get("order_type") or "MKT").upper().replace(" ", "").replace("_", "")
    price = _as_float(payload.get("requested_price"))
    if kind in _LIMIT_TYPES:
        return price, None
    if kind in _STOP_TYPES:
        return None, price
    return None, None


def _row_from_ledger(led: dict) -> dict:
    payload = led.get("payload") or {}
    qty = _requested_qty_from_ledger(led) or 0.0
    filled = _filled_qty_from_ledger(led)
    side = _ledger_side(led) or "BUY"
    if side not in ("BUY", "SELL"):
        side = "BUY"
    from execution.nova_placed import ledger_placed_iso

    iso = ledger_placed_iso(led)
    created_iso = _iso_from_ts(float(led.get("created_ts") or 0))
    updated_iso = _iso_from_ts(float(led.get("updated_ts") or 0)) or created_iso
    limit_price, stop_price = _leftover_prices(payload)
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
        "limit_price": limit_price,
        "stop_price": stop_price,
        "avg_fill_price": _as_float(led.get("avg_fill_price")) if filled > 0 else None,
        "outside_rth": False,
        "status": _leftover_status(led, filled),
        "submitted_at": iso,
        "updated_at": updated_iso,
        # The ledger keeps no wall-clock fill time; placement is not one (C54).
        "filled_at": None,
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
