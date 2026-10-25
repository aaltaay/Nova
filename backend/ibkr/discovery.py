"""
IBKR-only market-data discovery for scanner candidate rosters and cold
snapshot hydration.

Two-step pipeline, per IB's own scanner API:
  1. One-shot scanner (reqScannerSubscription -> wait -> cancel) -- up to 50
     ranked candidate symbols per scan code. Always cancels so we do not leak
     toward IBKR's 10 simultaneous API scanner subscription limit (Error 322).
     (https://interactivebrokers.github.io/tws-api/market_scanners.html)
  2. reqTickersAsync -- one live snapshot quote per candidate, batched
     (implemented in ``ibkr/snapshot_quotes.py`` and re-exported here).

Output rows preserve the scanner-row contract consumed by shared enrichment.
"""
from __future__ import annotations

import asyncio
import logging
import time

from constants import (
    IBKR_DISCOVERY_QUALIFY_TIMEOUT_SEC,  # noqa: F401 -- read via module attr by snapshot_quotes/tests
    IBKR_ERROR_SCANNER_SLOT_EXHAUSTED,
    IBKR_SCAN_ABOVE_PRICE,
    IBKR_SCAN_INSTRUMENT,
    IBKR_SCAN_LOCATION,
    IBKR_SCAN_MAX_ROWS,
    IBKR_SCAN_REQUEST_TIMEOUT_SEC,
    IBKR_SCAN_RESULT_TTL_SEC,
)
from ibkr import client as _client
from ibkr.errors import IbkrDiscoveryError, IbkrScannerSlotExhaustedError, describe_exc
from ibkr.qualified_contracts import (  # noqa: F401 -- the cache snapshot_quotes reuses
    _qualified_contracts,
    remember_qualified_contract,
    take_qualified_contract,
)
from ibkr.snapshot_quotes import (  # noqa: F401 -- compatibility re-exports (ADR 004)
    _cancel_snapshot_tickers,
    _get_movers,
    _log_budget_spent,
    chunk_symbols,
    get_afterhours_gainers,
    get_gainers,
    get_losers,
    snapshot_quotes,
)
from metrics.op_metrics import timed_async

logger = logging.getLogger(__name__)

_Stock = None
_ScannerSubscription = None
_ScanDataList = None
_ScannerSub = None
_ReqIdKey = None
# Short-TTL result cache keyed by (scan_code, num_rows, below_price) -- see
# IBKR_SCAN_RESULT_TTL_SEC. Coalesces duplicate one-shot scanner calls
# fired from independent loops (movers refresh, gapper fallback, HOD seed).
_scan_cache: dict[tuple[str, int, float | None], tuple[float, list[str]]] = {}
# Serialize one-shot scanners so we never hold more than one of IBKR's
# 10 simultaneous API scanner slots from this process (Error 322).
_scan_lock: asyncio.Lock | None = None
# reqIds for scanner subscriptions currently open from this process. Added
# right after reqScannerSubscription, discarded once _one_shot_scanner's
# finally has attempted cancellation -- belt-and-suspenders for
# recover_scanner_slots() if that cancel itself raised (see PROBLEM_LOG
# 2026-07-23 IBKR Error 322 scanner subscription leak).
_inflight_scan_reqids: set[int] = set()


def reset_scan_cache() -> None:
    """Clear the short-TTL scan result cache (test isolation / facade reload)."""
    _scan_cache.clear()


def clear_inflight_scan_reqids(*, reason: str = "") -> int:
    """Drop one-shot scanner reqIds after a full reconnect.

    A new ``IB()`` invalidates those ids. Leaving them lets
    ``recover_scanner_slots`` cancel ids the new session never issued (D-039).
    """
    n = len(_inflight_scan_reqids)
    _inflight_scan_reqids.clear()
    if n:
        logger.warning(
            "IBKR discovery: cleared %d stale scanner reqId(s) (%s)",
            n,
            reason or "unspecified",
        )
    return n


def _get_scan_lock() -> asyncio.Lock:
    global _scan_lock
    if _scan_lock is None:
        _scan_lock = asyncio.Lock()
    return _scan_lock


