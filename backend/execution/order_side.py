"""What an order does to the position: its side and its effect (ADR 048 decision 6).

Every order row, working and closed, on every venue, carries ``position_side`` (``"long"`` |
``"short"`` | null) and ``effect`` (``"opens"`` | ``"closes"`` | null) -- the Orders table's Side
column. They come from Nova's own record, never from a guess:

- a practice row stamps them when it is placed (``practice.order_rules.side_fields``);
- a Live row Nova sent reads its execution row: ``short_entry``, a bracket's legs, and the position
  the door saw when it sent the order (``position_at_send``);
- a Live order placed outside Nova and still working is read against the position now -- the
  position at the time that matters to a working order. A closed one Nova has no record of reads
  null: unknown, and the desk says so.
"""
from __future__ import annotations

from typing import Any

_EPS = 1e-9
Side = tuple[str | None, str | None]


def from_position(row_side: str | None, held: float | None) -> Side:
    """``(position_side, effect)`` of a plain order against the position ``held`` (signed)."""
    side = (row_side or "").strip().upper()
    if held is None or side not in ("BUY", "SELL"):
        return None, None
    if side == "BUY":
        return ("short", "closes") if held < -_EPS else ("long", "opens")
    return ("long", "closes") if held > _EPS else (None, None)


def from_record(payload: dict[str, Any], row_side: str | None, operation: str | None) -> Side:
    """``(position_side, effect)`` of an order row Nova sent, from its execution row."""
    side = (row_side or "").strip().upper()
    if payload.get("short_entry"):
        return ("short", "opens") if side == "SELL" else ("short", "closes")
    if operation == "bracket":
        return ("long", "opens") if side == "BUY" else ("long", "closes")
    held = payload.get("position_at_send")
    return from_position(side, float(held) if isinstance(held, (int, float)) else None)


def held_at_send(venue: str | None, symbol: str | None) -> float | None:
    """The venue's signed position in ``symbol`` as the door sends; None when it cannot be read."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    try:
        if venue in ("paper", "sim"):
            from practice.broker import loaded

            broker = loaded(venue)
            return float(broker.ledger.held_qty(sym)) if broker is not None else 0.0
        from execution.position_checks import position_qty

        return float(position_qty(sym))
    except Exception:  # an unreadable position is recorded as unknown, never as flat
        return None


def fill_from_positions(rows: list[dict[str, Any]], positions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Working rows with no side of their own (placed outside Nova) read the position now.

    ``positions`` None (unreadable) leaves them unknown.
    """
    held: dict[str, float] = {}
    for pos in positions or []:
        sym = str(pos.get("symbol") or "").strip().upper()
        try:
            held[sym] = held.get(sym, 0.0) + float(pos.get("qty") or 0)
        except (TypeError, ValueError):
            continue
    out = []
    for row in rows:
        copy = dict(row)
        if "position_side" not in copy:
            sym = str(copy.get("symbol") or "").strip().upper()
            known = None if positions is None else held.get(sym, 0.0)
            copy["position_side"], copy["effect"] = from_position(copy.get("side"), known)
        out.append(copy)
    return out
