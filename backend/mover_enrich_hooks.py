"""Post-roster-commit fundamentals warm for the mover tables (ADR 008).

Mirrors ``large_cap_hooks``: ``fetch_fundamentals_batch`` is synchronous
per-symbol network I/O and must never run on the asyncio loop that also serves
HTTP/WS (the same loop ``scanner_hydrate._hydrate_pending`` runs on).

Warming only fills the yfinance cache. ``mover_enrich_view.decorate_rows``
reads it at serialization time, so a frozen table's stored row is never
rewritten by a late fundamentals arrival.

Gappers needs no lease of its own -- premarket Gappers is a filtered projection
of the Gainers roster (ADR 008 amendment 2026-08-24), so warming Gainers
already covers every gapper symbol.
"""
from __future__ import annotations

import logging
import threading

from ibkr import scanner_session as _ss

logger = logging.getLogger(__name__)

_MOVER_TABLES = frozenset({
    _ss.TABLE_GAINERS,
    _ss.TABLE_LOSERS,
    _ss.TABLE_AFTERHOURS,
})


def on_mover_roster_commit(table: str, rows: list[dict]) -> None:
    if table not in _MOVER_TABLES:
        return
    symbols = [r.get("symbol") for r in rows if r.get("symbol")]
    if not symbols:
        return
    threading.Thread(
        target=_warm_fundamentals, args=(symbols,), daemon=True,
        name=f"mover_fundamentals_warm_{table}",
    ).start()


def _warm_fundamentals(symbols: list[str]) -> None:
    try:
        from fundamentals import fetch_fundamentals_batch

        fetch_fundamentals_batch(symbols)
    except Exception:
        logger.exception("mover_enrich_hooks: fundamentals warm failed")
