"""HOD Momo surge buffer seeding from recent 1-min bars.

Warrior Squeeze (Up 5% in 5min / 10% in 10min) needs price history spanning the
window. Nova's live path only appends IBKR 1Hz table ticks *after* a symbol
joins the focus universe — first tick → surge:None; after a few flat ticks →
surge≈0 even when the move already happened.

This module fetches recent bars (IBKR when discovery=ibkr) and seeds
``hod_momo``'s rolling price buffer so ``low_to_current`` / ``fixed_start``
surge can see the trough. No silent Alpaca fallback under discovery=ibkr.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

from constants import (
    HOD_MOMO_FULL_SESSION_BAR_LIMIT,
    HOD_MOMO_SURGE_SEED_BARS,
    HOD_MOMO_SURGE_SEED_MAX_PER_TICK,
    HOD_MOMO_SURGE_SEED_POLL_SEC,
    HOD_MOMO_SURGE_SEED_TIMEFRAME,
)
from market import ET, session_key_et

logger = logging.getLogger(__name__)


def parse_bar_ts(raw: object) -> float | None:
    """Parse bar timestamp (ISO ``t`` or unix) to unix seconds."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        ts = float(raw)
        return ts / 1000.0 if ts > 1e12 else ts
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def bars_to_surge_points(bars: list[dict]) -> list[tuple[float, float]]:
    """Convert OHLCV bars into (ts, price) points for the surge buffer.

    Each bar contributes its **low** then **close** (~30s later) so
    ``low_to_current`` surge can see the trough inside the candle.
    """
    points: list[tuple[float, float]] = []
    for bar in bars or []:
        ts = parse_bar_ts(bar.get("t"))
        if ts is None:
            continue
        try:
            low = float(bar["l"])
            close = float(bar["c"])
        except (KeyError, TypeError, ValueError):
            continue
        if low <= 0 or close <= 0:
            continue
        points.append((ts, low))
        points.append((ts + 30.0, close))
    points.sort(key=lambda p: p[0])
    return points


def filter_bars_to_session(bars: list[dict], session_key: str) -> list[dict]:
    """Keep only bars whose 04:00 ET-anchored session matches ``session_key``.

    A ``1 D`` IBKR duration pull can include a sliver of the prior calendar
    day before 04:00 ET; without this filter that stale bar could pollute
    today's session-high seed.
    """
    out: list[dict] = []
    for bar in bars or []:
        ts = parse_bar_ts(bar.get("t"))
        if ts is None:
            continue
        bar_et = datetime.fromtimestamp(ts, tz=ET)
        if session_key_et(bar_et) == session_key:
            out.append(bar)
    return out


async def _fetch_seed_bars(
    symbol: str, provider: str, *, limit: int = HOD_MOMO_SURGE_SEED_BARS,
) -> list[dict]:
    """Fetch recent 1-min bars from the active discovery feed (no silent fallback)."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return []
    prov = (provider or "").strip().lower()
    if prov == "ibkr":
        from ibkr import bars as _ibkr_bars

        result = await _ibkr_bars.fetch_bars_async(
            sym,
            HOD_MOMO_SURGE_SEED_TIMEFRAME,
            limit,
            interactive=False,
        )
        return list(result.get("bars") or [])

    from bars import fetch_bars

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: fetch_bars(sym, HOD_MOMO_SURGE_SEED_TIMEFRAME, limit),
    )
    return list((result or {}).get("bars") or [])


async def surge_seed_loop(get_provider: Callable[[], str]) -> None:
    """Background task: drain pending surge-seed symbols via historical bars."""
    import hod_momo as hm

    while True:
        try:
            await asyncio.sleep(HOD_MOMO_SURGE_SEED_POLL_SEC)
            pending = hm.pop_pending_surge_seeds(HOD_MOMO_SURGE_SEED_MAX_PER_TICK)
            if not pending:
                continue
            provider = (get_provider() or "").strip().lower() or "alpaca"
            for sym in pending:
                try:
                    # One fetch, full current session (04:00 ET forward) —
                    # HOD truth needs the whole session's highs; the 5m/10m
                    # surge buffer only needs the tail. Fetching once and
                    # slicing keeps this on the same historical gate/pacing
                    # queue as before (no extra IBKR request per symbol).
                    full_session_bars = await _fetch_seed_bars(
                        sym, provider, limit=HOD_MOMO_FULL_SESSION_BAR_LIMIT,
                    )
                    full_session_bars = filter_bars_to_session(
                        full_session_bars, session_key_et(),
                    )
                    bars = full_session_bars[-HOD_MOMO_SURGE_SEED_BARS:]
                    points = bars_to_surge_points(bars)
                    n = hm.seed_price_buffer(sym, points)
                    # Full-session bars → session-high seed (max h), not just
                    # the surge tail. Avoids inventing HOD from the first L1
                    # last print after admission, and avoids a falsely-low
                    # floor for a runner whose actual high happened earlier
                    # in the session than the last 15 minutes.
                    try:
                        import hod_momo_high as _high

                        sh = _high.seed_session_high_from_bars(sym, full_session_bars)
                        if sh is not None:
                            logger.info(
                                "HOD Momo high seed: %s session_high=%.4g from %d full-session bars",
                                sym, sh, len(full_session_bars),
                            )
                    except Exception as hexc:
                        logger.warning(
                            "HOD Momo high seed failed for %s: %s", sym, hexc,
                        )
                    if points:
                        logger.info(
                            "HOD Momo surge seed: %s +%d buffer pts from %d %s bars (%s)",
                            sym, n, len(bars), HOD_MOMO_SURGE_SEED_TIMEFRAME, provider,
                        )
                        hm.reevaluate_after_surge_seed(sym)
                    else:
                        logger.warning(
                            "HOD Momo surge seed: %s no usable bars (provider=%s) "
                            "-- giving up for this session (one-shot per symbol)",
                            sym, provider,
                        )
                        hm.mark_surge_seed_attempted(sym)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    hm.mark_surge_seed_attempted(sym)
                    logger.warning("HOD Momo surge seed failed for %s: %s", sym, exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HOD Momo surge seed loop error: %s", exc)
