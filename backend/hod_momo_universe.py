"""HOD Momo watch universe (ADR 008: current-session displayed union only).

The watch universe mirrors HOD eligibility exactly: current-session Gappers
∪ Gainers ∪ Afterhours ∪ manually curated Former Momo. No IBKR volume seeds,
no open-ticker priority, no Losers — see
``architecture/decisions/008-persistent-ibkr-scanner-rosters.md``.
"""
from __future__ import annotations

from typing import Callable, Iterable


def _symbols_from_rows(rows: Iterable[dict] | None) -> set[str]:
    out: set[str] = set()
    for row in rows or []:
        sym = (row.get("symbol") or "").strip().upper()
        if sym:
            out.add(sym)
    return out


def build_focus_universe(
    *,
    gapper_rows: Iterable[dict] | None = None,
    gainer_rows: Iterable[dict] | None = None,
    afterhours_rows: Iterable[dict] | None = None,
    extra_symbols: Iterable[str] | None = None,
    is_blocked: Callable[[str], bool] | None = None,
) -> set[str]:
    """Return the HOD Momo watch set: Gappers ∪ Gainers ∪ Afterhours ∪ extra
    (Former Momo). Blocked symbols are excluded."""
    blocked = is_blocked or (lambda _s: False)
    out: set[str] = set()
    for rows in (gapper_rows, gainer_rows, afterhours_rows):
        for sym in _symbols_from_rows(rows):
            if not blocked(sym):
                out.add(sym)
    for raw in extra_symbols or []:
        sym = (raw or "").strip().upper()
        if sym and not blocked(sym):
            out.add(sym)
    return out


def chunk_symbols(symbols: Iterable[str], chunk_size: int) -> list[list[str]]:
    """Split symbols into WS subscribe batches (Alpaca payload safety)."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    ordered = sorted({(s or "").strip().upper() for s in symbols if s})
    return [ordered[i : i + chunk_size] for i in range(0, len(ordered), chunk_size)]
