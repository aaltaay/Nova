"""Brackets on the practice venues (#606 step 1): the order shape Live sends.

Live sends IBKR's bracket (``ibkr.orders.place_bracket_order`` -> ib_async
``bracketOrder``): a LMT entry, a take-profit LMT and a stop-loss STP on the
reverse side, one quantity, TIF and outside-RTH flag on all three, three
consecutive order ids, the exits carrying ``parentId``. IBKR holds the exits
until the entry fills and treats them as one-cancels-other. The practice broker
takes the same shape (``PracticeBroker.place_bracket``) so Paper rehearses what
Live sends. This module holds the rules, pure over ledger rows:

* **Row fields.** Every practice row carries ``parent_id`` / ``oca_group`` /
  ``leg_role``: the entry ``None`` / ``None`` / ``parent``, each exit the entry's
  id / ``oca-<entry id>`` / ``target`` or ``stop``, a plain order ``None`` all
  three (a row written before brackets existed reads the same).
* **Waiting.** An exit rests ``PreSubmitted`` until its entry fills: it holds no
  shares to close and never fills. The ledger wakes it when it applies the
  entry's ``filled`` event -- ``Submitted``, placed at the entry's fill time -- so
  the print that filled the entry never fills an exit, and a Sim rewind before
  that fill puts the exits back to waiting. No new event type: a Paper file
  written before brackets loads unchanged.
* **Closures are events.** One exit filling cancels the other (one-cancels-
  other, ``PRACTICE_OCO_CANCELLED``); an entry that closes unfilled -- cancelled
  by the operator, refused by the venue at the fill, or expired -- cancels the
  exits waiting on it (``PRACTICE_PARENT_CANCELLED``). Each is an ordinary
  ``cancelled`` event at the same moment, stamped with the venue as its source,
  so a rewind before it restores the order.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

from constants_practice import (
    PRACTICE_BRACKET_GEOMETRY_CODE,
    PRACTICE_BRACKET_QTY_CODE,
    PRACTICE_LEG_PARENT,
    PRACTICE_LEG_STOP,
    PRACTICE_LEG_TARGET,
    PRACTICE_OCA_GROUP_PREFIX,
    PRACTICE_OCO_CANCELLED_CODE,
    PRACTICE_OCO_CANCELLED_REASON_DEFAULT,
    PRACTICE_OCO_CANCELLED_REASONS,
    PRACTICE_ORDER_STATUS_EXPIRED,
    PRACTICE_ORDER_STATUS_WAITING,
    PRACTICE_PARENT_CANCELLED_CODE,
    PRACTICE_PARENT_CANCELLED_REASON,
    PRACTICE_PARENT_EXPIRED_REASON,
)

# The ADR 007 source stamped on a close these rules make: the venue itself, never a caller.
CLOSURE_SOURCE = "venue"
EXIT_ROLES = (PRACTICE_LEG_TARGET, PRACTICE_LEG_STOP)

Closure = tuple[int, str, str]  # (order id, reason, code)


def oca_group(parent_id: int) -> str:
    return f"{PRACTICE_OCA_GROUP_PREFIX}{int(parent_id)}"


def plain_fields() -> dict[str, Any]:
    """The bracket fields of an order that is no bracket's leg."""
    return {"parent_id": None, "oca_group": None, "leg_role": None}


def leg_fields(parent_id: int, role: str) -> dict[str, Any]:
    """The bracket fields of one leg of the bracket whose entry is ``parent_id``; an exit waits."""
    if role == PRACTICE_LEG_PARENT:
        return {"parent_id": None, "oca_group": None, "leg_role": role}
    if role not in EXIT_ROLES:
        raise ValueError(f"unknown bracket leg {role!r}")
    return {
        "parent_id": int(parent_id), "oca_group": oca_group(parent_id), "leg_role": role,
        "status": PRACTICE_ORDER_STATUS_WAITING,
    }


