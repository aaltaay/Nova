"""Session windows + freeze/rollover for ADR 008 scanner tables.

Pure policy helpers (injected clock via ``now``). Scan loop and the persistent
scanner manager both call these so one-shot and push paths share boundaries.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable

from constants import (
    SESSION_AFTERHOURS_END_MIN_ET,
    SESSION_PREMARKET_START_MIN_ET,
    SESSION_RTH_CLOSE_MIN_ET,
    SESSION_RTH_OPEN_MIN_ET,
)
from market import ET, now_et, session_key_et
from runtime_state.state import (
    TABLE_STATE_FROZEN,
    TABLE_STATE_LIVE,
    TABLE_STATE_UNAVAILABLE,
    TableState,
)

logger = logging.getLogger(__name__)

TABLE_GAPPERS = "gappers"
TABLE_GAINERS = "gainers"
TABLE_LOSERS = "losers"
TABLE_AFTERHOURS = "afterhours"

PERIOD_PREMARKET = "premarket"
PERIOD_RTH = "rth"
PERIOD_AFTERHOURS = "afterhours"
PERIOD_CLOSED = "closed"

# Live window end (minutes from midnight ET) — freeze exactly at this boundary.
_FREEZE_AT_MIN: dict[str, int] = {
    TABLE_GAPPERS: SESSION_RTH_OPEN_MIN_ET,       # 09:30
    TABLE_GAINERS: SESSION_RTH_CLOSE_MIN_ET,      # 16:00
    TABLE_LOSERS: SESSION_RTH_CLOSE_MIN_ET,       # 16:00
    TABLE_AFTERHOURS: SESSION_AFTERHOURS_END_MIN_ET,  # 20:00
}

# Live window start (inclusive). Losers are RTH-only.
_LIVE_FROM_MIN: dict[str, int] = {
    TABLE_GAPPERS: SESSION_PREMARKET_START_MIN_ET,
    TABLE_GAINERS: SESSION_PREMARKET_START_MIN_ET,
    TABLE_LOSERS: SESSION_RTH_OPEN_MIN_ET,
    TABLE_AFTERHOURS: SESSION_RTH_CLOSE_MIN_ET,
}


def _minutes_et(now: datetime) -> int:
    local = now.astimezone(ET)
    return local.hour * 60 + local.minute


def session_period(now: datetime | None = None) -> str:
    """Premarket / RTH / afterhours / closed for desired scanner leases."""
    mins = _minutes_et(now or now_et())
    if SESSION_PREMARKET_START_MIN_ET <= mins < SESSION_RTH_OPEN_MIN_ET:
        return PERIOD_PREMARKET
    if SESSION_RTH_OPEN_MIN_ET <= mins < SESSION_RTH_CLOSE_MIN_ET:
        return PERIOD_RTH
    if SESSION_RTH_CLOSE_MIN_ET <= mins < SESSION_AFTERHOURS_END_MIN_ET:
        return PERIOD_AFTERHOURS
    return PERIOD_CLOSED


def desired_leases(now: datetime | None = None) -> list[tuple[str, str]]:
    """Return ``(table, scan_code)`` pairs for the current period (≤2 slots)."""
    from constants import (
        IBKR_SCAN_CODE_AH_GAINERS,
        IBKR_SCAN_CODE_GAINERS,
        IBKR_SCAN_CODE_GAPPERS,
        IBKR_SCAN_CODE_LOSERS,
    )

    period = session_period(now)
    if period == PERIOD_PREMARKET:
        return [
            (TABLE_GAINERS, IBKR_SCAN_CODE_GAINERS),
            (TABLE_GAPPERS, IBKR_SCAN_CODE_GAPPERS),
        ]
    if period == PERIOD_RTH:
        return [
            (TABLE_GAINERS, IBKR_SCAN_CODE_GAINERS),
            (TABLE_LOSERS, IBKR_SCAN_CODE_LOSERS),
        ]
    if period == PERIOD_AFTERHOURS:
        return [(TABLE_AFTERHOURS, IBKR_SCAN_CODE_AH_GAINERS)]
    return []


def table_is_live(table: str, now: datetime | None = None) -> bool:
    """True when the table's session window is open (not yet at freeze boundary)."""
    now = now or now_et()
    mins = _minutes_et(now)
    start = _LIVE_FROM_MIN.get(table)
    end = _FREEZE_AT_MIN.get(table)
    if start is None or end is None:
        return False
    return start <= mins < end


def table_should_be_frozen(table: str, now: datetime | None = None) -> bool:
    """True when past the freeze boundary for the current session calendar day."""
    now = now or now_et()
    mins = _minutes_et(now)
    end = _FREEZE_AT_MIN.get(table)
    if end is None:
        return False
    # Before the live window starts on a new session day, the prior freeze holds
    # until 04:00 rollover clears it — treat pre-live as "not actively live."
    start = _LIVE_FROM_MIN.get(table, 0)
    if mins < SESSION_PREMARKET_START_MIN_ET:
        return True  # midnight–03:59: prior session already complete
    if mins < start:
        return False  # waiting for this table's live window
    return mins >= end


def table_attr(state, table: str) -> TableState:
    mapping = {
        TABLE_GAPPERS: state.gapper_table,
        TABLE_GAINERS: state.gainer_table,
        TABLE_LOSERS: state.loser_table,
        TABLE_AFTERHOURS: state.afterhours_table,
    }
    return mapping[table]


