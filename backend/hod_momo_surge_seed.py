"""HOD Momo surge buffer seeding from local 1-min bars (never IB historicals).

momentum Squeeze (Up 5% in 5min / 10% in 10min) needs a rolling price buffer.
Live L1 only starts after a symbol joins the focus universe. If the operator
already paid for today's 1Min series (chart open / warm prefetch), reuse
``bars_store`` so Squeeze can see the trough. Otherwise the buffer builds
live; the Gainers row's change_pct is the admission-leg signal.

This module never calls ``reqHistoricalData``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
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


def filter_bars_to_recent(
    bars: list[dict], *, now_ts: float, max_age_sec: float,
) -> list[dict]:
    """Keep bars whose timestamp is within ``max_age_sec`` of ``now_ts``.

    Squeeze is last-N-minutes of the latest print. Older store bars cannot
    participate once a newer live tick arrives, and they must not inflate
    the buffer span so integrity thinks a window exists.
    """
    cutoff = float(now_ts) - max(0.0, float(max_age_sec))
    out: list[dict] = []
    for bar in bars or []:
        ts = parse_bar_ts(bar.get("t"))
        if ts is not None and ts >= cutoff:
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


def _apply_seed(sym: str, local_bars: list[dict], session: str) -> str:
    """Apply a completed local read on the state-owning thread."""
    import hod_momo as hm
    import hod_momo_high as _high

    full_session_bars = filter_bars_to_session(local_bars, session)
    if not full_session_bars:
        hm.mark_surge_seed_live(sym)
        logger.info(
            "HOD Momo surge seed: %s live-only (no local %s bars)",
            sym, HOD_MOMO_SURGE_SEED_TIMEFRAME,
        )
        return "live"

    try:
        sh = _high.seed_session_high_from_bars(sym, full_session_bars)
        if sh is not None:
            logger.info(
                "HOD Momo high seed: %s session_high=%.4g from %d store bars",
                sym, sh, len(full_session_bars),
            )
    except Exception as hexc:
        logger.warning("HOD Momo high seed failed for %s: %s", sym, hexc)

    recent = filter_bars_to_recent(
        full_session_bars,
        now_ts=time.time(),
        max_age_sec=float(HOD_MOMO_SURGE_SEED_BARS) * 60.0,
    )
    bars = recent[-HOD_MOMO_SURGE_SEED_BARS:]
    points = bars_to_surge_points(bars)
    if not points:
        hm.mark_surge_seed_stored(sym)
        hm.mark_surge_seed_attempted(sym)
        logger.info(
            "HOD Momo surge seed: %s live-only (store bars older than %ds)",
            sym, HOD_MOMO_SURGE_SEED_BARS * 60,
        )
        return "live"

    hm.mark_surge_seed_stored(sym)
    n = hm.seed_price_buffer(sym, points)
    logger.info(
        "HOD Momo surge seed: %s +%d buffer pts from %d store %s bars",
        sym, n, len(bars), HOD_MOMO_SURGE_SEED_TIMEFRAME,
    )
    hm.reevaluate_after_surge_seed(sym)
    return "store"


def seed_symbol(symbol: str, provider: str) -> str:
    """Synchronous store-only seed for offline callers; the runtime uses ``seed_symbol_async``."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:  # maintainer: allow-swallow no running loop means this offline read is safe
        pass
    else:
        raise RuntimeError("use seed_symbol_async on an event loop")
    sym = (symbol or "").strip().upper()
    if not sym:
        return "live"
    return _apply_seed(sym, _read_local_bars(sym, provider, HOD_MOMO_FULL_SESSION_BAR_LIMIT), session_key_et())


@dataclass(frozen=True)
class _SeedContext:
    state: object
    session: str
    state_session: str
    pending: set[str]

    @classmethod
    def capture(cls) -> _SeedContext:
        import hod_momo as hm

        state = hm.get_state()
        return cls(state, session_key_et(), state.session_date, state.pending_surge_seed)

    def current(self) -> bool:
        import hod_momo as hm

        state = hm.get_state()
        return (state is self.state and state.session_date == self.state_session
                and state.pending_surge_seed is self.pending and session_key_et() == self.session)

    def requeue(self, symbols: list[str]) -> None:
        if self.current():
            self.pending.update(symbols)


async def seed_symbol_async(symbol: str, provider: str, *, context: _SeedContext | None = None) -> str:
    """Read on a worker, then seed only the unchanged state/session on this loop."""
    import hod_momo as hm

    sym = (symbol or "").strip().upper()
    if not sym:
        return "live"
    context = context or _SeedContext.capture()
    try:
        bars = await asyncio.to_thread(_read_local_bars, sym, provider, HOD_MOMO_FULL_SESSION_BAR_LIMIT)
    except asyncio.CancelledError:
        context.requeue([sym])
        raise
    except Exception:
        logger.warning("HOD Momo store seed read failed for %s, retrying live-only", sym, exc_info=True)
        if context.current():
            hm.mark_surge_seed_live(sym)
            return "live"
        return "stale"
    if not context.current():
        return "stale"
    return _apply_seed(sym, bars, context.session)


async def surge_seed_loop(get_provider: Callable[[], str]) -> None:
    """Background task: drain pending seeds from the local bars store."""
    import hod_momo as hm

    while True:
        pending: list[str] = []
        context = None
        try:
            await asyncio.sleep(HOD_MOMO_SURGE_SEED_POLL_SEC)
            pending_n = len(hm.get_state().pending_surge_seed)
            if pending_n <= 0:
                continue
            context = _SeedContext.capture()
            pending = hm.pop_pending_surge_seeds(pending_n)
            if not pending:
                continue
            provider = (get_provider() or "").strip().lower() or "alpaca"
            while pending:
                sym = pending[0]
                try:
                    await seed_symbol_async(sym, provider, context=context)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "HOD Momo store seed failed for %s: %s -- live-only",
                        sym, exc,
                    )
                    if context.current():
                        hm.mark_surge_seed_live(sym)
                pending.pop(0)
        except asyncio.CancelledError:
            if context is not None:
                context.requeue(pending)
            raise
        except Exception as exc:
            logger.warning("HOD Momo surge seed loop error: %s", exc)
            if context is not None:
                context.requeue(pending)
