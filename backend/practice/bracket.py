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
* **Closures are events.** The stop filling cancels the targets (one-cancels-
  other, ``PRACTICE_OCO_CANCELLED``); an entry that closes unfilled -- cancelled
  by the operator, refused by the venue at the fill, or expired (at its close, or
  at its own good-for second, #816) -- cancels the exits waiting on it
  (``PRACTICE_PARENT_CANCELLED``). Each is an ordinary
  ``cancelled`` event at the same moment, stamped with the venue as its source,
  so a rewind before it restores the order.
* **Two halves shrink the stop** (#681, #845). A group may hold a stop for every
  share and two targets, one per half (``leg_role`` ``target`` / ``target2``). A
  target's fill shrinks the group's stop by the shares it sold (``shrink_stops``,
  applied with the fill event, so a rewind before the fill puts the stop back)
  and leaves the other target working; a stop the targets have spent is
  cancelled (``PRACTICE_OCO_CANCELLED``). One target for every share -- every
  bracket before #681 -- reads exactly as before: its fill spends the stop. The
  stop never moves: its price is the caller's (a replace) alone.
* **The exit-only pair** (``exit_pair_rows``, #681): the same group for shares
  already held -- no entry, nothing waits -- placed by ``PracticeBroker.place_exit_oco``.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

from constants_practice import (
    PRACTICE_BRACKET_GEOMETRY_CODE,
    PRACTICE_BRACKET_QTY_CODE,
    PRACTICE_GOOD_FOR_EXPIRED_CODE,
    PRACTICE_LEG_PARENT,
    PRACTICE_LEG_STOP,
    PRACTICE_LEG_TARGET,
    PRACTICE_LEG_TARGET2,
    PRACTICE_OCA_GROUP_PREFIX,
    PRACTICE_OCO_CANCELLED_CODE,
    PRACTICE_OCO_CANCELLED_REASON_DEFAULT,
    PRACTICE_OCO_CANCELLED_REASONS,
    PRACTICE_ORDER_STATUS_EXPIRED,
    PRACTICE_ORDER_STATUS_WAITING,
    PRACTICE_PARENT_CANCELLED_CODE,
    PRACTICE_PARENT_CANCELLED_REASON,
    PRACTICE_PARENT_EXPIRED_REASON,
    PRACTICE_PARENT_GOOD_FOR_EXPIRED_REASON,
)

# The ADR 007 source stamped on a close these rules make: the venue itself, never a caller.
CLOSURE_SOURCE = "venue"
TARGET_ROLES = (PRACTICE_LEG_TARGET, PRACTICE_LEG_TARGET2)
EXIT_ROLES = (*TARGET_ROLES, PRACTICE_LEG_STOP)
_EPS = 1e-9

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


def _legs(stop_id: int, stop: float, target_id: int | None, target: float | None, target2_id: int | None,
          target2: float | None, qty: float, target1_qty: float | None) -> list[tuple[int, str, str, Any, Any, float]]:
    """``(id, role, type, limit, trigger, qty)`` for a group: the targets first, then the stop for every share."""
    wanted = []
    second = target2 is not None and target2_id is not None and target1_qty is not None
    if target is not None and target_id is not None:
        first = float(target1_qty) if second else float(qty)
        wanted.append((int(target_id), PRACTICE_LEG_TARGET, "LMT", float(target), None, first))
        if second:
            wanted.append((int(target2_id), PRACTICE_LEG_TARGET2, "LMT", float(target2), None,
                           float(qty) - first))
    wanted.append((int(stop_id), PRACTICE_LEG_STOP, "STP", None, float(stop), float(qty)))
    return wanted


def exit_rows(entry: dict[str, Any], target_id: int | None, stop_id: int, target: float | None,
              stop: float, *, target2_id: int | None = None, target2: float | None = None,
              target1_qty: float | None = None) -> list[dict[str, Any]]:
    """The exits of the bracket whose entry row is ``entry``, as Live's ``bracketOrder`` builds them.

    Each is the entry's row on the reverse side -- the same symbol, TIF, expiry,
    attribution and placement stamps -- at its own price: the take-profit a LMT at
    ``target``, the stop-loss a STP at ``stop``. All wait. A short's bracket may
    leave out its target (ADR 048 1.6): then the stop alone. Two halves (#681): the
    first target sells ``target1_qty``, the second (``target2``) the rest, and the
    stop covers every share.
    """
    parent_id = int(entry["order_id"])
    reverse = "SELL" if str(entry["side"]).upper() == "BUY" else "BUY"
    qty = float(entry["qty"])
    return [
        {**entry, "order_id": oid, "perm_id": oid, "side": reverse, "order_type": typ, "limit_price": limit,
         "stop_price": trigger, "qty": share, "remaining_qty": share, **leg_fields(parent_id, role)}
        for oid, role, typ, limit, trigger, share in _legs(stop_id, stop, target_id, target, target2_id, target2,
                                                            qty, target1_qty)
    ]


def exit_pair_rows(stop_row: dict[str, Any], target_id: int, target: float, *, target2_id: int | None = None,
                   target2: float | None = None, target1_qty: float | None = None) -> list[dict[str, Any]]:
    """An exit-only pair's rows (#681), from its stop's row: one group -- ``oca-<stop id>`` -- with the stop for
    every share and a LMT per half on the same side. Nothing waits: the shares are already held."""
    stop_id = int(stop_row["order_id"])
    group = oca_group(stop_id)
    return [
        {**stop_row, "order_id": oid, "perm_id": oid, "order_type": typ, "limit_price": limit,
         "stop_price": trigger, "qty": share, "remaining_qty": share, "parent_id": None, "oca_group": group,
         "leg_role": role}
        for oid, role, typ, limit, trigger, share in _legs(stop_id, float(stop_row["stop_price"]), target_id,
                                                            target, target2_id, target2, float(stop_row["qty"]),
                                                            target1_qty)
    ]


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
    qty: float, entry: float, target: float | None, stop: float, *, short: bool = False,
    target2: float | None = None, target1_qty: float | None = None,
) -> tuple[str, str] | None:
    """``(reason, code)`` when a bracket's numbers do not hang together, else ``None``.

    The execution door refuses the same shapes with the same words
    (``execution.validate``); the broker repeats it for callers that bypass
    the door. Exits on the wrong side of the entry would fill the moment the
    entry does. Only a short's bracket may leave out its target (ADR 048 1.6).
    """
    if target is None and not short:
        return "a long bracket needs its target", PRACTICE_BRACKET_GEOMETRY_CODE
    try:
        q, e, s = float(qty), float(entry), float(stop)
        t = float(target) if target is not None else None
    except (TypeError, ValueError):
        return "bracket qty and prices must be numbers", PRACTICE_BRACKET_GEOMETRY_CODE
    if not math.isfinite(q) or q <= 0:
        return "bracket qty must be greater than zero", PRACTICE_BRACKET_QTY_CODE
    if not all(math.isfinite(p) and p > 0 for p in (e, s, t if t is not None else e)):
        return "bracket prices must be greater than zero", PRACTICE_BRACKET_GEOMETRY_CODE
    if t is None:
        if e < s:
            return None
        return (f"short bracket needs entry < stop (entry {e}, stop {s})", PRACTICE_BRACKET_GEOMETRY_CODE)
    if not (t < e < s if short else s < e < t):
        need = "target < entry < stop" if short else "stop < entry < target"
        return (
            f"{'short' if short else 'long'} bracket needs {need} (entry {e}, stop {s}, target {t})",
            PRACTICE_BRACKET_GEOMETRY_CODE,
        )
    from execution.exit_oco import halves_error

    halves = halves_error(q, t, target2, target1_qty, short=short)   # the execution door's words (#681)
    if halves is not None:
        return halves[0], PRACTICE_BRACKET_GEOMETRY_CODE
    return None


def open_qty(row: dict[str, Any]) -> float:
    """The shares an order still has to fill."""
    remaining = row.get("remaining_qty")
    if remaining is not None:
        return float(remaining)
    return float(row.get("qty") or 0) - float(row.get("filled_qty") or 0)


def shrink_stops(rows: Iterable[dict[str, Any]], filled: dict[str, Any]) -> None:
    """A target's fill shrinks its group's working stop by the shares it sold (the rows themselves change).

    The stop keeps its price and covers the shares still held. A stop the fill spends -- it held no more than
    the target sold -- is left as it was with nothing open, for ``closures_after_fill`` to cancel at once: a
    one-target bracket's stop reads exactly as before two halves existed.
    """
    group = filled.get("oca_group")
    if not group or filled.get("leg_role") not in TARGET_ROLES:
        return
    sold = float(filled.get("filled_qty") or filled.get("qty") or 0)
    for row in rows:
        if row.get("oca_group") != group or row.get("leg_role") != PRACTICE_LEG_STOP or is_waiting(row):
            continue
        left = open_qty(row) - sold
        if left > _EPS:
            row.update(qty=left, remaining_qty=left)
        else:
            row["remaining_qty"] = 0.0          # spent: cancelled with the fill (one-cancels-other)


def closures_after_fill(rows: Iterable[dict[str, Any]], filled: dict[str, Any]) -> list[Closure]:
    """What a fill closes in its group: the stop's fill, every target; a target's fill, a stop it spent
    (``shrink_stops``) -- never the other target, which still sells its half."""
    group = filled.get("oca_group")
    if not group:
        return []
    oid = int(filled["order_id"])
    role = str(filled.get("leg_role"))
    reason = PRACTICE_OCO_CANCELLED_REASONS.get(role, PRACTICE_OCO_CANCELLED_REASON_DEFAULT)
    out = []
    for row in rows:
        if row.get("oca_group") != group or int(row["order_id"]) == oid:
            continue
        if role in TARGET_ROLES and (row.get("leg_role") in TARGET_ROLES or open_qty(row) > _EPS):
            continue
        out.append((int(row["order_id"]), reason, PRACTICE_OCO_CANCELLED_CODE))
    return out


def closures_after_close(rows: Iterable[dict[str, Any]], closed: dict[str, Any]) -> list[Closure]:
    """What an entry closing unfilled closes: the exits waiting on it."""
    if closed.get("status") == "Filled":
        return []
    reason = PRACTICE_PARENT_CANCELLED_REASON
    if closed.get("status") == PRACTICE_ORDER_STATUS_EXPIRED:
        ran_out = closed.get("reason_code") == PRACTICE_GOOD_FOR_EXPIRED_CODE   # its own good-for second (#816)
        reason = PRACTICE_PARENT_GOOD_FOR_EXPIRED_REASON if ran_out else PRACTICE_PARENT_EXPIRED_REASON
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
