"""HOD Momo surge buffer seeding from local 1-min bars (never IB historicals).

Warrior Squeeze (Up 5% in 5min / 10% in 10min) needs a rolling price buffer.
Live L1 only starts after a symbol joins the focus universe. If the operator
already paid for today's 1Min series (chart open / warm prefetch), reuse
``bars_store`` so Squeeze can see the trough. Otherwise the buffer builds
live; the Gainers row's change_pct is the admission-leg signal.

This module never calls ``reqHistoricalData``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

from constants import (
    HOD_MOMO_FULL_SESSION_BAR_LIMIT,
    HOD_MOMO_SURGE_SEED_BARS,
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
    """Keep only bars whose 04:00 ET-anchored session matches ``session_key``."""
    out: list[dict] = []
    for bar in bars or []:
        ts = parse_bar_ts(bar.get("t"))
        if ts is None:
            continue
        bar_et = datetime.fromtimestamp(ts, tz=ET)
        if session_key_et(bar_et) == session_key:
            out.append(bar)
    return out


def _read_local_bars(symbol: str, provider: str, limit: int) -> list[dict]:
    """Read bars already on disk. Never schedules an IB fill."""
    prov = (provider or "").strip().lower()
    if prov == "ibkr":
        import bars_store

        stored = bars_store.read(symbol, HOD_MOMO_SURGE_SEED_TIMEFRAME, limit)
        return list((stored or {}).get("bars") or [])

    from bars import fetch_bars

    result = fetch_bars(symbol, HOD_MOMO_SURGE_SEED_TIMEFRAME, limit)
    return list((result or {}).get("bars") or [])


def seed_symbol(symbol: str, provider: str) -> str:
    """Apply a store-only seed. Returns ``store`` or ``live``.

    ``live`` means the local store was empty -- the engine will build the
    surge buffer from post-admission ticks and tick-6 / observed-warmup
    handles the high floor.
    """
    import hod_momo as hm
    import hod_momo_high as _high

    sym = (symbol or "").strip().upper()
    if not sym:
        return "live"

    full_session_bars = filter_bars_to_session(
        _read_local_bars(sym, provider, HOD_MOMO_FULL_SESSION_BAR_LIMIT),
        session_key_et(),
    )
    if not full_session_bars:
        hm.mark_surge_seed_attempted(sym)
        logger.info(
            "HOD Momo surge seed: %s live-only (no local %s bars)",
            sym, HOD_MOMO_SURGE_SEED_TIMEFRAME,
        )
        return "live"

    bars = full_session_bars[-HOD_MOMO_SURGE_SEED_BARS:]
    points = bars_to_surge_points(bars)
    n = hm.seed_price_buffer(sym, points)
    try:
        sh = _high.seed_session_high_from_bars(sym, full_session_bars)
        if sh is not None:
            logger.info(
                "HOD Momo high seed: %s session_high=%.4g from %d store bars",
                sym, sh, len(full_session_bars),
            )
    except Exception as hexc:
        logger.warning("HOD Momo high seed failed for %s: %s", sym, hexc)
    if points:
        logger.info(
            "HOD Momo surge seed: %s +%d buffer pts from %d store %s bars",
            sym, n, len(bars), HOD_MOMO_SURGE_SEED_TIMEFRAME,
        )
        hm.reevaluate_after_surge_seed(sym)
    else:
        hm.mark_surge_seed_attempted(sym)
    return "store"


async def surge_seed_loop(get_provider: Callable[[], str]) -> None:
    """Background task: drain pending seeds from the local bars store."""
    import hod_momo as hm

    while True:
        try:
            await asyncio.sleep(HOD_MOMO_SURGE_SEED_POLL_SEC)
            pending_n = len(hm.get_state().pending_surge_seed)
            if pending_n <= 0:
                continue
            pending = hm.pop_pending_surge_seeds(pending_n)
            if not pending:
                continue
            provider = (get_provider() or "").strip().lower() or "alpaca"
            for sym in pending:
                try:
                    seed_symbol(sym, provider)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "HOD Momo store seed failed for %s: %s -- live-only",
                        sym, exc,
                    )
                    hm.mark_surge_seed_attempted(sym)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HOD Momo surge seed loop error: %s", exc)