def _load_ib_types() -> bool:
    global _Stock, _ScannerSubscription, _ScanDataList, _ScannerSub, _ReqIdKey
    if _Stock is not None:
        return True
    try:
        from ib_async import ScanDataList, ScannerSubscription, Stock
        _Stock = Stock
        _ScannerSubscription = ScannerSubscription
        _ScanDataList = ScanDataList
        # ScannerSub / ReqIdKey moved with the typed-registry refactor
        # (ib_async pin c9f4c14, 2026-07-30) that dropped Wrapper.startReq /
        # wrapper.reqId2Subscriber -- see PROBLEM_LOG 2026-07-31. Both are
        # optional: older ib_async releases still work via the legacy
        # startReq fallback in _open_scan_future / recover_scanner_slots.
        try:
            from ib_async._subscriptions import ScannerSub
            _ScannerSub = ScannerSub
        except ImportError:
            _ScannerSub = None
        try:
            from ib_async._requests import ReqIdKey
            _ReqIdKey = ReqIdKey
        except ImportError:
            _ReqIdKey = None
        return True
    except ImportError:
        return False


def _open_scan_future(ib, data_list) -> asyncio.Future:
    """Open the awaitable future for a just-issued scanner subscription.

    ``ib_async``'s typed ``RequestRegistry`` (pin c9f4c14, 2026-07-30)
    replaced ``Wrapper.startReq`` with ``wrapper.requests.open(key, ...)``.
    Prefer the new API; fall back to the legacy facade for older pins so a
    partial rollback does not also need a code change. Raises
    ``IbkrDiscoveryError`` with a clear message if neither exists -- this is
    the loud failure this helper exists to prevent (see PROBLEM_LOG
    2026-07-31 empty gappers/gainers after startReq removal).
    """
    requests_registry = getattr(ib.wrapper, "requests", None)
    if requests_registry is not None and _ReqIdKey is not None:
        req, _ = requests_registry.open(_ReqIdKey(data_list.reqId), container=data_list)
        return req.future
    start_req = getattr(ib.wrapper, "startReq", None)
    if callable(start_req):
        return start_req(data_list.reqId, container=data_list)
    raise IbkrDiscoveryError(
        "ib_async Wrapper exposes neither requests.open nor startReq -- "
        "scanner API surface changed; update ibkr/discovery.py._open_scan_future"
    )


@timed_async("ibkr.scanner.oneshot")
async def _one_shot_scanner(ib, sub) -> list:
    """Open one IBKR scanner subscription, wait for results, always cancel.

    ``ib_async.IB.reqScannerDataAsync`` only cancels *after* the future
    completes. Wrapping it in ``asyncio.wait_for`` abandons the await on
    timeout **without** calling ``cancelScannerSubscription``, which leaks
    toward IBKR Error 322 (max 10 simultaneous API scanner subscriptions).
    Once those slots are full, every later scan returns 0 symbols / Error 365
    and HOD seeds + losers look permanently empty.

    Raises ``IbkrScannerSlotExhaustedError`` when IBKR itself rejects the
    request with Error 322. With ``RaiseRequestErrors=False`` (ib_async's
    default) that error resolves the request's future to ``[]`` with no
    exception -- indistinguishable from a genuinely empty market -- so this
    listens on ``errorEvent`` directly rather than trusting the future.

    Nothing that can raise sits between the subscribe and the ``try`` whose
    ``finally`` cancels it: the Market page's movers scan called this without
    ``_load_ib_types``, ``_open_scan_future`` raised after the subscribe, and
    each refresh leaked a slot until all ten were gone (2026-10-23).
    """
    _load_ib_types()
    data_list = ib.reqScannerSubscription(sub)
    req_id = getattr(data_list, "reqId", None)
    if req_id is not None:
        _inflight_scan_reqids.add(req_id)

    slot_exhausted = False

    def _on_scan_error(err_req_id: int, error_code: int, *_rest: object) -> None:
        nonlocal slot_exhausted
        if error_code == IBKR_ERROR_SCANNER_SLOT_EXHAUSTED and err_req_id == req_id:
            slot_exhausted = True

    # hasattr-guarded: real ib_async.IB always has errorEvent; minimal test
    # doubles that only stub reqScannerSubscription/wrapper.requests do not.
    has_error_hook = hasattr(ib, "errorEvent")
    if has_error_hook:
        ib.errorEvent += _on_scan_error
    try:
        future = _open_scan_future(ib, data_list)
        await asyncio.wait_for(future, timeout=IBKR_SCAN_REQUEST_TIMEOUT_SEC)
        if slot_exhausted:
            raise IbkrScannerSlotExhaustedError(
                f"IBKR Error {IBKR_ERROR_SCANNER_SLOT_EXHAUSTED}: no free scanner "
                f"subscription slot (reqId={req_id})"
            )
        return list(future.result() or [])
    except asyncio.TimeoutError:
        logger.warning(
            "IBKR scanner request timed out after %.0fs (cancelling subscription reqId=%s)",
            IBKR_SCAN_REQUEST_TIMEOUT_SEC,
            getattr(data_list, "reqId", "?"),
        )
        raise
    finally:
        if has_error_hook:
            ib.errorEvent -= _on_scan_error
        try:
            ib.cancelScannerSubscription(data_list)
        except Exception:
            try:
                ib.client.cancelScannerSubscription(data_list.reqId)
            except Exception:
                logger.debug(
                    "IBKR scanner cancel failed for reqId=%s",
                    getattr(data_list, "reqId", None),
                    exc_info=True,
                )
        if req_id is not None:
            _inflight_scan_reqids.discard(req_id)


