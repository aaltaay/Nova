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

from constants import IBKR_HOD_SEED_BELOW_PRICE

# IBKR volume-scanner seeds refreshed by hod_momo_seed.seed_refresh_loop.
# List preserves scan rank order (HOT_BY_VOLUME first, then TOP_VOLUME_RATE, …).
_seed_symbols: list[str] = []


def set_seed_symbols(
    symbols: Iterable[str],
    *,
    allow_empty: bool = False,
) -> bool:
    """Replace the volume-seed watch set (called from the seed refresh loop).

    Returns True when the set was updated. Refuses to wipe a non-empty prior
    set with ``[]`` unless ``allow_empty`` is True (transport failures must
    not clear HOD volume seeds).
    """
    global _seed_symbols
    out: list[str] = []
    seen: set[str] = set()
    for s in symbols:
        sym = (s or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    if not out and _seed_symbols and not allow_empty:
        return False
    _seed_symbols = out
    return True


def get_seed_symbols() -> list[str]:
    return list(_seed_symbols)


def _symbols_from_rows(rows: Iterable[dict] | None) -> set[str]:
    out: set[str] = set()
    for row in rows or []:
        sym = (row.get("symbol") or "").strip().upper()
        if sym:
            out.add(sym)
    return out


def _row_change_pct(row: dict) -> float:
    try:
        return float(row.get("change_pct") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _row_price(row: dict) -> float | None:
    for key in ("price", "current_price"):
        raw = row.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def under20_gainer_symbols(
    gainer_rows: Iterable[dict] | None,
    *,
    below_price: float = IBKR_HOD_SEED_BELOW_PRICE,
) -> list[str]:
    """IBKR top-gainer rows under ``below_price``, hottest % first."""
    ranked: list[tuple[float, str]] = []
    seen: set[str] = set()
    cap = float(below_price)
    for row in gainer_rows or []:
        sym = (row.get("symbol") or "").strip().upper()
        if not sym or sym in seen:
            continue
        px = _row_price(row)
        if px is None or px <= 0 or px >= cap:
            continue
        seen.add(sym)
        ranked.append((_row_change_pct(row), sym))
    ranked.sort(key=lambda t: (-t[0], t[1]))
    return [sym for _pct, sym in ranked]


def seed_symbols_for_active(
    volume_seeds: Iterable[str] | None,
    gainer_rows: Iterable[dict] | None = None,
    *,
    below_price: float = IBKR_HOD_SEED_BELOW_PRICE,
) -> list[str]:
    """Seed input for active-set quota: sub-$N table gainers, then volume seeds.

    ``build_active_set`` only takes the *head* of ``seed_symbols`` for reserved
    L1 slots. Pure HOT_BY_VOLUME ordering buried mid-tier Squeeze names (PN /
    BTMD) behind ~150 volume leaders even when they sat on the gainer table.
    """
    out: list[str] = []
    seen: set[str] = set()
    for sym in under20_gainer_symbols(gainer_rows, below_price=below_price):
        if sym not in seen:
            seen.add(sym)
            out.append(sym)
    for raw in volume_seeds or []:
        sym = (raw or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def discovery_for_active(
    universe: Iterable[str] | None,
    gainer_rows: Iterable[dict] | None = None,
) -> list[str]:
    """Discovery order for explore rotation: hottest gainers first, then rest."""
    out: list[str] = []
    seen: set[str] = set()
    ranked: list[tuple[float, str]] = []
    for row in gainer_rows or []:
        sym = (row.get("symbol") or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        ranked.append((_row_change_pct(row), sym))
    ranked.sort(key=lambda t: (-t[0], t[1]))
    for _pct, sym in ranked:
        out.append(sym)
    for raw in universe or []:
        sym = (raw or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
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
