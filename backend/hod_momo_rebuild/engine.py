"""The real HOD Momo engine over a rebuilt day's ticks, on the replay clock.

One fresh engine per build, with the operator's own strategy settings and blocklist (read, never written) and
nothing else of today's: no alerts, no highs, no cooldowns. Every HOD Momo save is switched off for the run
(``no_saves``): the engine saves session highs as it raises them, and the live desk's files are not this replay's.
The clock is pinned to each tick's time (``hod_momo_replay.pinned_clock``), so pace RVOL, the session-dependent
gates, cooldowns and consolidation run on the day's time.

A stock is primed when it first gets an L1 line, the way production seeds a new name: its session-high floor
from the minute bars closed by then and its prior close, its surge buffer from those bars, and a snapshot with
its prior close, float, average volume and 52-week high (``daily``). Change is measured from the prior close on
every tick; the gap exists from 09:30, from the day's open, as IBKR's open tick does.

The float is SEC shares outstanding filed before the day: an upper bound, which proves a float under a max-float
line and can never prove one over a floor. So every strategy with a min-float line sits out the run
(``floor_unproven``): live, a float it cannot judge is ``float:unknown`` and the strategy does not fire.
"""
from __future__ import annotations

import contextlib
import dataclasses
import heapq
import logging
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, time as time_cls
from typing import Any

import hod_momo as hm
import hod_momo_high as _high
import hod_momo_market as _market
from hod_momo_replay import ReplayClock, flush_due, pinned_clock, quiet_trade_log, reset_engine_state
from hod_momo_rebuild.daily import Facts
from hod_momo_rebuild.ticks import SymbolDay
from hod_momo_state import HodMomoState
from hod_momo_surge_seed import bars_to_surge_points
from leaderboard.rows import ET

logger = logging.getLogger(__name__)
_REGULAR_OPEN = time_cls(9, 30)


class Cancelled(Exception):
    """The build was asked to stop."""


@contextlib.contextmanager
def no_saves() -> Iterator[None]:
    """Every HOD Momo save is a no-op inside: the replay never writes the live desk's HOD files. The writer thread's
    hand-offs (``submit``, ``submit_alerts``, ``submit_highs``) are no-ops too, so nothing the replay queued can run
    after the real save functions are back."""
    import cache
    import cache_snapshots
    import hod_momo_writer

    patched: list[tuple[Any, str, Any]] = []
    for module in (cache, cache_snapshots):
        for name in dir(module):
            if name.startswith("save_hod_momo"):
                patched.append((module, name, getattr(module, name)))
    for name in ("submit", "submit_alerts", "submit_highs"):
        patched.append((hod_momo_writer, name, getattr(hod_momo_writer, name)))
    for module, name, _orig in patched:
        setattr(module, name, lambda *a, **k: None)
    try:
        yield
    finally:
        for module, name, orig in patched:
            setattr(module, name, orig)


def fresh_engine() -> HodMomoState:
    """The replay harness's fresh engine (``hod_momo_replay.reset_engine_state``: the operator's strategy settings,
    nothing of today's) plus the operator's blocklist, which live HOD Momo honours; call inside ``no_saves``."""
    import cache

    reset_engine_state()
    state = hm.get_state()
    state.blocklist = {s.upper() for s in cache.load_hod_momo_blocklist()}
    return state


