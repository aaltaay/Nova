"""Active-set L1 heartbeat — keep quote/eval ages fresh on quiet tapes.

IBKR ``updateEvent`` only notifies quote listeners when last price *changes*.
Illiquid AH names stay subscribed but never call ``note_quote``, so integrity
p95 ages climb to hours while a few movers keep ``last_tick`` green.

This loop refreshes ``note_quote`` / ``note_evaluation`` from the last known
L1 price so integrity ages stay honest on quiet tapes. Quiet-tape strategy
re-eval was removed (amplified cold-start false HOD) — alerts only on real
L1 price / day-high updates.
"""
from __future__ import annotations

import asyncio
import logging
import time

from constants import (
    HOD_MOMO_ACTIVE_HEARTBEAT_SEC,
    HOD_MOMO_ACTIVE_HEARTBEAT_STALE_SEC,
    HOD_MOMO_FUNDAMENTALS_REFRESH_SEC,
    HOD_MOMO_QUIET_REEVAL_ENABLED,
)

logger = logging.getLogger(__name__)

_last_fundamentals_refresh_ts: dict[str, float] = {}


def _cache_prices(symbols: list[str]) -> dict[str, float]:
    """Fallback prices from scanner caches when L1 has never printed a last."""
    from runtime_state import get_runtime_state

    wanted = {s for s in symbols}
    out: dict[str, float] = {}
    state = get_runtime_state()
    for rows in (
        state.gainer_cache,
        state.loser_cache,
        state.gapper_cache,
        state.afterhours_cache,
    ):
        for row in rows or []:
            sym = (row.get("symbol") or "").strip().upper()
            if sym not in wanted or sym in out:
                continue
            px = row.get("price") or row.get("current_price")
            try:
                if px is not None:
                    out[sym] = float(px)
            except (TypeError, ValueError):
                continue
    return out


def _maybe_refresh_fundamentals(sym: str, *, now: float) -> None:
    """Re-queue avg_volume/float/52wk-high for an active symbol on a slow cadence.

    ``evaluate_strategy`` only calls ``mark_needs_fundamentals`` while a field is
    still unknown (None) — once populated it is never re-requested. For a runner
    tracked across multiple sessions (Former Momo list) that leaves avg_volume
    frozen at whatever yfinance reported the first time it was fetched, which can
    be orders of magnitude below today's live average as the squeeze continues.
    Re-queuing here lets fetch_fundamentals()'s own TTL decide whether to refetch.
    """
    import hod_momo_market as _market

    last = _last_fundamentals_refresh_ts.get(sym, 0.0)
    if (now - last) < float(HOD_MOMO_FUNDAMENTALS_REFRESH_SEC):
        return
    _last_fundamentals_refresh_ts[sym] = now
    _market.mark_needs_fundamentals(sym)


async def active_heartbeat_loop() -> None:
    """Heartbeat stale active symbols (age telemetry only — no quiet re-eval)."""
    import hod_momo_active as active
    from ibkr import ticks as _ticks

    if HOD_MOMO_QUIET_REEVAL_ENABLED:
        logger.warning(
            "HOD Momo: HOD_MOMO_QUIET_REEVAL_ENABLED is True but quiet re-eval "
            "was removed — flag is ignored",
        )

    while True:
        try:
            await asyncio.sleep(float(HOD_MOMO_ACTIVE_HEARTBEAT_SEC))
            symbols = active.get_active_symbols()
            if not symbols:
                continue
            now = time.time()
            stale_after = float(HOD_MOMO_ACTIVE_HEARTBEAT_STALE_SEC)
            quotes = _ticks.last_quotes(symbols)
            cache_px = _cache_prices(symbols)
            subscribed = {(s or "").strip().upper() for s in _ticks.subscribed_symbols()}
            for sym in symbols:
                q_age = active.quote_age_sec(sym, now)
                e_age = active.eval_age_sec(sym, now)
                need_quote = q_age is None or q_age >= stale_after
                need_eval = e_age is None or e_age >= stale_after
                _maybe_refresh_fundamentals(sym, now=now)
                if not need_quote and not need_eval:
                    continue
                if (
                    sym not in quotes
                    and sym not in cache_px
                    and sym not in subscribed
                ):
                    continue
                if need_quote:
                    active.note_quote(sym, now)
                if need_eval:
                    active.note_evaluation(sym, now)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("HOD Momo active heartbeat failed")