"""Background-loop factories for FastAPI lifespan.

Kept out of ``app_lifespan.py`` so that file stays under the 400-line limit.
Each factory is spawned independently -- one bad name must not abort scanner_l1.
"""
from __future__ import annotations

import asyncio
import logging

import hod_momo as _hod_momo
import hod_momo_enrichment as _hod_momo_enrichment
import hod_momo_heartbeat as _hod_momo_heartbeat
import hod_momo_surge_seed as _hod_momo_surge_seed
import integrity_live as _integrity_live
import l2.db as _l2_db
import scanner_news_badge as _scanner_news_badge
import scanner_tab_registry as _scanner_tabs
import strategy.executor as _executor
import strategy.risk as _risk
import strategy.setups_stream as _setups_stream
from alpaca import _get_discovery_provider
from archive.scheduler import archive_maintenance_loop, maintenance_enabled
import archive.write_queue as _archive_write_queue
from bot.loops import breaker_loop, ttl_loop
from constants import IBKR_DETAIL_STREAM_FRESH_SEC, L2_RETENTION_SWEEP_INTERVAL_SEC
from ibkr import reprice as _ibkr_reprice
from ibkr import scanner_l1 as _scanner_l1
from ibkr import scanner_session as _scanner_session
from ibkr import scanner_stream as _scanner_stream
from ibkr import ticks as _ibkr_ticks
from ibkr import nasdaq_halt_feed as _nasdaq_halt_feed
from ibkr_bridge import (
    get_ibkr_detail_symbols,
    hod_stream_symbols,
    run_ibkr,
    symbols_for_tab,
)
import loop_lag as _loop_lag
from scan_loop import scan_loop
from scanner_push import broadcast as _scanner_broadcast
from ticker import _find_ibkr_cache_row
from websocket import broadcast_trade_update, stream_loop

logger = logging.getLogger(__name__)


def spawn_runtime_tasks() -> list[asyncio.Task]:
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
            return asyncio.create_task(factory(), name=name)
        except Exception:
            logger.exception("lifespan: failed to start background task %s", name)
            return None

    factories: list[tuple[str, object]] = [
        ("scanner_l1.reconcile", lambda: _scanner_l1.reconcile_loop(
            _get_discovery_provider,
            _scanner_tabs.get_active_tables,
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
        ("scanner_news_badge", _scanner_news_badge.refresh_loop),
        ("setups_stream", _setups_stream.scan_loop),
        ("risk.session_reset", _risk.session_reset_loop),
        # Name is fill_poll_loop (singular). The old fills_poll_loop typo raised
        # AttributeError mid-list and aborted spawn before scanner_l1.
        ("executor.fill", _executor.fill_poll_loop),
        ("l2.flush", _l2_batch.flush_loop),
        ("l2.retention", _l2_retention_loop),
        ("archive.write_queue", _archive_write_queue.drain_loop),
        ("ibkr.detail_reprice", lambda: _ibkr_reprice.detail_reprice_loop(
            get_ibkr_detail_symbols, run_ibkr, broadcast_trade_update, _find_ibkr_cache_row,
            lambda sym: _ibkr_ticks.is_fresh(sym, IBKR_DETAIL_STREAM_FRESH_SEC),
        )),
        ("observability.loop_lag", _loop_lag.sample_loop_lag_loop),
        ("nasdaq_halt_rss", _nasdaq_halt_feed.poll_loop),
        ("bot.ttl", ttl_loop),
        ("bot.breakers", breaker_loop),
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
