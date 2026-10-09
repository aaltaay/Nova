"""Nova never reuses an IBKR order id, whatever the Gateway's next valid id says.

IBKR gives each new API session its next valid order id and ib_async counts up from it. Lean's IBKR
brokerage saw that id go backwards after a Gateway restart (issue 242) and reissued ids already used.
Nova keys order watches, in-flight shares and ledger joins by order id, so a reused id would hand one
order's callbacks to another order's row, and the startup sweep could close a row by a stranger's
outcome. Before a session becomes READY, ``raise_floor`` moves ib_async's sequence above every id
Nova's ledger sent to IBKR and every execution the session read back from this client.
"""
from __future__ import annotations

import logging
from typing import Any

from constants_ibkr import IBKR_ORDER_ID_MAX
from execution import store

logger = logging.getLogger(__name__)

# Rows a practice venue (Paper, Sim) wrote carry the practice broker's own ids, which restart at 1.
_LEDGER_MAX_SQL = """
SELECT MAX(order_id), MAX(parent_order_id), MAX(target_order_id), MAX(stop_order_id)
FROM executions
WHERE IFNULL(json_extract(payload_json, '$.venue'), '') NOT IN ('paper', 'sim')
  AND IFNULL(mode, '') != 'sim'
"""


def ledger_max_order_id() -> int:
    """The highest IBKR order id any ledger row names (entry or bracket leg); 0 for an empty ledger."""
    store.init_db()
    conn = store.get_connection()
    try:
        row = conn.execute(_LEDGER_MAX_SQL).fetchone()
    finally:
        conn.close()
    return max((int(v) for v in (row or ()) if v is not None), default=0)


def _session_max_order_id(ib: Any) -> int:
    """The highest order id among this client's executions the session read back."""
    try:
        ours = int(ib.client.clientId)
    except (AttributeError, TypeError, ValueError):
        return 0
    best = 0
    for fill in list(ib.fills() or []):
        execution = getattr(fill, "execution", None)
        try:
            if int(getattr(execution, "clientId", -1)) == ours:
                best = max(best, int(getattr(execution, "orderId", 0) or 0))
        except (TypeError, ValueError):
            continue
    return best


def raise_floor(ib: Any) -> dict[str, Any]:
    """Move ``ib``'s next id above every id Nova used. ``{floor, before, after}``; raises when unreadable."""
    floor = max(ledger_max_order_id(), _session_max_order_id(ib))
    before = getattr(ib.client, "_reqIdSeq", None)
    if floor + 1 > IBKR_ORDER_ID_MAX:
        logger.error("IBKR order ids: Nova's highest id %s leaves no room below IBKR's limit", floor)
        return {"floor": floor, "before": before, "after": before}
    ib.client.updateReqId(floor + 1)
    after = getattr(ib.client, "_reqIdSeq", None)
    if before is not None and after != before:
        logger.warning(
            "IBKR order ids: the Gateway's next id %s is at or below %s, an id Nova already used -- "
            "new orders start at %s (ids are never reused)", before, floor, after,
        )
    return {"floor": floor, "before": before, "after": after}
