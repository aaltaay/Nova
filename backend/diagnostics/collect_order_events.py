"""Diagnostics row for IBKR order events no Nova order claims (``ibkr.unclaimed``).

Fail when IBKR liquidated a position or a position moved with no fill to explain it this run; warn on
fills sent outside Nova or IBKR errors on orders no Nova order watches; ok otherwise. The evidence
lists the newest events, newest first.
"""
from __future__ import annotations

from typing import Any

from constants_diagnostics import DIAG_GROUP_GATEWAY, DIAG_STATE_FAIL, DIAG_STATE_OK, DIAG_STATE_WARN
from diagnostics.rows import row

_LOUD = ("liquidation", "position_gap")


def unclaimed_rows(*, status: dict[str, Any], now: float) -> list[dict[str, Any]]:
    counts = dict(status.get("counts") or {})
    events = list(status.get("events") or [])
    loud = {kind: counts.get(kind, 0) for kind in _LOUD if counts.get(kind)}
    quiet = {kind: n for kind, n in counts.items() if kind not in _LOUD and n}
    if loud:
        state = DIAG_STATE_FAIL
        detail = ", ".join(f"{n} {kind.replace('_', ' ')}" for kind, n in loud.items())
        cause = ("IBKR changed a position this run without an order Nova sent: a liquidation, or a position "
                 "that moved with no fill to explain it.")
        fix = "Check the account in TWS or Client Portal now; the event log has each one."
    elif quiet:
        state = DIAG_STATE_WARN
        detail = ", ".join(f"{n} {kind.replace('_', ' ')}" for kind, n in quiet.items())
        cause = "IBKR sent fills Nova did not place, or errors on orders no Nova order is watching."
        fix = "Nothing to do if you traded outside Nova; otherwise read the events below."
    else:
        state, detail = DIAG_STATE_OK, "every IBKR fill and order error this run was Nova's"
        cause, fix = "Each fill and order error IBKR sent belonged to an order Nova sent.", "Nothing to do."
    since = min((float(e["ts"]) for e in events if e.get("ts")), default=None)
    return [row(id="ibkr_unclaimed", group=DIAG_GROUP_GATEWAY, title="IBKR events Nova did not send",
                state=state, detail=detail, cause=cause, fix=fix, since=since,
                evidence={"counts": counts, "events": events, "checked_at": now})]
