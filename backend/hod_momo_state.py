"""Single mutable-state owner for the HOD Momo engine.

Phase 10 implements ADR 001/003/004: focused imperative-shell modules always
resolve the current owner through ``get_state()``. They never retain aliases to
mutable fields, so tests and startup recovery can replace the owner atomically.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable

from hod_momo_models import (
    AlertObject,
    DecisionRecord,
    MasterGateConfig,
    StrategyConfig,
    TickerSnap,
)


@dataclass
class HodMomoState:
    price_buffer: dict[str, deque[tuple[float, float]]] = field(default_factory=dict)
    surge_seeded: set[str] = field(default_factory=set)
    pending_surge_seed: set[str] = field(default_factory=set)
    last_trade_ts: float | None = None
    session_highs: dict[str, float] = field(default_factory=dict)
    # True once bar max-high and/or IBKR tick-6 day High has seeded the symbol.
    session_high_seeded: set[str] = field(default_factory=set)
    # IBKR L1 tick type 6 (day High) — floor for session_highs.
    day_highs: dict[str, float] = field(default_factory=dict)
    # "bars" | "tick6" | "bars+tick6" — debug / decision log.
    session_high_source: dict[str, str] = field(default_factory=dict)
    # Wall time when session high last *rose* via observed print or post-seed
    # tick-6 (not the initial bars/tick6 floor seed). Opens HOD alert grace.
    session_high_raised_ts: dict[str, float] = field(default_factory=dict)
    cooldown: dict[tuple[str, int], float] = field(default_factory=dict)
    pending_consolidation: dict[str, list[tuple[float, AlertObject]]] = field(
        default_factory=dict
    )
    configs: dict[int, StrategyConfig] = field(default_factory=dict)
    master: MasterGateConfig = field(default_factory=MasterGateConfig)
    blocklist: set[str] = field(default_factory=set)
    session_date: str = ""
    today_alerts: list[AlertObject] = field(default_factory=list)
    hod_ws_clients: set[Any] = field(default_factory=set)
    total_trades_seen: int = 0
    gate_counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    recent_decisions: deque[DecisionRecord] = field(
        default_factory=lambda: deque(maxlen=500)
    )
    per_symbol_decisions: dict[str, deque[DecisionRecord]] = field(
        default_factory=dict
    )
    fundamentals_queue: deque[str] = field(default_factory=deque)
    fundamentals_queued: set[str] = field(default_factory=set)
    startup_ts: float = 0.0
    alerts_dirty: bool = False
    last_alert_save_mono: float = 0.0
    highs_dirty: bool = False
    last_highs_save_mono: float = 0.0
    ticker_snaps: dict[str, TickerSnap] = field(default_factory=dict)
    active_symbol_name: str = ""
    on_blocklist_changed: Callable[[], None] | None = None


_state = HodMomoState()


def get_state() -> HodMomoState:
    return _state


def replace_state(state: HodMomoState | None = None) -> HodMomoState:
    """Atomically replace the owner; intended for tests and controlled recovery."""
    global _state
    _state = state or HodMomoState()
    return _state
