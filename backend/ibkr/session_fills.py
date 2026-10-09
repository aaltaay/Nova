"""IBKR executions this process has seen, across reconnects, and the positions they explain.

A reconnect builds a new ``IB()``. ib_async reads today's executions back at connect, but as a
request's answer, never as live fills: ``execDetailsEvent`` does not fire for them, so a fill made
while the socket was down reaches no handler. That is the failure Lean's IBKR brokerage hit (issue
249): fills during a disconnect dropped, and a position nobody booked. Nova's handlers never skip a
fill for being "disconnected", but a new session's read-back would still go unheard.

This module remembers which executions Nova has seen -- heard live, or read back -- so a new session
can name the ones it never heard (``take_unheard``), and the positions IBKR last reported with the
executions known when it reported them (``mirror``), so a new session can say whether the fills it
read back explain how each position moved (``explain``). State lives for the process; a new ``IB()``
starts nothing over.
"""
from __future__ import annotations

import logging
import weakref
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

Key = tuple[str, str]  # (account, symbol)

_SEEN_KEEP = 20_000
_seen: dict[str, None] = {}
# (account, symbol) -> (shares, execution ids known when IBKR reported it). None before the first read.
_mirror: dict[Key, tuple[float, frozenset[str]]] | None = None
_wired: "weakref.WeakSet[Any]" = weakref.WeakSet()


def exec_id(fill: Any) -> str:
    return str(getattr(getattr(fill, "execution", None), "execId", "") or "")


def fill_key(fill: Any) -> Key:
    execution = getattr(fill, "execution", None)
    symbol = str(getattr(getattr(fill, "contract", None), "symbol", "") or "").upper()
    return str(getattr(execution, "acctNumber", "") or ""), symbol


def signed_shares(fill: Any) -> float:
    """Shares a fill moved the position by: + bought (``BOT``), - sold (``SLD``)."""
    execution = getattr(fill, "execution", None)
    try:
        shares = abs(float(getattr(execution, "shares", 0) or 0))
    except (TypeError, ValueError):
        return 0.0
    side = str(getattr(execution, "side", "") or "").upper()
    return shares if side in ("BOT", "BUY") else -shares if side in ("SLD", "SELL") else 0.0


def note_heard(fill: Any) -> None:
    """A fill a live handler heard: a new session never calls it unheard."""
    key = exec_id(fill)
    if not key:
        return
    _seen[key] = None
    if len(_seen) > _SEEN_KEEP:
        for stale in list(_seen)[: len(_seen) - _SEEN_KEEP]:
            _seen.pop(stale, None)


def _fills(ib: Any) -> list[Any]:
    fills_fn = getattr(ib, "fills", None)
    if not callable(fills_fn):
        return []
    return list(fills_fn() or [])


def take_unheard(ib: Any) -> list[Any]:
    """The fills ``ib`` holds that no handler heard and no earlier call returned, oldest first.

    They are marked seen as they are returned. Raises what ``ib.fills()`` raises: an unreadable list
    is never "no fills".
    """
    fresh = [fill for fill in _fills(ib) if exec_id(fill) and exec_id(fill) not in _seen]
    for fill in fresh:
        note_heard(fill)
    return sorted(fresh, key=lambda f: str(getattr(getattr(f, "execution", None), "time", "") or ""))


def read_positions(ib: Any) -> dict[Key, float]:
    """IBKR's stock positions now, per (account, symbol). Raises when unreadable: never "flat"."""
    out: dict[Key, float] = {}
    for position in ib.positions():
        contract = getattr(position, "contract", None)
        if str(getattr(contract, "secType", "STK") or "STK") != "STK":
            continue
        key = (str(getattr(position, "account", "") or ""), str(getattr(contract, "symbol", "") or "").upper())
        out[key] = out.get(key, 0.0) + float(getattr(position, "position", 0) or 0)
    return out


def mirror() -> dict[Key, tuple[float, frozenset[str]]] | None:
    return None if _mirror is None else dict(_mirror)


def remember(positions: dict[Key, float], fills: Iterable[Any]) -> None:
    """IBKR's positions, with the executions known when it reported them (all of ``fills``)."""
    global _mirror
    known: dict[Key, set[str]] = {}
    for fill in fills:
        known.setdefault(fill_key(fill), set()).add(exec_id(fill))
    keys = set(positions) | set(known)
    _mirror = {key: (positions.get(key, 0.0), frozenset(known.get(key, set()))) for key in keys}


def _on_position(ib: Any, position: Any) -> None:
    """IBKR moved one position: the mirror takes it, with every execution ``ib`` knows for it now."""
    global _mirror
    try:
        contract = getattr(position, "contract", None)
        if str(getattr(contract, "secType", "STK") or "STK") != "STK":
            return
        key = (str(getattr(position, "account", "") or ""), str(getattr(contract, "symbol", "") or "").upper())
        known = frozenset(exec_id(f) for f in _fills(ib) if fill_key(f) == key)
        if _mirror is None:
            _mirror = {}
        _mirror[key] = (float(getattr(position, "position", 0) or 0), known)
    except Exception:
        logger.exception("IBKR session fills: a position update could not be mirrored")


def wire(ib: Any, on_position: Callable[[Any], None] | None = None) -> None:
    """Follow ``ib``'s position updates (once per ``IB()``); ``on_position(ib)`` runs after each."""
    if ib is None or ib in _wired or not hasattr(ib, "positionEvent"):
        return
    ref = weakref.ref(ib)

    def handler(position: Any) -> None:
        session = ref()
        if session is None:
            return
        _on_position(session, position)
        if on_position is not None:
            try:
                on_position(session)
            except Exception:
                logger.exception("IBKR session fills: the position follow-up failed")

    ib.positionEvent += handler
    _wired.add(ib)


def explain(
    before: dict[Key, tuple[float, frozenset[str]]], after: dict[Key, float], fills: Iterable[Any],
) -> list[dict[str, Any]]:
    """Each position that moved by more than the fills IBKR reported since ``before`` saw it.

    A fill counts for a position when ``before`` did not already know it. What is left over moved with
    no fill to say why: a liquidation IBKR did not report as one, a transfer, or a fill Nova never got.
    """
    fills = list(fills)
    gaps: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        held, known = before.get(key, (0.0, frozenset()))
        by_fills = sum(signed_shares(f) for f in fills if fill_key(f) == key and exec_id(f) not in known)
        now = after.get(key, 0.0)
        unexplained = (now - held) - by_fills
        if abs(unexplained) > 1e-6:
            gaps.append({
                "account": key[0], "symbol": key[1], "before": held, "after": now,
                "by_fills": by_fills, "unexplained": unexplained,
            })
    return gaps


def reset_for_tests() -> None:
    global _mirror
    _seen.clear()
    _mirror = None
    _wired.clear()
