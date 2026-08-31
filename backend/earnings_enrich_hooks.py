"""Background yfinance fundamentals warm for the Earnings calendar tab.

Mirrors ``mover_enrich_hooks.py``: ``fetch_fundamentals_batch`` is
synchronous per-symbol network I/O and must run off the request-handling
thread. Single-flight -- a warm already running absorbs new symbols instead
of stacking a second yfinance session pile-up (2026-08 mover incident).

``earnings_calendar.build_earnings_view`` decorates rows from the
fundamentals cache at read time (cache-only, non-blocking); this module only
fills that cache in the background so later polls show company name / sector
/ market cap. Never mutates a Finnhub row directly.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_pending: set[str] = set()
_worker: threading.Thread | None = None


def warm(symbols: list[str] | set[str]) -> None:
    """Queue symbols for a background yfinance fundamentals warm."""
    global _worker
    syms = {s.strip().upper() for s in symbols if s and s.strip()}
    if not syms:
        return
    with _lock:
        _pending.update(syms)
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(
            target=_drain, daemon=True, name="earnings_fundamentals_warm",
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
                # warm() arriving right now cannot see a live-but-exiting
                # worker and drop its symbols on the floor.
                _worker = None
                return
        try:
            fetch_fundamentals_batch(batch)
        except Exception:
            logger.exception(
                "earnings_enrich_hooks: fundamentals warm failed for %d symbol(s)",
                len(batch),
            )


def reset_for_testing() -> None:
    """Test-only: drop pending state without touching the worker thread."""
    global _worker
    with _lock:
        _pending.clear()
        _worker = None