async def _scan_once_with_recovery(ib, sub, scan_code: str) -> list:
    """Run one scan attempt; on Error 322 (slot exhaustion) recover leaked
    scanner slots and retry exactly once under the same ``_scan_lock`` hold.

    A second consecutive ``IbkrScannerSlotExhaustedError`` is not retried
    again here -- it propagates to ``scan_symbols``'s generic exception
    handler and surfaces as a normal ``IbkrDiscoveryError`` failure.
    """
    try:
        return await _one_shot_scanner(ib, sub)
    except IbkrScannerSlotExhaustedError:
        recovered = recover_scanner_slots(ib)
        logger.warning(
            "IBKR scanner %s: slot exhausted (Error %d) -- recovered %d slot(s), retrying once",
            scan_code, IBKR_ERROR_SCANNER_SLOT_EXHAUSTED, recovered,
        )
        return await _one_shot_scanner(ib, sub)


def recover_scanner_slots(ib) -> int:
    """Surgically reclaim leaked IBKR scanner-subscription slots.

    Cancels only (a) reqIds this process still has recorded as in-flight --
    belt-and-suspenders for a ``_one_shot_scanner`` finally-block cancel that
    itself raised -- and (b) any live ``ScannerSub`` in ib_async's own
    subscription registry (``wrapper.subscriptions.subs_of_type``), each of
    which is a real open scanner subscription IBKR is still holding for this
    clientId, regardless of which call created it. Never touches
    mktData/tick/order/bar subscribers, and never disconnects -- this is the
    Error 322 recovery path, not a Gateway restart (see PROBLEM_LOG
    2026-07-23 IBKR scanner subscription leak).

    Uses ``wrapper.subscriptions.subs_of_type(ScannerSub)`` (typed-registry
    API, ib_async pin c9f4c14+); falls back to the legacy
    ``wrapper.reqId2Subscriber`` dict for older pins (see PROBLEM_LOG
    2026-07-31 startReq/registry removal).
    """
    if ib is None or not _load_ib_types():
        return 0
    wrapper = getattr(ib, "wrapper", None)
    # ADR 008: never cancel currently-desired persistent leases.
    try:
        from ibkr.scanner_stream import persistent_reqids as _persistent_reqids
        protected = _persistent_reqids()
    except Exception:
        protected = set()

    candidates: dict[int, object] = {
        req_id: None
        for req_id in list(_inflight_scan_reqids)
        if req_id not in protected
    }

    subscriptions = getattr(wrapper, "subscriptions", None) if wrapper is not None else None
    subs_of_type = getattr(subscriptions, "subs_of_type", None) if subscriptions is not None else None
    if callable(subs_of_type) and _ScannerSub is not None:
        for sub in subs_of_type(_ScannerSub):
            req_id = getattr(sub, "reqId", None)
            if req_id is None or req_id in protected:
                continue
            candidates[req_id] = getattr(sub, "dataList", None)
    else:
        # Legacy ib_async (pre-c9f4c14): reqId2Subscriber maps reqId -> ScanDataList.
        registry = getattr(wrapper, "reqId2Subscriber", None) if wrapper is not None else None
        if isinstance(registry, dict):
            for req_id, subscriber in list(registry.items()):
                if req_id in protected:
                    continue
                if isinstance(subscriber, _ScanDataList):
                    candidates[req_id] = subscriber

    recovered = 0
    for req_id, subscriber in candidates.items():
        try:
            if subscriber is not None:
                ib.cancelScannerSubscription(subscriber)
            else:
                ib.client.cancelScannerSubscription(req_id)
            recovered += 1
        except Exception:
            logger.debug(
                "recover_scanner_slots: cancel failed for reqId=%s", req_id, exc_info=True,
            )
        finally:
            _inflight_scan_reqids.discard(req_id)

    if recovered:
        logger.warning(
            "IBKR: recover_scanner_slots reclaimed %d leaked scanner subscription slot(s)",
            recovered,
        )
    return recovered