def exit_rows(entry: dict[str, Any], target_id: int, stop_id: int, target: float, stop: float) -> list[dict[str, Any]]:
    """The two exits of the bracket whose entry row is ``entry``, as Live's ``bracketOrder`` builds them.

    Each is the entry's row on the reverse side -- the same symbol, quantity,
    TIF, expiry, attribution and placement stamps -- at its own price: the
    take-profit a LMT at ``target``, the stop-loss a STP at ``stop``. Both wait.
    """
    parent_id = int(entry["order_id"])
    reverse = "SELL" if str(entry["side"]).upper() == "BUY" else "BUY"
    legs = []
    for oid, role, typ, limit, trigger in (
        (target_id, PRACTICE_LEG_TARGET, "LMT", float(target), None),
        (stop_id, PRACTICE_LEG_STOP, "STP", None, float(stop)),
    ):
        legs.append({
            **entry, "order_id": int(oid), "perm_id": int(oid), "side": reverse, "order_type": typ,
            "limit_price": limit, "stop_price": trigger, **leg_fields(parent_id, role),
        })
    return legs


def _id(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def is_waiting(row: dict[str, Any]) -> bool:
    """An exit whose entry has not filled: it closes nothing held and never fills."""
    return row.get("parent_id") is not None and row.get("status") == PRACTICE_ORDER_STATUS_WAITING


def waiting_exits(rows: Iterable[dict[str, Any]], parent_id: int) -> list[dict[str, Any]]:
    """The exits in ``rows`` still waiting on the entry ``parent_id`` (the rows themselves, not copies)."""
    return [row for row in rows if _id(row.get("parent_id")) == int(parent_id) and is_waiting(row)]


def shape_error(
    qty: float, entry: float, target: float, stop: float, *, short: bool = False,
) -> tuple[str, str] | None:
    """``(reason, code)`` when a bracket's numbers do not hang together, else ``None``.

    The execution door refuses the same shapes with the same words
    (``execution.validate``); the broker repeats it for callers that bypass
    the door. Exits on the wrong side of the entry would fill the moment the
    entry does.
    """
    try:
        q, e, t, s = float(qty), float(entry), float(target), float(stop)
    except (TypeError, ValueError):
        return "bracket qty and prices must be numbers", PRACTICE_BRACKET_GEOMETRY_CODE
    if not math.isfinite(q) or q <= 0:
        return "bracket qty must be greater than zero", PRACTICE_BRACKET_QTY_CODE
    if not all(math.isfinite(p) and p > 0 for p in (e, t, s)):
        return "bracket prices must be greater than zero", PRACTICE_BRACKET_GEOMETRY_CODE
    if not (t < e < s if short else s < e < t):
        need = "target < entry < stop" if short else "stop < entry < target"
        return (
            f"{'short' if short else 'long'} bracket needs {need} (entry {e}, stop {s}, target {t})",
            PRACTICE_BRACKET_GEOMETRY_CODE,
        )
    return None


def closures_after_fill(rows: Iterable[dict[str, Any]], filled: dict[str, Any]) -> list[Closure]:
    """What a fill closes: the other exit of its one-cancels-other group."""
    group = filled.get("oca_group")
    if not group:
        return []
    oid = int(filled["order_id"])
    reason = PRACTICE_OCO_CANCELLED_REASONS.get(str(filled.get("leg_role")), PRACTICE_OCO_CANCELLED_REASON_DEFAULT)
    return [
        (int(row["order_id"]), reason, PRACTICE_OCO_CANCELLED_CODE)
        for row in rows
        if row.get("oca_group") == group and int(row["order_id"]) != oid
    ]


def closures_after_close(rows: Iterable[dict[str, Any]], closed: dict[str, Any]) -> list[Closure]:
    """What an entry closing unfilled closes: the exits waiting on it."""
    if closed.get("status") == "Filled":
        return []
    expired = closed.get("status") == PRACTICE_ORDER_STATUS_EXPIRED
    reason = PRACTICE_PARENT_EXPIRED_REASON if expired else PRACTICE_PARENT_CANCELLED_REASON
    return [
        (int(row["order_id"]), reason, PRACTICE_PARENT_CANCELLED_CODE)
        for row in waiting_exits(rows, int(closed["order_id"]))
    ]


def closures(rows: Iterable[dict[str, Any]], closed: dict[str, Any]) -> list[Closure]:
    """What closing ``closed`` closes with it, by how it closed."""
    if closed.get("status") == "Filled":
        return closures_after_fill(rows, closed)
    return closures_after_close(rows, closed)


def closed_by_bracket(row: dict[str, Any]) -> bool:
    """A leg these rules closed (one-cancels-other, or its entry closing) -- not a caller's cancel."""
    return row.get("status") == "Cancelled" and row.get("reason_code") in (
        PRACTICE_OCO_CANCELLED_CODE, PRACTICE_PARENT_CANCELLED_CODE,
    )
