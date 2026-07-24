"""
FastAPI lifespan — startup restore, background tasks, shutdown cleanup.

Extracted from ``main.py`` so the app factory stays a thin wiring file.

HTTP readiness: yield as soon as local restore/DB init finishes. IBKR connect,
Alpaca health ping, Nova OS recovery, and background loops run in a deferred
bootstrap task so a hung Gateway handshake cannot leave :8000 listening but
never serving (Starlette startup blocked on the same event loop).
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import hod_momo as _hod_momo
import hod_momo_enrichment as _hod_momo_enrichment
import hod_momo_heartbeat as _hod_momo_heartbeat
import hod_momo_surge_seed as _hod_momo_surge_seed
import integrity_live as _integrity_live
import journal.db as _journal_db
import l2.db as _l2_db
import nova_os.events_db as _nova_os_events_db
import strategy.executor as _executor
import strategy.risk as _risk
import strategy.setups_stream as _setups_stream
from alpaca import _alpaca_headers, _env, _get_discovery_provider
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
    IBKR_DETAIL_STREAM_FRESH_SEC,
    IBKR_RECONNECT_DELAY_SEC,
    L2_RETENTION_SWEEP_INTERVAL_SEC,
)
import archive.db as _archive_db
from archive.scheduler import archive_maintenance_loop, maintenance_enabled
from health_status import ping_health, set_health_broker_keys_missing
from ibkr import client as _ibkr_client
from ibkr import reprice as _ibkr_reprice
from ibkr import scanner_l1 as _scanner_l1
from ibkr import scanner_session as _scanner_session
from ibkr import scanner_stream as _scanner_stream
from ibkr import ticks as _ibkr_ticks
from ibkr_bridge import (
    apply_l1_quote,
    get_ibkr_detail_symbols,
    hod_stream_symbols,
    run_ibkr,
    symbols_for_tab,
)
import scanner_tab_registry as _scanner_tabs
from scanner_push import broadcast as _scanner_broadcast
from scan_loop import scan_loop
from ticker import _find_ibkr_cache_row
from universe import invalidate_universe_cache
from websocket import broadcast_trade_update, stream_loop
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

    # ADR 008: attach session_key / freeze metadata for restored rows.
    _scanner_session.reconcile_session_tables(state)


def _init_databases() -> None:
    _hod_momo.load_state()
    _journal_db.init_db()
    _l2_db.init_db()
    _nova_os_events_db.init_db()
    _archive_db.init_db()
    try:
        from execution import store as _execution_store
        _execution_store.init_db()
    except Exception:
        logger.exception("execution ledger: init_db failed")
    _hod_momo.set_blocklist_changed_hook(invalidate_universe_cache)


async def _ping_alpaca_health() -> None:
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if not headers:
        set_health_broker_keys_missing()
        logger.warning(
            "Alpaca credentials missing (APCA_API_KEY_ID / APCA_API_SECRET_KEY); "
            "scanner cannot run until they are set in the host environment."
        )
        return
    try:
        await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(
                None, lambda: ping_health(base_url, headers)
            ),
            timeout=8.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Alpaca health ping timed out after 8s — continuing bootstrap")
    except Exception:
        logger.exception("Alpaca health ping failed")


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
    """Start background loops. Each task is spawned independently so one bad
    import/name cannot abort the rest (e.g. scanner_l1 must not die because
    a typo in fill_poll_loop aborted the list mid-build).
    """
    from l2 import batch as _l2_batch

    async def _l2_retention_loop() -> None:
        while True:
            try:
                await asyncio.sleep(L2_RETENTION_SWEEP_INTERVAL_SEC)
                _l2_db.purge_older_than()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("l2 retention sweep failed")

    def _start(name: str, factory) -> asyncio.Task | None:
        try:
            task = asyncio.create_task(factory(), name=name)
            return task
        except Exception:
            logger.exception("lifespan: failed to start background task %s", name)
            return None

    # scanner_l1 first — HOD Squeeze / active-set SLOs depend on it.
    factories: list[tuple[str, object]] = [
        ("scanner_l1.reconcile", lambda: _scanner_l1.reconcile_loop(
            _get_discovery_provider,
            _scanner_tabs.get_dominant_tab,
            symbols_for_tab,
            hod_stream_symbols,
        )),
        ("scanner_l1.flush", lambda: _scanner_l1.flush_loop(_scanner_broadcast)),
        ("hod_momo.heartbeat", lambda: _hod_momo_heartbeat.active_heartbeat_loop()),
        ("hod_momo.surge_seed", lambda: _hod_momo_surge_seed.surge_seed_loop(
            _get_discovery_provider,
        )),
        ("scan_loop", scan_loop),
        ("stream_loop", stream_loop),
        ("hod_momo.flush_consolidated", _hod_momo.flush_consolidated_loop),
        ("hod_momo.session_reset", _hod_momo.session_reset_loop),
        ("hod_momo.universe_enrichment", _hod_momo_enrichment.universe_enrichment_loop),
        ("hod_momo.fundamentals_enrichment", _hod_momo_enrichment.fundamentals_enrichment_loop),
        ("integrity_live", _integrity_live.integrity_loop),
        ("setups_stream", _setups_stream.scan_loop),
        ("risk.session_reset", _risk.session_reset_loop),
        # Name is fill_poll_loop (singular). The old fills_poll_loop typo raised
        # AttributeError mid-list and aborted spawn before scanner_l1.
        ("executor.fill", _executor.fill_poll_loop),
        ("l2.flush", _l2_batch.flush_loop),
        ("l2.retention", _l2_retention_loop),
        ("ibkr.detail_reprice", lambda: _ibkr_reprice.detail_reprice_loop(
            get_ibkr_detail_symbols, run_ibkr, broadcast_trade_update, _find_ibkr_cache_row,
            lambda sym: _ibkr_ticks.is_fresh(sym, IBKR_DETAIL_STREAM_FRESH_SEC),
        )),
        ("observability.loop_lag", _loop_lag.sample_loop_lag_loop),
    ]
    if maintenance_enabled():
        factories.append(("archive.maintenance", archive_maintenance_loop))
        logger.info("archive.maintenance: enabled (ARCHIVE_MAINTENANCE_ENABLED)")

    if (
        _scanner_session.is_persistent_enabled()
        and _get_discovery_provider() == "ibkr"
    ):
        factories.append(("scanner_stream", _scanner_stream.manager_loop))
        logger.info(
            "scanner_stream: enabled (authoritative=%s)",
            _scanner_session.is_persistent_authoritative(),
        )

    tasks: list[asyncio.Task] = []
    for name, factory in factories:
        task = _start(name, factory)
        if task is not None:
            tasks.append(task)
    return tasks


async def _bootstrap_runtime() -> None:
    """Deferred after HTTP yield: network ping, IBKR, recovery, loops."""
    global _runtime_tasks
    await _ping_alpaca_health()

    await _ibkr_client.startup()
    # Prefer waiting ~one connect wall; never block HTTP (already yielded).
    connected = await _wait_ibkr_connected(float(IBKR_RECONNECT_DELAY_SEC) + 2.0)
    if not connected:
        logger.warning(
            "IBKR: not connected after bootstrap wait — recovery runs in "
            "disconnected mode; reconnect_loop keeps retrying"
        )

    try:
        _risk.reconstruct_from_journal()
    except Exception:
        logger.exception("Risk engine: startup reconstruction from journal failed")

    from nova_os.recovery import run_startup_recovery

    try:
        run_startup_recovery()
    except Exception:
        logger.exception("Nova OS startup recovery failed")

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
    init_sentry()
    _restore_caches()
    _init_databases()

    # Sync wiring only — no await on IBKR/network before yield.
    _ibkr_ticks.configure(broadcast_trade_update, _find_ibkr_cache_row)
    _scanner_l1.configure(apply_l1_quote)

    bootstrap_task = asyncio.create_task(_bootstrap_runtime())
    logger.info("lifespan: HTTP ready — IBKR/bootstrap deferred")
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
