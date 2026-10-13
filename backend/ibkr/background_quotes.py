"""Quotes for a background pass over many names: the live Level 1 lines first, then a budgeted
cold snapshot of the rest, in turns (#891).

HOD Momo's enrichment snapshotted its whole active set (up to 40 names) every 30 s. Off hours IBKR
takes up to ~11 s per 5-name snapshot, so the call ran past the 25 s thread bridge on every pass
since at least 2026-10-10, the bridge cancelled it, and nothing it asked for was ever used. Most of
those names already have a live Level 1 line holding the same price, volume and prior close.

So: a name with a live line is read from it (memory, no request); the rest go to
``ibkr.discovery.snapshot_quotes`` with a budget, at most ``max_names`` a pass, the longest since
their last try first. A name is marked tried whether or not IBKR answered, so one that never
answers moves to the back instead of holding the front every pass.
"""
from __future__ import annotations

import time
from typing import Any, Callable

# When each name was last sent for a snapshot (process memory, pruned to the names asked about).
_tried_at: dict[str, float] = {}


def reset_for_tests() -> None:
    _tried_at.clear()


def streamed(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """The names whose live Level 1 line holds a price: ``{symbol: {price, volume, prev_close, quote_quality}}``.

    A replay desk's quotes are the recording's, never a live pass's, so it reads none.
    """
    from ibkr import ticks
    from sim.mode import is_replay_desk

    if is_replay_desk():
        return {}
    return {sym: row for sym, row in ticks.last_quotes(symbols).items() if row.get("price") is not None}


def snapshot_turn(symbols: list[str], *, now: float, max_names: int) -> list[str]:
    """This pass's names to snapshot: at most ``max_names``, the longest since their last try first."""
    turn = sorted(symbols, key=lambda s: _tried_at.get(s, 0.0))[:max(0, int(max_names))]
    wanted = set(symbols)
    for sym in [s for s in _tried_at if s not in wanted]:
        del _tried_at[sym]
    for sym in turn:
        _tried_at[sym] = now
    return turn


def gather(
    symbols: list[str],
    *,
    run_ibkr: Callable[[Any], Any],
    budget_sec: float,
    max_names: int,
    now: float | None = None,
) -> dict[str, dict[str, Any]]:
    """Live-line quotes for ``symbols``, plus this pass's budgeted snapshot. Blocking: run it off the loop."""
    from ibkr import discovery

    quotes = streamed(symbols)
    turn = snapshot_turn([s for s in symbols if s not in quotes],
                         now=time.time() if now is None else now, max_names=max_names)
    if turn:
        snapped = run_ibkr(discovery.snapshot_quotes(turn, budget_sec=budget_sec)) or {}
        quotes.update({sym: q for sym, q in snapped.items() if sym not in quotes})
    return quotes
