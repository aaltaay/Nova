"""Persistent IBKR scanner subscriptions (ADR 008).

Owns ``ScanDataList`` handles for the process lifetime. Desired set by period:
Premarket = Gainers + Gappers; RTH = Gainers + Losers; AH = AH Gainers; Closed = none.

Shadow by default (``IBKR_SCANNER_PERSISTENT_AUTHORITATIVE=false``): builds
rosters for parity evidence without replacing one-shot ``scan_loop`` writers.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from constants import (
    IBKR_SCAN_ABOVE_PRICE,
    IBKR_SCAN_CODE_GAPPERS,
    IBKR_SCAN_INSTRUMENT,
    IBKR_SCAN_LOCATION,
    IBKR_SCAN_MAX_ROWS,
    IBKR_SCAN_REQUEST_TIMEOUT_SEC,
    IBKR_SCANNER_RECONCILE_SEC,
    IBKR_SCANNER_WATCHDOG_CADENCE_MULT,
    IBKR_SCANNER_WATCHDOG_MIN_SEC,
)
from ibkr import client as _client
from ibkr import scanner_hydrate as _hydrate
from ibkr import scanner_session as _session
from metrics.op_metrics import record_since, timed_sync
from runtime_state import get_runtime_state

logger = logging.getLogger(__name__)

_ScannerSubscription = None
_persistent_reqids: dict[int, str] = {}
_leases: dict[str, "_Lease"] = {}
_epoch = 0
_shadow: dict[str, list[dict]] = {}
_pending_hydrate: dict[str, tuple[list[str], int]] = {}
_hydrate_task: asyncio.Task | None = None


@dataclass
class _Lease:
    table: str
    scan_code: str
    data_list: Any = None
    req_id: int | None = None
    generation: int = 0
    epoch: int = 0
    session_key: str = ""
    last_batch_mono: float = 0.0
    batch_intervals: list[float] = field(default_factory=list)
    first_batch_event: asyncio.Event | None = None
    listener: Any = None


def persistent_reqids() -> set[int]:
    """ReqIds of currently-desired persistent leases (Error-322 recovery fence)."""
    return set(_persistent_reqids)


def shadow_roster(table: str) -> list[dict]:
    return list(_shadow.get(table) or [])


def bump_epoch() -> int:
    global _epoch
    _epoch += 1
    return _epoch


def _load_types() -> bool:
    global _ScannerSubscription
    if _ScannerSubscription is not None:
        return True
    try:
        from ib_async import ScannerSubscription
        _ScannerSubscription = ScannerSubscription
        return True
    except ImportError:
        return False


def _symbols_from_rows(rows: list) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        try:
            sym = row.contractDetails.contract.symbol
        except AttributeError:
            continue
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def _on_batch(lease: _Lease, rows: list) -> None:
    """IB callback — copy symbols immediately; hydrate off the event thread."""
    if lease.generation != _client.current_generation() or lease.epoch != _epoch:
        return
    if lease.session_key != _session.session_key_et():
        return
    symbols = _symbols_from_rows(list(rows or []))
    now_m = time.monotonic()
    if lease.last_batch_mono > 0:
        lease.batch_intervals.append(now_m - lease.last_batch_mono)
        lease.batch_intervals = lease.batch_intervals[-20:]
    lease.last_batch_mono = now_m
    if lease.first_batch_event is not None and not lease.first_batch_event.is_set():
        lease.first_batch_event.set()
    if lease.table == _session.TABLE_GAPPERS and not symbols:
        pending_gainers = _pending_hydrate.get(_session.TABLE_GAINERS)
        symbols = list(pending_gainers[0] if pending_gainers else []) or [
            r["symbol"] for r in (_shadow.get(_session.TABLE_GAINERS) or [])
        ]
        if symbols:
            logger.info(
                "scanner_stream: %s empty — derive from gainers (%d)",
                IBKR_SCAN_CODE_GAPPERS, len(symbols),
            )
    _pending_hydrate[lease.table] = (symbols, time.perf_counter_ns())
    _schedule_hydrate()


def _schedule_hydrate() -> None:
    global _hydrate_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _hydrate_task is not None and not _hydrate_task.done():
        return
    _hydrate_task = loop.create_task(_hydrate_pending(), name="scanner_stream.hydrate")


async def _hydrate_pending() -> None:
    await asyncio.sleep(0)
    pending = dict(_pending_hydrate)
    _pending_hydrate.clear()
    for table, (symbols, started_ns) in pending.items():
        lease = _leases.get(table)
        if lease is None:
            continue
        try:
            committed = await _hydrate.commit_table(
                table=table,
                symbols=symbols,
                lease_generation=lease.generation,
                lease_epoch=lease.epoch,
                lease_session_key=lease.session_key,
                epoch=_epoch,
                shadow=_shadow,
            )
        except Exception:
            record_since("ibkr.scanner.pipeline", started_ns, ok=False)
            logger.exception("scanner_stream: hydrate failed for %s", table)
        else:
            if committed is not None:
                record_since("ibkr.scanner.pipeline", started_ns, ok=committed)


async def _open_lease(table: str, scan_code: str) -> _Lease | None:
    ib = _client.get_ib()
    if ib is None or not _load_types() or not _client.is_ready():
        return None
    sub = _ScannerSubscription(
        numberOfRows=IBKR_SCAN_MAX_ROWS,
        instrument=IBKR_SCAN_INSTRUMENT,
        locationCode=IBKR_SCAN_LOCATION,
        scanCode=scan_code,
        abovePrice=IBKR_SCAN_ABOVE_PRICE,
    )
    with timed_sync("ibkr.scanner.persistent_subscribe"):
        data_list = ib.reqScannerSubscription(sub)
    req_id = getattr(data_list, "reqId", None)
    lease = _Lease(
        table=table,
        scan_code=scan_code,
        data_list=data_list,
        req_id=req_id,
        generation=_client.current_generation(),
        epoch=_epoch,
        session_key=_session.session_key_et(),
        first_batch_event=asyncio.Event(),
    )

    def _listener(*_a, lease=lease, dl=data_list):
        try:
            payload = list(dl)
        except TypeError:
            payload = []
        _on_batch(lease, payload)

    lease.listener = _listener
    if hasattr(data_list, "updateEvent"):
        data_list.updateEvent += _listener
    if req_id is not None:
        _persistent_reqids[req_id] = table
    _leases[table] = lease
    logger.info(
        "scanner_stream: opened %s (%s) reqId=%s gen=%d epoch=%d",
        table, scan_code, req_id, lease.generation, lease.epoch,
    )
    try:
        await asyncio.wait_for(
            lease.first_batch_event.wait(), timeout=IBKR_SCAN_REQUEST_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "scanner_stream: first batch timeout for %s after %.0fs",
            table, IBKR_SCAN_REQUEST_TIMEOUT_SEC,
        )
    return lease


def _cancel_lease(table: str, *, freeze_first: bool = False) -> None:
    lease = _leases.pop(table, None)
    if lease is None:
        return
    if freeze_first:
        try:
            _session.freeze_table(get_runtime_state(), table, source="lease_cancel")
        except Exception:
            logger.debug("scanner_stream: freeze on cancel failed", exc_info=True)
    ib = _client.get_ib()
    if lease.listener is not None and lease.data_list is not None:
        try:
            if hasattr(lease.data_list, "updateEvent"):
                lease.data_list.updateEvent -= lease.listener
        except Exception:
            pass
    if ib is not None and lease.data_list is not None:
        try:
            ib.cancelScannerSubscription(lease.data_list)
        except Exception:
            try:
                if lease.req_id is not None:
                    ib.client.cancelScannerSubscription(lease.req_id)
            except Exception:
                logger.debug(
                    "scanner_stream: cancel failed reqId=%s", lease.req_id, exc_info=True,
                )
    if lease.req_id is not None:
        _persistent_reqids.pop(lease.req_id, None)
    logger.info("scanner_stream: cancelled %s reqId=%s", table, lease.req_id)


async def reconcile_leases() -> None:
    """Open/cancel leases to match desired set; freeze before cancelling."""
    if not _client.is_ready() or not _load_types():
        return
    desired = {
        table: code for table, code in _session.desired_leases()
        if _session.table_is_live(table)
    }
    for table in list(_leases):
        if table not in desired:
            _cancel_lease(table, freeze_first=_session.table_should_be_frozen(table))
    gen = _client.current_generation()
    for table, code in desired.items():
        existing = _leases.get(table)
        if existing is not None:
            if (
                existing.scan_code == code
                and existing.generation == gen
                and existing.epoch == _epoch
            ):
                continue
            _cancel_lease(table, freeze_first=False)
        await _open_lease(table, code)


async def _watchdog_once() -> None:
    for table, lease in list(_leases.items()):
        if lease.last_batch_mono <= 0:
            continue
        age = time.monotonic() - lease.last_batch_mono
        cadence = (
            sum(lease.batch_intervals) / len(lease.batch_intervals)
            if lease.batch_intervals else IBKR_SCANNER_WATCHDOG_MIN_SEC
        )
        limit = max(
            IBKR_SCANNER_WATCHDOG_MIN_SEC,
            IBKR_SCANNER_WATCHDOG_CADENCE_MULT * cadence,
        )
        if age <= limit:
            continue
        logger.warning(
            "scanner_stream: watchdog resubscribe %s (batch age %.0fs > %.0fs)",
            table, age, limit,
        )
        code = lease.scan_code
        _cancel_lease(table, freeze_first=False)
        await _open_lease(table, code)


async def manager_loop() -> None:
    """Background reconcile + watchdog. Started from app lifespan when enabled."""
    last_gen = _client.current_generation()
    last_shadow_log = 0.0
    while True:
        try:
            gen = _client.current_generation()
            if gen != last_gen:
                bump_epoch()
                for table in list(_leases):
                    _cancel_lease(table, freeze_first=False)
                last_gen = gen
            _session.reconcile_session_tables(get_runtime_state())
            await reconcile_leases()
            await _watchdog_once()
            now_m = time.monotonic()
            if (
                now_m - last_shadow_log >= 60.0
                and not _session.is_persistent_authoritative()
            ):
                _hydrate.log_shadow_parity(_shadow, _persistent_reqids)
                last_shadow_log = now_m
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scanner_stream: manager iteration failed")
        await asyncio.sleep(float(IBKR_SCANNER_RECONCILE_SEC))


async def shutdown() -> None:
    for table in list(_leases):
        _cancel_lease(table, freeze_first=False)
    _shadow.clear()
    _pending_hydrate.clear()
    _hydrate.reset_known()