def cache_attr_names(table: str) -> tuple[str, str]:
    """Return ``(rows_attr, ts_attr)`` on ScannerRuntimeState for *table*."""
    return {
        TABLE_GAPPERS: ("gapper_cache", "gapper_cache_ts"),
        TABLE_GAINERS: ("gainer_cache", "gainer_cache_ts"),
        TABLE_LOSERS: ("loser_cache", "loser_cache_ts"),
        TABLE_AFTERHOURS: ("afterhours_cache", "afterhours_cache_ts"),
    }[table]


def mark_live(table_state: TableState, *, source: str, session_key: str) -> None:
    table_state.state = TABLE_STATE_LIVE
    table_state.session_key = session_key
    table_state.source = source
    table_state.frozen_at = 0.0


def freeze_table(
    state,
    table: str,
    *,
    now_wall: float | None = None,
    source: str = "session_boundary",
) -> bool:
    """Idempotently freeze *table*. Returns True when a transition occurred."""
    ts = table_attr(state, table)
    if ts.state == TABLE_STATE_FROZEN and ts.session_key == session_key_et():
        return False
    wall = now_wall if now_wall is not None else time.time()
    key = session_key_et()
    ts.state = TABLE_STATE_FROZEN
    ts.session_key = key
    ts.source = source
    ts.frozen_at = wall
    ts.roster_ts = wall
    ts.revision += 1
    logger.info("scanner session: froze %s (session_key=%s rev=%d)", table, key, ts.revision)
    try:
        import asyncio
        from scanner_push import broadcast_table_state
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_table_state(table, ts))
    except RuntimeError:
        pass
    except Exception:
        logger.debug("scanner session: freeze broadcast failed", exc_info=True)
    return True


def ensure_session_key(state, table: str, *, source: str = "scan") -> None:
    """Attach current session_key and mark live when the window is open."""
    key = session_key_et()
    ts = table_attr(state, table)
    if ts.session_key and ts.session_key != key:
        # Rollover: prior session metadata is stale — reset before new writes.
        ts.state = TABLE_STATE_UNAVAILABLE
        ts.revision += 1
        ts.frozen_at = 0.0
        ts.roster_ts = 0.0
        ts.quote_ts = 0.0
    if table_is_live(table):
        mark_live(ts, source=source, session_key=key)
    elif table_should_be_frozen(table) and getattr(state, cache_attr_names(table)[0]):
        if ts.state != TABLE_STATE_FROZEN or ts.session_key != key:
            freeze_table(state, table, source=source)


def is_table_frozen(state, table: str) -> bool:
    """True when *table* is frozen for the current session (ADR 008).

    Shared by the one-shot runners, ``ibkr_bridge`` L1 quote application,
    and integrity — a single place answers "may this table's cache be
    mutated right now?" so a HOD-reserved-pool tick for a retained symbol
    can never reprice a table the user is told is immutable.
    """
    ts = table_attr(state, table)
    return ts.state == TABLE_STATE_FROZEN and ts.session_key == session_key_et()


def can_commit_roster(state, table: str, *, generation: int, epoch: int,
                      fence_generation: int, fence_epoch: int,
                      session_key: str) -> bool:
    """Fence a late hydration/commit against READY generation + epoch + freeze."""
    if generation != fence_generation or epoch != fence_epoch:
        return False
    if session_key != session_key_et():
        return False
    ts = table_attr(state, table)
    if ts.state == TABLE_STATE_FROZEN and ts.session_key == session_key:
        return False
    if not table_is_live(table):
        return False
    return True


def reconcile_session_tables(
    state,
    *,
    now: datetime | None = None,
    on_frozen: Callable[[str], None] | None = None,
) -> list[str]:
    """Apply freeze boundaries and 04:00 session-key rollover. Returns frozen tables."""
    now = now or now_et()
    key = session_key_et(now)
    frozen: list[str] = []
    for table in (TABLE_GAPPERS, TABLE_GAINERS, TABLE_LOSERS, TABLE_AFTERHOURS):
        ts = table_attr(state, table)
        if ts.session_key and ts.session_key != key:
            # New session — clear prior live/frozen flag so a missed morning
            # cannot be treated as today's live roster without a fresh scan.
            rows_attr, ts_attr = cache_attr_names(table)
            if ts.state == TABLE_STATE_FROZEN:
                logger.info(
                    "scanner session: rollover clearing %s (was session %s → %s)",
                    table, ts.session_key, key,
                )
            setattr(state, rows_attr, [])
            setattr(state, ts_attr, 0.0)
            ts.state = TABLE_STATE_UNAVAILABLE
            ts.session_key = key
            ts.frozen_at = 0.0
            ts.roster_ts = 0.0
            ts.quote_ts = 0.0
            ts.revision += 1
            continue
        if table_should_be_frozen(table, now) and getattr(state, cache_attr_names(table)[0]):
            if freeze_table(state, table):
                frozen.append(table)
                if on_frozen is not None:
                    on_frozen(table)
        elif table_is_live(table, now) and ts.session_key in ("", key):
            if ts.state != TABLE_STATE_LIVE:
                mark_live(ts, source="reconcile", session_key=key)
    return frozen


def is_persistent_authoritative() -> bool:
    import os
    from constants import IBKR_SCANNER_PERSISTENT_AUTHORITATIVE

    raw = os.environ.get("IBKR_SCANNER_PERSISTENT_AUTHORITATIVE")
    if raw is not None and raw.strip():
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(IBKR_SCANNER_PERSISTENT_AUTHORITATIVE)


def is_persistent_enabled() -> bool:
    import os
    from constants import IBKR_SCANNER_PERSISTENT_ENABLED

    raw = os.environ.get("IBKR_SCANNER_PERSISTENT_ENABLED")
    if raw is not None and raw.strip():
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(IBKR_SCANNER_PERSISTENT_ENABLED)