async def scan_symbols(
    scan_code: str,
    num_rows: int = IBKR_SCAN_MAX_ROWS,
    *,
    below_price: float | None = None,
) -> list[str]:
    """One-shot market scan. Returns up to num_rows unique ranked symbols.

    Raises ``IbkrDiscoveryError`` on disconnect / API failure.
    Returns ``[]`` only when IB answered successfully with zero symbols.
    """
    cache_key = (scan_code, num_rows, float(below_price) if below_price else None)
    cached = _scan_cache.get(cache_key)
    now_mono = time.monotonic()
    if cached is not None and (now_mono - cached[0]) < IBKR_SCAN_RESULT_TTL_SEC:
        return list(cached[1])

    ib = _client.get_ib()
    if ib is None or not _load_ib_types():
        raise IbkrDiscoveryError(
            f"IBKR not connected for scanner {scan_code} "
            f"(ib={'none' if ib is None else 'present'})"
        )
    sub = _ScannerSubscription(
        numberOfRows=num_rows,
        instrument=IBKR_SCAN_INSTRUMENT,
        locationCode=IBKR_SCAN_LOCATION,
        scanCode=scan_code,
        abovePrice=IBKR_SCAN_ABOVE_PRICE,
    )
    if below_price is not None and float(below_price) > 0:
        sub.belowPrice = float(below_price)

    async with _get_scan_lock():
        try:
            rows = await _scan_once_with_recovery(ib, sub, scan_code)
        except asyncio.TimeoutError as exc:
            raise IbkrDiscoveryError(
                f"scanner {scan_code} timed out after {IBKR_SCAN_REQUEST_TIMEOUT_SEC:.0f}s"
            ) from exc
        except Exception as exc:
            detail = describe_exc(exc)
            logger.exception("IBKR scanner %s failed: %s", scan_code, detail)
            raise IbkrDiscoveryError(f"scanner {scan_code} failed: {detail}") from exc

    symbols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        try:
            sym = row.contractDetails.contract.symbol
        except AttributeError:
            continue
        if sym and sym not in seen:
            seen.add(sym)
            symbols.append(sym)
    label = scan_code
    if below_price is not None and float(below_price) > 0:
        label = f"{scan_code}(belowPrice={float(below_price):g})"
    if not symbols:
        logger.warning(
            "IBKR scanner %s returned 0 symbols (common for TOP_OPEN_PERC_GAIN before RTH open)",
            label,
        )
    else:
        logger.info("IBKR scanner %s -> %d symbols", label, len(symbols))
    _scan_cache[cache_key] = (now_mono, list(symbols))
    return symbols