def config_digest() -> str:
    """What decides an alert in the operator's settings: the master gate, the strategies (as the API serves them)
    and the blocklist."""
    import hashlib
    import json

    payload = {**hm.get_configs(), "blocklist": sorted(hm.get_state().blocklist)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class EngineResult:
    alerts: list[dict] = field(default_factory=list)
    ticks: int = 0
    primed: int = 0
    gate_counters: dict[str, int] = field(default_factory=dict)
    pending_unflushed: int = 0
    config: str = ""                       # ``config_digest`` of the settings the engine ran with
    floor_unproven: list[int] = field(default_factory=list)   # strategies with a min-float line, sat out


@contextlib.contextmanager
def floors_sat_out(state: HodMomoState) -> Iterator[list[int]]:
    """Inside, every enabled strategy with a min-float line is off; yields their ids. Their settings are put back
    after, so nothing outside the run (a test's engine, ``config_digest``) sees them changed."""
    held = {sid: cfg for sid, cfg in state.configs.items() if cfg.enabled and float(cfg.min_float or 0) > 0}
    for sid, cfg in held.items():
        state.configs[sid] = dataclasses.replace(cfg, enabled=False)
    try:
        yield sorted(int(sid) for sid in held)
    finally:
        state.configs.update(held)


def _prime(symbol: str, day: SymbolDay, at: float, prev_close: float | None, facts: Facts) -> None:
    closed = [b for b in day.bars if b[0] + 60 <= at]
    seeds = [b[2] for b in closed]
    if prev_close:
        seeds.append(prev_close)
    if seeds:
        _high.apply_session_high(symbol, float(max(seeds)), source="bars")
    if closed:
        _market.seed_price_buffer(symbol, bars_to_surge_points([{"t": b[0], "l": b[3], "c": b[4]} for b in closed]))
    _market.mark_surge_seed_attempted(symbol)
    hm.update_ticker_snapshot(
        symbol,
        price=float(prev_close or (closed[-1][4] if closed else 0.0)),
        float_shares=facts.float_shares,
        float_contradicted=facts.float_contradicted,
        shares_outstanding=facts.shares_outstanding,
        fifty_two_week_high=facts.fifty_two_week_high,
        avg_volume=facts.avg_volume,
    )


def _open_ts(day: str) -> float:
    from datetime import date as date_cls

    return datetime.combine(date_cls.fromisoformat(day), _REGULAR_OPEN, tzinfo=ET).timestamp()


def run(session_date: str, days: dict[str, SymbolDay], prev_close: dict[str, float], facts: dict[str, Facts], *,
        stop: threading.Event | None = None, progress: Callable[[int, int], None] | None = None) -> EngineResult:
    """Feed every stock's ticks through the engine in time order; the alerts it raised, oldest first."""
    total = sum(len(d) for d in days.values())
    result = EngineResult()
    open_ts = _open_ts(session_date)
    with no_saves():
        state = fresh_engine()
        result.config = config_digest()
        heap: list[tuple[float, str, int]] = [(d.ts[0], sym, 0) for sym, d in days.items() if len(d)]
        heapq.heapify(heap)
        clock = ReplayClock(heap[0][0] if heap else 0.0)
        primed: set[str] = set()
        with pinned_clock(clock), quiet_trade_log(), floors_sat_out(state) as floors:
            result.floor_unproven = floors
            while heap:
                ts, sym, i = heapq.heappop(heap)
                day = days[sym]
                if i + 1 < len(day):
                    heapq.heappush(heap, (day.ts[i + 1], sym, i + 1))
                clock.set(ts)
                close = prev_close.get(sym)
                fact = facts.get(sym) or Facts()
                if sym not in primed:
                    _prime(sym, day, ts, close, fact)
                    primed.add(sym)
                price = float(day.price[i])
                gap = ((fact.day_open / close - 1.0) * 100.0
                       if close and fact.day_open and ts >= open_ts else None)
                hm.update_ticker_snapshot(
                    sym, price=price,
                    change_pct=round((price / close - 1.0) * 100.0, 2) if close else None,
                    gap_pct=gap,
                )
                hm.on_trade_update(sym, price, ts, volume=int(day.volume[i]), day_high=float(day.high[i]))
                flush_due(state, ts, result.alerts)
                result.ticks += 1
                if result.ticks % 20_000 == 0:
                    if stop is not None and stop.is_set():
                        raise Cancelled()
                    if progress is not None:
                        progress(result.ticks, total)
            # The live flush loop keeps ticking after the day's last print: a burst still open goes out at its end.
            dues = [due for bucket in state.pending_consolidation.values() for due, _alert in bucket]
            if dues:
                clock.set(max(dues))
                flush_due(state, max(dues), result.alerts)
        result.primed = len(primed)
        result.gate_counters = dict(state.gate_counters)
        result.pending_unflushed = sum(len(bucket) for bucket in state.pending_consolidation.values())
    return result
