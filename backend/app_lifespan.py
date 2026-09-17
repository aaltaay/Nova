"""
FastAPI lifespan — startup restore, background tasks, shutdown cleanup.

Extracted from ``main.py`` so the app factory stays a thin wiring file.

HTTP readiness (D-006): yield before Sentry/cache/DB. Those run off-loop
in the deferred bootstrap, then IBKR, recovery, and background loops.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import hod_momo as _hod_momo
import journal.db as _journal_db
import l2.db as _l2_db
import nova_os.events_db as _nova_os_events_db
from alpaca import _alpaca_headers
from cache import (
    _migrate_legacy_files,
    cleanup_old_snapshots,
    load_afterhours_snapshot,
    load_gapper_snapshot,
    load_movers_snapshot,
)
from constants import (
    CORS_ALLOWED_ORIGINS_DEFAULT,
    HISTORY_RETENTION_DAYS,
    IBKR_RECONNECT_DELAY_SEC,
)
import archive.db as _archive_db
from health_status import mark_nova_process_health, set_health_broker_keys_missing
from ibkr import client as _ibkr_client
from ibkr import scanner_l1 as _scanner_l1
from ibkr import scanner_session as _scanner_session
from ibkr import session_watchdog as _session_watchdog
from ibkr import ticks as _ibkr_ticks
from ibkr_bridge import apply_l1_quote
from ticker import _find_ibkr_cache_row
from universe import invalidate_universe_cache
from websocket import broadcast_trade_update
from observability import init_sentry
from runtime_state import get_runtime_state
import instance_identity
import loop_lag as _loop_lag
from metrics.http_middleware import HttpOperationMetricsMiddleware

logger = logging.getLogger(__name__)

# Background tasks spawned by deferred bootstrap (cancelled on shutdown).
_runtime_tasks: list[asyncio.Task] = []
# True once _bootstrap_runtime() has spawned all background loops — /readyz
# reports this so restart tooling can tell "serving HTTP" apart from
# "actually finished startup" (see PROBLEM_LOG 2026-07-23).
_bootstrap_complete: bool = False


def is_bootstrap_complete() -> bool:
    return _bootstrap_complete


def configure_cors(app: FastAPI) -> None:
    """Register the CORS middleware — extracted out of main.py's app factory
    (see backend-modularity rule) so that file stays under the file-size limit.

    Origins default to localhost Vite ports (see CORS_ALLOWED_ORIGINS_DEFAULT);
    set NOVA_CORS_ALLOWED_ORIGINS (comma-separated) for non-local deploys.
    allow_credentials stays False (frontend does not send cookies).
    """
    origins_env = os.environ.get("NOVA_CORS_ALLOWED_ORIGINS", "").strip()
    origins = (
        [o.strip() for o in origins_env.split(",") if o.strip()]
        if origins_env
        else CORS_ALLOWED_ORIGINS_DEFAULT
    )
    app.add_middleware(HttpOperationMetricsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _restore_caches() -> None:
    state = get_runtime_state()
    _migrate_legacy_files()
    cleanup_old_snapshots(HISTORY_RETENTION_DAYS)

    restored, restored_ts = load_gapper_snapshot()
    if restored:
        state.gapper_cache = restored
        state.gapper_cache_ts = restored_ts

    ah_restored, ah_restored_ts = load_afterhours_snapshot()
    if ah_restored:
        state.afterhours_cache = ah_restored
        state.afterhours_cache_ts = ah_restored_ts

    mv_gainers, mv_losers, mv_ts = load_movers_snapshot()
    if mv_gainers or mv_losers:
        state.gainer_cache = mv_gainers
        state.loser_cache = mv_losers
        state.gainer_cache_ts = mv_ts
        state.loser_cache_ts = mv_ts

    try:
        from news_catalyst_persist import load_news_catalyst_snapshot

        catalysts, cat_ts = load_news_catalyst_snapshot()
        if catalysts:
            state.news_catalyst_cache = catalysts
            state.news_catalyst_cache_ts = cat_ts
    except Exception:
        logger.exception("news catalysts: snapshot restore failed")

    # ADR 008: attach session_key / freeze metadata for restored rows.
    _scanner_session.reconcile_session_tables(state)


def _init_databases() -> None:
    _hod_momo.load_state()
    _journal_db.init_db()
    try:
        from advise import book as _advise_book

        _advise_book.init_db()
    except Exception:
        logger.exception("advise book: init_db failed")
    _l2_db.init_db()
    _nova_os_events_db.init_db()
    _archive_db.init_db()
    try:
        from execution import store as _execution_store
        _execution_store.init_db()
    except Exception:
        logger.exception("execution ledger: init_db failed")
    try:
        from journal.round_trip import rebuild_from_ledger

        rebuild_from_ledger()
    except Exception:
        logger.exception("journal.round_trip: ledger rebuild failed")
    _hod_momo.set_blocklist_changed_hook(invalidate_universe_cache)


async def _mark_nova_api_health() -> None:
    """API chip SoT = Nova process. Alpaca keys are aux-only (warn, do not fail API)."""
    mark_nova_process_health()
    headers = _alpaca_headers()
    if not headers:
        set_health_broker_keys_missing()


async def _wait_ibkr_connected(budget_sec: float) -> bool:
    """Poll is_ready() briefly so recovery sees a fully-synchronized Gateway
    session if fast — not just a raw socket connect (see PROBLEM_LOG
    2026-07-23: background tasks used to spawn while account-kind validation
    and cache warm-up were still running)."""
    deadline = asyncio.get_running_loop().time() + budget_sec
    while asyncio.get_running_loop().time() < deadline:
        if _ibkr_client.is_ready():
            return True
        await asyncio.sleep(0.25)
    return _ibkr_client.is_ready()


def _spawn_runtime_tasks() -> list[asyncio.Task]:
    from app_runtime_tasks import spawn_runtime_tasks

    return spawn_runtime_tasks()


def _local_startup() -> None:
    """Sentry + disk restore + DB init. After HTTP yield, off the loop."""
    t0 = time.perf_counter()
    init_sentry()
    t_s = time.perf_counter()
    _restore_caches()
    t_c = time.perf_counter()
    _init_databases()
    try:
        from news.sentiment import warm_pipeline
        warm_pipeline()
    except Exception:
        logger.exception("news.sentiment: FinBERT warm failed to start")
    logger.info(
        "lifespan: local startup sentry=%.0fms cache=%.0fms db=%.0fms",
        (t_s - t0) * 1000, (t_c - t_s) * 1000, (time.perf_counter() - t_c) * 1000,
    )


async def _bootstrap_runtime() -> None:
    """Deferred after HTTP yield: local restore, then network/IBKR/loops."""
    global _runtime_tasks
    await asyncio.to_thread(_local_startup)
    await _mark_nova_api_health()

    from ibkr.loop_supervisor import set_http_loop, spawn_ib, start as start_ib_loop

    set_http_loop(asyncio.get_running_loop())
    start_ib_loop()
    await _ibkr_client.startup()
    spawn_ib("observability.ib_loop_lag", _loop_lag.sample_ib_loop_lag_loop)
    # Sibling task to the dialer, not inside it -- see session_watchdog
    # module docstring / PROBLEM_LOG 2026-08-31.
    spawn_ib("ibkr.session_watchdog", _session_watchdog.run)
    # Prefer waiting ~one connect wall; never block HTTP (already yielded).
    connected = await _wait_ibkr_connected(float(IBKR_RECONNECT_DELAY_SEC) + 2.0)
    if not connected:
        logger.warning(
            "IBKR: not connected after bootstrap wait — recovery runs in "
            "disconnected mode; reconnect_loop keeps retrying"
        )

    from startup_reconciliation import run_startup_reconciliation

    run_startup_reconciliation()

    _runtime_tasks = _spawn_runtime_tasks()
    global _bootstrap_complete
    _bootstrap_complete = True
    logger.info("lifespan bootstrap complete (%d background tasks)", len(_runtime_tasks))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _runtime_tasks
    logger.info(
        "Nova API instance %s starting (pid=%s ppid=%s reload=%s)",
        instance_identity.INSTANCE_ID,
        instance_identity.PID,
        instance_identity.PARENT_PID,
        instance_identity.RELOAD_ENABLED,
    )
    # Sync wiring only — no Sentry, disk, or IBKR/network before yield.
    _ibkr_ticks.configure(broadcast_trade_update, _find_ibkr_cache_row)
    _scanner_l1.configure(apply_l1_quote)

    bootstrap_task = asyncio.create_task(_bootstrap_runtime())
    logger.info("lifespan: HTTP ready — Sentry/restore/IBKR deferred")
    yield

    try:
        _hod_momo.flush_pending_alert_save()
        _hod_momo.flush_pending_highs_save()
    except Exception:
        logger.exception("HOD Momo: final alert flush failed")

    bootstrap_task.cancel()
    try:
        await bootstrap_task
    except asyncio.CancelledError:
        pass
    global _bootstrap_complete
    _bootstrap_complete = False

    try:
        await _scanner_l1.shutdown()
    except Exception:
        logger.exception("scanner_l1 shutdown failed")

    for t in list(_runtime_tasks):
        t.cancel()
    for t in list(_runtime_tasks):
        try:
            await t
        except asyncio.CancelledError:
            pass
    _runtime_tasks = []

    try:
        from l2 import batch as _l2_batch
        _l2_batch.flush()
    except Exception:
        logger.exception("l2.batch: final flush failed")
    try:
        from scan_executor import shutdown_scan_executor
        shutdown_scan_executor()
    except Exception:
        logger.exception("scan_executor shutdown failed")
    await _ibkr_client.shutdown()
    try:
        from ibkr.loop_supervisor import stop as stop_ib_loop
        stop_ib_loop()
    except Exception:
        logger.exception("IB loop supervisor stop failed")
    try:
        from logging_setup import shutdown_logging
        shutdown_logging()
    except Exception:
        logger.exception("logging_setup shutdown failed")
