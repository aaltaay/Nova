"""
FastAPI lifespan — startup restore, background tasks, shutdown cleanup.

Extracted from ``main.py`` so the app factory stays a thin wiring file.
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
import hod_momo_seed as _hod_momo_seed
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
    L2_RETENTION_SWEEP_INTERVAL_SEC,
)
from health_status import ping_health, set_health_broker_keys_missing
from ibkr import client as _ibkr_client
from ibkr import reprice as _ibkr_reprice
from ibkr import ticks as _ibkr_ticks
from ibkr_bridge import (
    apply_table_quotes,
    get_ibkr_detail_symbols,
    run_ibkr,
    table_reprice_symbols,
)
from scanner_push import broadcast as _scanner_broadcast
from scan_loop import scan_loop
from ticker import _find_ibkr_cache_row
from universe import invalidate_universe_cache
from websocket import broadcast_trade_update, stream_loop
from observability import init_sentry

logger = logging.getLogger(__name__)


def _m():
    import main as _main
    return _main


def configure_cors(app: FastAPI) -> None:
    """Register the CORS middleware — extracted out of main.py's app factory
    (see backend-modularity rule) so that file stays under the file-size limit.

    Origins default to "*" for local dev (see centralized-constants.mdc);
    set NOVA_CORS_ALLOWED_ORIGINS (comma-separated) to lock this down for any
    non-local deploy. Nova's frontend never sends cookies/auth credentials, so
    allow_credentials stays False — required anyway for a wildcard origin per
    the CORS spec.
    """
    origins_env = os.environ.get("NOVA_CORS_ALLOWED_ORIGINS", "").strip()
    origins = (
        [o.strip() for o in origins_env.split(",") if o.strip()]
        if origins_env
        else CORS_ALLOWED_ORIGINS_DEFAULT
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_sentry()
    m = _m()
    _migrate_legacy_files()
    cleanup_old_snapshots(HISTORY_RETENTION_DAYS)

    restored, restored_ts = load_gapper_snapshot()
    if restored:
        m._gapper_cache = restored
        m._gapper_cache_ts = restored_ts

    ah_restored, ah_restored_ts = load_afterhours_snapshot()
    if ah_restored:
        m._afterhours_cache = ah_restored
        m._afterhours_cache_ts = ah_restored_ts

    mv_gainers, mv_losers, mv_ts = load_movers_snapshot()
    if mv_gainers or mv_losers:
        m._gainer_cache = mv_gainers
        m._loser_cache = mv_losers
        m._gainer_cache_ts = mv_ts
        m._loser_cache_ts = mv_ts

    _hod_momo.load_state()
    _journal_db.init_db()
    _l2_db.init_db()
    _nova_os_events_db.init_db()
    from nova_os.recovery import run_startup_recovery

    try:
        run_startup_recovery()
    except Exception:
        logger.exception("Nova OS startup recovery failed")
    _hod_momo._on_blocklist_changed = invalidate_universe_cache

    loop = asyncio.get_event_loop()
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if headers:
        await loop.run_in_executor(None, lambda: ping_health(base_url, headers))
    else:
        set_health_broker_keys_missing()
        logger.warning(
            "Alpaca credentials missing (APCA_API_KEY_ID / APCA_API_SECRET_KEY); "
            "scanner cannot run until they are set in the host environment."
        )

    scan_task = asyncio.create_task(scan_loop())
    ws_task = asyncio.create_task(stream_loop())
    hod_flush_task = asyncio.create_task(_hod_momo.flush_consolidated_loop())
    hod_reset_task = asyncio.create_task(_hod_momo.session_reset_loop())
    hod_enrich_task = asyncio.create_task(_hod_momo_enrichment.universe_enrichment_loop())
    hod_fund_task = asyncio.create_task(_hod_momo_enrichment.fundamentals_enrichment_loop())
    hod_seed_task = asyncio.create_task(
        _hod_momo_seed.seed_refresh_loop(_get_discovery_provider)
    )
    setups_scan_task = asyncio.create_task(_setups_stream.scan_loop())
    risk_reset_task = asyncio.create_task(_risk.session_reset_loop())
    executor_fill_task = asyncio.create_task(_executor.fill_poll_loop())

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

    l2_flush_task = asyncio.create_task(_l2_batch.flush_loop())
    l2_retention_task = asyncio.create_task(_l2_retention_loop())

    await _ibkr_client.startup()
    _ibkr_ticks.configure(broadcast_trade_update, _find_ibkr_cache_row)
    detail_reprice_task = asyncio.create_task(_ibkr_reprice.detail_reprice_loop(
        get_ibkr_detail_symbols, run_ibkr, broadcast_trade_update, _find_ibkr_cache_row,
        lambda sym: _ibkr_ticks.is_fresh(sym, IBKR_DETAIL_STREAM_FRESH_SEC),
    ))
    table_reprice_task = asyncio.create_task(_ibkr_reprice.table_reprice_loop(
        _get_discovery_provider, table_reprice_symbols, apply_table_quotes, _scanner_broadcast,
    ))

    yield

    try:
        _hod_momo.flush_pending_alert_save()
    except Exception:
        logger.exception("HOD Momo: final alert flush failed")
    detail_reprice_task.cancel()
    table_reprice_task.cancel()
    scan_task.cancel()
    ws_task.cancel()
    hod_flush_task.cancel()
    hod_reset_task.cancel()
    hod_enrich_task.cancel()
    hod_fund_task.cancel()
    hod_seed_task.cancel()
    setups_scan_task.cancel()
    risk_reset_task.cancel()
    executor_fill_task.cancel()
    l2_flush_task.cancel()
    l2_retention_task.cancel()
    for t in (
        detail_reprice_task, table_reprice_task, scan_task, ws_task,
        hod_flush_task, hod_reset_task, hod_enrich_task, hod_fund_task, hod_seed_task,
    ):
        try:
            await t
        except asyncio.CancelledError:
            pass
    try:
        _l2_batch.flush()
    except Exception:
        logger.exception("l2.batch: final flush failed")
    await _ibkr_client.shutdown()
