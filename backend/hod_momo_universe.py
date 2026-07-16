"""HOD Momo trade universe — Warrior-style watch set under feed limits.

Warrior Day Trade Dash scans the full tape for HOD + momentum. Nova cannot
subscribe ~6k IEX symbols (empty tape). Approximation:

- ``focus`` (default): union of Top Gainer/Gapper/Loser/AH caches
  + IBKR volume seeds (HOT_BY_VOLUME / TOP_VOLUME_RATE / MOST_ACTIVE)
  + open ticker-detail symbols.
- ``broad``: full common-stock asset list (legacy; needs SIP / breaks IEX).

See knowledge/obsidian/03-Nova-Decisions/Scanner-Provider-IBKR-Primary.md.
"""
from __future__ import annotations

from typing import Callable, Iterable

# IBKR volume-scanner seeds refreshed by hod_momo_seed.seed_refresh_loop.
# List preserves scan rank order (HOT_BY_VOLUME first, then TOP_VOLUME_RATE, …).
_seed_symbols: list[str] = []


def set_seed_symbols(symbols: Iterable[str]) -> None:
    """Replace the volume-seed watch set (called from the seed refresh loop)."""
    global _seed_symbols
    out: list[str] = []
    seen: set[str] = set()
    for s in symbols:
        sym = (s or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    _seed_symbols = out


def get_seed_symbols() -> list[str]:
    return list(_seed_symbols)


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
    loser_rows: Iterable[dict] | None = None,
    afterhours_rows: Iterable[dict] | None = None,
    detail_symbols: Iterable[str] | None = None,
    extra_symbols: Iterable[str] | None = None,
    is_blocked: Callable[[str], bool] | None = None,
) -> set[str]:
    """Return the HOD Momo watch set (scanners + volume seeds + open details).

    Blocked symbols are excluded from scanner/seed rows, but open detail-panel
    symbols stay subscribed so unblock / quote workflows keep working.
    """
    blocked = is_blocked or (lambda _s: False)
    out: set[str] = set()
    for rows in (gapper_rows, gainer_rows, loser_rows, afterhours_rows):
        for sym in _symbols_from_rows(rows):
            if not blocked(sym):
                out.add(sym)
    for raw in list(extra_symbols or []) + list(get_seed_symbols()):
        sym = (raw or "").strip().upper()
        if sym and not blocked(sym):
            out.add(sym)
    for raw in detail_symbols or []:
        sym = (raw or "").strip().upper()
        if sym:
            out.add(sym)
    return out


def chunk_symbols(symbols: Iterable[str], chunk_size: int) -> list[list[str]]:
    """Split symbols into WS subscribe batches (Alpaca payload safety)."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    ordered = sorted({(s or "").strip().upper() for s in symbols if s})
    return [ordered[i : i + chunk_size] for i in range(0, len(ordered), chunk_size)]
