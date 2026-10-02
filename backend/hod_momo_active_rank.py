"""How a scanner row ranks for HOD Momo's active set (ADR 008): pure, no state.

Moved out of ``hod_momo_active`` unchanged (ADR 043 added the hot list's admission there): the bounded
admission keeps the state, these only order rows -- by the size of the move, ties by IB's own scanner
rank, still-unpriced rows by that rank alone.
"""
from __future__ import annotations

from typing import Iterable


def row_score(row: dict) -> float:
    for key in ("change_pct", "gap_percent", "change_abs"):
        val = row.get(key)
        if val is None:
            continue
        try:
            return abs(float(val))
        except (TypeError, ValueError):
            continue
    return 0.0


def ordered_unique(symbols: Iterable[str]) -> list[str]:
    """Preserve first-seen rank order (do not alphabetically sort)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        sym = (raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def row_rank(row: dict) -> float:
    """IB's own scanner rank, or +inf when the row carries none."""
    raw = row.get("rank")
    if raw is None:
        return float("inf")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float("inf")


def ranked_symbols(rows: Iterable[dict] | None) -> list[str]:
    """Rows ranked by magnitude of move, hottest first.

    Ties (most commonly every still-unpriced row, score 0.0) break on IB's
    own scanner rank, not the symbol string -- sorting unpriced rows
    alphabetically is what buried XAIR (IB gainer rank 3) behind BY/CNTB/ECF
    on 2026-08-31 (PROBLEM_LOG). Rank is also the ordering the discovery
    quota (``discovery_candidates``) uses for rows no score has reached yet.
    """
    ranked: list[tuple[float, float, str]] = []
    seen: set[str] = set()
    for row in rows or []:
        sym = (row.get("symbol") or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        ranked.append((row_score(row), row_rank(row), sym))
    ranked.sort(key=lambda t: (-t[0], t[1], t[2]))
    return [sym for _score, _rank, sym in ranked]


def discovery_candidates(rows_lists: Iterable[Iterable[dict] | None]) -> list[str]:
    """Still-unpriced (score 0.0) symbols across every table, IB rank first.

    A row with a real score already competes for a normal round-robin slot
    on merit -- this pool exists only for rows no L1 tick has reached yet,
    which ``row_score`` cannot otherwise distinguish from "legitimately
    quiet" (both score 0.0). IB rank is the only signal that still exists for
    those rows, so it decides discovery order.
    """
    ranked: list[tuple[float, str]] = []
    seen: set[str] = set()
    for rows in rows_lists:
        for row in rows or []:
            sym = (row.get("symbol") or "").strip().upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            if row_score(row) != 0.0:
                continue
            ranked.append((row_rank(row), sym))
    ranked.sort(key=lambda t: (t[0], t[1]))
    return [sym for _rank, sym in ranked]
