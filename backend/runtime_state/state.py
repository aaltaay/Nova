"""Typed ownership for mutable scanner/runtime state.

ADR 001 keeps Nova's caches in-process; this module gives that shared memory a
single explicit owner. ADR 002 consumers retrieve the current owner through a
small provider instead of importing the FastAPI composition root.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from constants import (
    GAPPER_MIN_GAP_PCT,
    SCAN_CAP_DEFAULT,
    SCAN_REQUIRE_TRADABLE,
    TOP_N_DEFAULT,
)
from constants_metrics import (
    HEALTH_LATENCY_SOURCE_ALPACA_ACCOUNT,
    HEALTH_SOURCE_ALPACA_ACCOUNT,
)

ScannerRow = dict[str, Any]
HealthPayload = dict[str, Any]

# Table state values (ADR 008 — session-owned persistent scanner rosters).
TABLE_STATE_LIVE = "live"
TABLE_STATE_FROZEN = "frozen"
TABLE_STATE_UNAVAILABLE = "unavailable"


@dataclass(slots=True)
class TableState:
    """Session-scoped metadata for one scanner table (gappers/gainers/losers/afterhours).

    ``state`` transitions ``unavailable`` -> ``live`` -> ``frozen`` at most once per
    session; a ``frozen`` table's roster/values must never change again until the
    next session's rollover picks a new ``session_key``. ``revision`` is bumped on
    every committed roster or freeze so consumers (WS clients, integrity checks)
    can detect stale/out-of-order writes without relying on wall-clock timestamps.
    """

    state: str = TABLE_STATE_UNAVAILABLE
    session_key: str = ""
    source: str = ""
    revision: int = 0
    roster_ts: float = 0.0
    quote_ts: float = 0.0
    frozen_at: float = 0.0


def _env_bool(primary: str, legacy: str, default: bool) -> bool:
    raw = os.environ.get(primary) or os.environ.get(legacy)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True, slots=True)
class ScannerRuntimeConfig:
    """Environment-derived scanner values captured for one app process."""

    scan_cap: int
    min_gap_pct: float
    top_n: int
    require_tradable: bool

    @classmethod
    def from_environment(cls) -> "ScannerRuntimeConfig":
        return cls(
            scan_cap=int(os.environ.get("ALPACA_SCAN_SYMBOL_CAP", str(SCAN_CAP_DEFAULT))),
            min_gap_pct=float(
                os.environ.get(
                    "NOVA_MIN_GAP_PCT",
                    os.environ.get("BLAST_MIN_GAP_PCT", str(GAPPER_MIN_GAP_PCT)),
                )
            ),
            top_n=int(
                os.environ.get("NOVA_TOP_N", os.environ.get("BLAST_TOP_N", str(TOP_N_DEFAULT)))
            ),
            require_tradable=_env_bool(
                "NOVA_SCAN_REQUIRE_TRADABLE",
                "BLAST_SCAN_REQUIRE_TRADABLE",
                SCAN_REQUIRE_TRADABLE,
            ),
        )


@dataclass(slots=True)
class ScannerRuntimeState:
    """All mutable caches and status values shared by scanner consumers."""

    config: ScannerRuntimeConfig = field(default_factory=ScannerRuntimeConfig.from_environment)

    assets_cache: list[str] = field(default_factory=list)
    assets_cache_set: set[str] = field(default_factory=set)
    assets_cache_ts: float = 0.0

    gapper_cache: list[ScannerRow] = field(default_factory=list)
    gapper_cache_ts: float = 0.0
    gapper_table: TableState = field(default_factory=TableState)
    last_discovery_ts: float = 0.0
    # Last IBKR thread→asyncio bridge failure (loud; UI/integrity can surface).
    ibkr_bridge_last_error: str = ""
    ibkr_bridge_last_error_ts: float = 0.0

    afterhours_cache: list[ScannerRow] = field(default_factory=list)
    afterhours_cache_ts: float = 0.0
    afterhours_table: TableState = field(default_factory=TableState)
    last_afterhours_discovery_ts: float = 0.0

    gainer_cache: list[ScannerRow] = field(default_factory=list)
    gainer_cache_ts: float = 0.0
    gainer_table: TableState = field(default_factory=TableState)
    loser_cache: list[ScannerRow] = field(default_factory=list)
    loser_cache_ts: float = 0.0
    loser_table: TableState = field(default_factory=TableState)

    news_catalyst_cache: list[ScannerRow] = field(default_factory=list)
    news_catalyst_cache_ts: float = 0.0
    last_catalyst_scan_ts: float = 0.0

    avg_volume_cache: dict[str, float] = field(default_factory=dict)
    avg_volume_date: str = ""

    cached_health: HealthPayload = field(
        default_factory=lambda: {
            "status": "loading",
            "latency_ms": 0,
            "health_source": HEALTH_SOURCE_ALPACA_ACCOUNT,
            "latency_source": HEALTH_LATENCY_SOURCE_ALPACA_ACCOUNT,
        }
    )
    current_mode: str = "closed"

    hod_momo_universe: set[str] = field(default_factory=set)
    hod_momo_universe_ts: float = 0.0


_runtime_state = ScannerRuntimeState()


def get_runtime_state() -> ScannerRuntimeState:
    """Return the current process-wide state owner."""
    return _runtime_state


def reset_runtime_state(
    *, config: ScannerRuntimeConfig | None = None
) -> ScannerRuntimeState:
    """Replace all runtime state with empty caches; intended for startup/tests."""
    global _runtime_state
    _runtime_state = ScannerRuntimeState(
        config=config or ScannerRuntimeConfig.from_environment()
    )
    return _runtime_state


def set_runtime_state_for_testing(state: ScannerRuntimeState) -> ScannerRuntimeState:
    """Install a test-owned state and return the previous owner for restoration."""
    global _runtime_state
    previous = _runtime_state
    _runtime_state = state
    return previous
