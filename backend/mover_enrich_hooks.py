"""Post-roster-commit fundamentals warm for the mover tables (ADR 008).

Mirrors ``large_cap_hooks`` in spirit: ``fetch_fundamentals_batch`` is
synchronous per-symbol network I/O and must never run on the asyncio loop that
also serves HTTP/WS (the same loop ``scanner_hydrate._hydrate_pending`` runs
on).

Unlike Large Cap -- one table, rare commits -- the mover tables commit often and
there are three of them, so a thread-per-commit pile-up is real: each
``fetch_fundamentals_batch`` opens a yfinance HTTPS session per symbol, and
overlapping warms for a cold cache stacked hundreds of live Yahoo sockets and
threads onto the API process until it stopped accepting connections. So this
hook is **single-flight**: one warm worker at a time, with pending symbols
coalesced into a set that the running worker drains before exiting.

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

_lock = threading.Lock()
_pending: set[str] = set()
_worker: threading.Thread | None = None


def on_mover_roster_commit(table: str, rows: list[dict]) -> None:
    """Queue this table's symbols for a background yfinance warm."""
    global _worker
    if table not in _MOVER_TABLES:
        return
    symbols = {
        sym for sym in (
            (r.get("symbol") or "").strip().upper() for r in rows
        ) if sym
    }
    if not symbols:
        return
    with _lock:
        _pending.update(symbols)
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(
            target=_drain, daemon=True, name="mover_fundamentals_warm",
        )
        _worker.start()


def _drain() -> None:
    """Fetch queued symbols until the queue is empty, one batch at a time."""
    global _worker
    from fundamentals import fetch_fundamentals_batch

    while True:
        with _lock:
            batch = sorted(_pending)
            _pending.clear()
            if not batch:
                # Release the slot under the same lock a producer checks, so a
                # commit arriving right now cannot see a live-but-exiting
                # worker and drop its symbols on the floor.
                _worker = None
                return
        try:
            fetch_fundamentals_batch(batch)
        except Exception:
            logger.exception(
                "mover_enrich_hooks: fundamentals warm failed for %d symbol(s)",
                len(batch),
            )
