"""Nova's own reference on every Live order (IBKR's ``orderRef``), and the one rule that matches it back.

Owner: the execution row's ``order_ref`` column. ``mint`` derives the reference from the execution id;
``execution.live_send`` writes it to the ledger with the row's ``sent`` stage, before the order leaves,
so an order whose send Nova could not see finish (``SEND_UNKNOWN``), or one a restart cut off, can be
found at IBKR by the reference it carries (``execution.startup_sweep``).

IBKR does not enforce orderRef uniqueness: another API client, TWS or a person can type the same text.
So a reference alone never names an order. ``match`` also needs the symbol, the side and the quantity,
and the permId when both sides know it; more than one order passing all of them is a question for the
operator, never a pick (``ambiguous``).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from constants_ibkr import IBKR_ORDER_REF_ID_CHARS, IBKR_ORDER_REF_PREFIX
from execution import ledger_generation, store

logger = logging.getLogger(__name__)

#: A row whose send was unknown, found at IBKR by its reference (the sweep).
RESOLVED_BY_REF = "SEND_RESOLVED_BY_REF"
#: A row whose send was unknown, settled by the send itself when it finally ended.
FINISHED_LATE = "SEND_FINISHED_LATE"
#: More than one order at IBKR passes the match: the operator decides, Nova never picks.
AMBIGUOUS = "ORDER_REF_AMBIGUOUS"


def mint(execution_id: str) -> str:
    """The reference for ``execution_id``'s order: ``nova-`` and the id's first 16 hex characters."""
    digits = "".join(ch for ch in str(execution_id).lower() if ch in "0123456789abcdef")
    return f"{IBKR_ORDER_REF_PREFIX}{digits[:IBKR_ORDER_REF_ID_CHARS]}"


def is_nova(order_ref: str | None) -> bool:
    return str(order_ref or "").startswith(IBKR_ORDER_REF_PREFIX)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _qty(value: Any) -> float | None:
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class RefMatch:
    """``one`` (``row`` is the order), ``none``, or ``ambiguous`` (``candidates`` lists them)."""

    verdict: Literal["one", "none", "ambiguous"]
    row: dict | None = None
    candidates: tuple[dict, ...] = field(default_factory=tuple)

    def order_ids(self) -> list[int]:
        return [_int(row.get("order_id")) for row in self.candidates]


def match(
    rows: Iterable[dict],
    *,
    order_ref: str,
    symbol: str | None,
    side: str | None,
    qty: float | None,
    perm_id: int | None = None,
) -> RefMatch:
    """The broker order rows (``ibkr.order_rows``) that are this order: ref, symbol, side, quantity and permId.

    The working and closed lists can both carry one order, so rows are counted once per permId (else
    per order id). A quantity Nova does not know (``None``) matches nothing: it is never assumed.
    """
    want_symbol = str(symbol or "").strip().upper()
    want_side = str(side or "").strip().upper()
    want_qty = _qty(qty)
    want_perm = _int(perm_id)
    hits: dict[Any, dict] = {}
    if not order_ref or want_qty is None:
        return RefMatch("none")
    for row in rows:
        if str(row.get("order_ref") or "") != order_ref:
            continue
        if str(row.get("symbol") or "").strip().upper() != want_symbol:
            continue
        if str(row.get("side") or "").strip().upper() != want_side:
            continue
        got_qty = _qty(row.get("qty"))
        if got_qty is None or abs(got_qty - want_qty) > 1e-9:
            continue
        row_perm = _int(row.get("perm_id"))
        if want_perm and row_perm and row_perm != want_perm:
            continue
        hits.setdefault(row_perm or ("order", _int(row.get("order_id"))), row)
    found = tuple(hits.values())
    if not found:
        return RefMatch("none")
    if len(found) > 1:
        return RefMatch("ambiguous", candidates=found)
    return RefMatch("one", row=found[0], candidates=found)


def adopt(
    execution_id: str, *, order_id: int, perm_id: int | None = None, reason_code: str = RESOLVED_BY_REF,
) -> None:
    """Give a row whose send was unknown the order IBKR has for it, and clear the unknown."""
    fields = ["order_id = ?", "reason_code = ?", "error = NULL", "updated_ts = ?"]
    values: list = [int(order_id), reason_code, time.time()]
    if _int(perm_id) > 0:
        fields.append("perm_id = ?")
        values.append(int(perm_id))
    values.append(execution_id)
    store.init_db()
    conn = store.get_connection()
    try:
        conn.execute(f"UPDATE executions SET {', '.join(fields)} WHERE id = ?", values)
        ledger_generation.commit(conn)
    finally:
        conn.close()
    logger.warning("execution: row %s's unknown send is IBKR order %s (%s)", execution_id, order_id, reason_code)
