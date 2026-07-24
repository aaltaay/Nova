"""
IBKR-only market-data discovery for scanner candidate rosters and cold
snapshot hydration.

Two-step pipeline, per IB's own scanner API:
  1. One-shot scanner (reqScannerSubscription → wait → cancel) — up to 50
     ranked candidate symbols per scan code. Always cancels so we do not leak
     toward IBKR's 10 simultaneous API scanner subscription limit (Error 322).
     (https://interactivebrokers.github.io/tws-api/market_scanners.html)
  2. reqTickersAsync — one live snapshot quote per candidate, batched

Output rows preserve the scanner-row contract consumed by shared enrichment.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time

from constants import (
    GAPPER_MIN_GAP_PCT,
    IBKR_DISCOVERY_QUALIFY_TIMEOUT_SEC,
    IBKR_ERROR_SCANNER_SLOT_EXHAUSTED,
    IBKR_QUOTE_BATCH_TIMEOUT_SEC,
    IBKR_SCAN_ABOVE_PRICE,
    IBKR_SCAN_CODE_AH_GAINERS,
    IBKR_SCAN_CODE_GAINERS,
    IBKR_SCAN_CODE_GAPPERS,
    IBKR_SCAN_CODE_LOSERS,
    IBKR_SCAN_INSTRUMENT,
    IBKR_SCAN_LOCATION,
    IBKR_SCAN_MAX_ROWS,
    IBKR_SCAN_REQUEST_TIMEOUT_SEC,
    IBKR_SCAN_RESULT_TTL_SEC,
    SCANNER_MIN_PRICE,
)
from ibkr import client as _client
from ibkr.errors import IbkrDiscoveryError, IbkrScannerSlotExhaustedError, describe_exc
from metrics.op_metrics import timed, timed_async

logger = logging.getLogger(__name__)

_Stock = None
_ScannerSubscription = None
_ScanDataList = None
# Qualified Stock contracts reused across cold snapshot calls.
_qualified_contracts: dict[str, object] = {}
# Serialize cold reqTickersAsync so discovery/enrichment cannot fan out
# concurrent snapshot batches against the shared Gateway socket.
_snapshot_lock: asyncio.Lock | None = None
# Short-TTL result cache keyed by (scan_code, num_rows, below_price) — see
# IBKR_SCAN_RESULT_TTL_SEC. Coalesces duplicate one-shot scanner calls
# fired from independent loops (movers refresh, gapper fallback, HOD seed).
_scan_cache: dict[tuple[str, int, float | None], tuple[float, list[str]]] = {}
# Serialize one-shot scanners so we never hold more than one of IBKR's
# 10 simultaneous API scanner slots from this process (Error 322).
_scan_lock: asyncio.Lock | None = None
# reqIds for scanner subscriptions currently open from this process. Added
# right after reqScannerSubscription, discarded once _one_shot_scanner's
# finally has attempted cancellation — belt-and-suspenders for
# recover_scanner_slots() if that cancel itself raised (see PROBLEM_LOG
# 2026-07-23 IBKR Error 322 scanner subscription leak).
_inflight_scan_reqids: set[int] = set()


def reset_scan_cache() -> None:
    """Clear the short-TTL scan result cache (test isolation / facade reload)."""
    _scan_cache.clear()


def _get_scan_lock() -> asyncio.Lock:
    global _scan_lock
    if _scan_lock is None:
        _scan_lock = asyncio.Lock()
    return _scan_lock


def _get_snapshot_lock() -> asyncio.Lock:
    global _snapshot_lock
    if _snapshot_lock is None:
        _snapshot_lock = asyncio.Lock()
    return _snapshot_lock


def _load_ib_types() -> bool:
    global _Stock, _ScannerSubscription, _ScanDataList
    if _Stock is not None:
        return True
    try:
        from ib_async import ScanDataList, ScannerSubscription, Stock
        _Stock = Stock
        _ScannerSubscription = ScannerSubscription
        _ScanDataList = ScanDataList
        return True
    except ImportError:
        return False


def _clean(x: float | None) -> float | None:
    """IB leaves un-populated Ticker fields as NaN, not None."""
    if x is None:
        return None
    try:
        return None if math.isnan(x) else float(x)
    except TypeError:
        return None


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
    exception — indistinguishable from a genuinely empty market — so this
    listens on ``errorEvent`` directly rather than trusting the future.
    """
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
    # doubles that only stub reqScannerSubscription/wrapper.startReq do not.
    has_error_hook = hasattr(ib, "errorEvent")
    if has_error_hook:
        ib.errorEvent += _on_scan_error
    future = ib.wrapper.startReq(data_list.reqId, container=data_list)
    try:
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
    again here — it propagates to ``scan_symbols``'s generic exception
    handler and surfaces as a normal ``IbkrDiscoveryError`` failure.
    """
    try:
        return await _one_shot_scanner(ib, sub)
    except IbkrScannerSlotExhaustedError:
        recovered = recover_scanner_slots(ib)
        logger.warning(
            "IBKR scanner %s: slot exhausted (Error %d) — recovered %d slot(s), retrying once",
            scan_code, IBKR_ERROR_SCANNER_SLOT_EXHAUSTED, recovered,
        )
        return await _one_shot_scanner(ib, sub)


def recover_scanner_slots(ib) -> int:
    """Surgically reclaim leaked IBKR scanner-subscription slots.

    Cancels only (a) reqIds this process still has recorded as in-flight —
    belt-and-suspenders for a ``_one_shot_scanner`` finally-block cancel that
    itself raised — and (b) any entry in ib_async's own
    ``wrapper.reqId2Subscriber`` registry whose container is a
    ``ScanDataList`` (a real open scanner subscription IBKR is still holding
    for this clientId, regardless of which call created it). Never touches
    mktData/tick/order/bar subscribers, and never disconnects — this is the
    Error 322 recovery path, not a Gateway restart (see PROBLEM_LOG
    2026-07-23 IBKR scanner subscription leak).
    """
    if ib is None or not _load_ib_types():
        return 0
    wrapper = getattr(ib, "wrapper", None)
    registry = getattr(wrapper, "reqId2Subscriber", None) if wrapper is not None else None
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
                if isinstance(registry, dict):
                    registry.pop(req_id, None)
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
        logger.info("IBKR scanner %s → %d symbols", label, len(symbols))
    _scan_cache[cache_key] = (now_mono, list(symbols))
    return symbols


async def snapshot_quotes(
    symbols: list[str],
    *,
    timeout_sec: float = IBKR_QUOTE_BATCH_TIMEOUT_SEC,
    require_success: bool = False,
) -> dict[str, dict]:
    """Qualify + snapshot each symbol. Returns {symbol: {price, prev_close, open, volume}}.

    Reuses qualified contracts across ticks so the 1Hz table reprice loop does not
    pay qualifyContractsAsync on every second for the same universe.
    ``timeout_sec`` bounds a hung reqTickersAsync so table chunks stay responsive.

    When ``require_success`` is True (discovery/movers paths), disconnect /
    timeout / API failure raises ``IbkrDiscoveryError`` instead of returning ``{}``
    (which callers previously treated as a successful empty market).
    """
    if not symbols:
        return {}

    ib = _client.get_ib()
    if ib is None or not _load_ib_types():
        if require_success:
            raise IbkrDiscoveryError("IBKR not connected for snapshot quotes")
        return {}

    symbols = [s.upper() for s in symbols]
    missing = [s for s in symbols if s not in _qualified_contracts]
    if missing:
        contracts = [_Stock(sym, "SMART", "USD") for sym in missing]
        try:
            qualified = await asyncio.wait_for(
                ib.qualifyContractsAsync(*contracts),
                timeout=IBKR_DISCOVERY_QUALIFY_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError as exc:
            detail = f"qualify batch timed out after {IBKR_DISCOVERY_QUALIFY_TIMEOUT_SEC:.0f}s"
            logger.warning("IBKR: %s (%d symbols)", detail, len(contracts))
            if require_success:
                raise IbkrDiscoveryError(detail) from exc
            qualified = []
        except Exception as exc:
            detail = describe_exc(exc)
            logger.exception("IBKR: qualify batch failed: %s", detail)
            if require_success:
                raise IbkrDiscoveryError(f"qualify failed: {detail}") from exc
            qualified = []
        for c in qualified:
            if c is None:
                continue
            sym = getattr(c, "symbol", None)
            if sym:
                _qualified_contracts[sym.upper()] = c

    qualified = [_qualified_contracts[s] for s in symbols if s in _qualified_contracts]
    if not qualified:
        if require_success:
            raise IbkrDiscoveryError(
                f"no qualified contracts for {len(symbols)} snapshot symbol(s)"
            )
        return {}

    try:
        async with _get_snapshot_lock():
            async with timed("ibkr.snapshot_quotes"):
                tickers = await asyncio.wait_for(
                    ib.reqTickersAsync(*qualified),
                    timeout=max(0.5, float(timeout_sec)),
                )
    except asyncio.TimeoutError as exc:
        logger.warning(
            "IBKR: snapshot timeout (%.1fs) for %d symbols",
            timeout_sec, len(qualified),
        )
        if require_success:
            raise IbkrDiscoveryError(
                f"snapshot timeout ({timeout_sec:.1f}s) for {len(qualified)} symbols"
            ) from exc
        return {}
    except Exception as exc:
        detail = describe_exc(exc)
        logger.exception("IBKR: snapshot batch failed: %s", detail)
        if require_success:
            raise IbkrDiscoveryError(f"snapshot failed: {detail}") from exc
        return {}

    out: dict[str, dict] = {}
    for t in tickers:
        sym = getattr(t.contract, "symbol", None)
        if not sym:
            continue
        # Last preferred; close is a fallback print AND the usual prior close.
        # Do not require both — missing close used to drop the symbol entirely,
        # which blanked Stock View header price/change (symbol-only chip).
        price = _clean(t.last) or _clean(t.close)
        prev_close = _clean(t.close)
        if price is None:
            continue
        out[sym] = {
            "price": price,
            "prev_close": prev_close,
            "open": _clean(t.open),
            "high": _clean(getattr(t, "high", None)),
            "volume": int(_clean(t.volume) or 0),
            "exchange": getattr(t.contract, "primaryExchange", None) or None,
        }
    return out


def chunk_symbols(symbols: list[str], chunk_size: int) -> list[list[str]]:
    """Split symbols into fixed-size batches for progressive table reprice."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    ordered = [s for s in symbols if s]
    return [ordered[i : i + chunk_size] for i in range(0, len(ordered), chunk_size)]


def _meets_min_gap(gap_frac: float | None) -> bool:
    return gap_frac is not None and gap_frac * 100 >= GAPPER_MIN_GAP_PCT


async def get_gappers() -> list[dict]:
    """Gap scan: current price vs prior session close.

    Prefers ``TOP_OPEN_PERC_GAIN`` (open vs prior close). Before the regular
    open IB often returns an empty/cancelled result for that code — fall back
    to ``TOP_PERC_GAIN`` (last vs prior close), which is the correct premarket
    gap definition and matches what traders mean by "gappers" at 4:00–9:30 ET.
    """
    symbols = await scan_symbols(IBKR_SCAN_CODE_GAPPERS)
    if not symbols:
        logger.info(
            "IBKR gappers: %s empty — falling back to %s (premarket / pre-open)",
            IBKR_SCAN_CODE_GAPPERS,
            IBKR_SCAN_CODE_GAINERS,
        )
        symbols = await scan_symbols(IBKR_SCAN_CODE_GAINERS)
    if not symbols:
        logger.info("IBKR gappers: both scanner codes returned 0 symbols (empty market)")
        return []
    quotes = await snapshot_quotes(symbols, require_success=True)

    rows: list[dict] = []
    for sym, q in quotes.items():
        price, prev_close = q["price"], q["prev_close"]
        if price < SCANNER_MIN_PRICE or not prev_close:
            continue
        gap_frac = (price - prev_close) / prev_close
        if not _meets_min_gap(gap_frac):
            continue
        rows.append({
            "symbol": sym,
            "price": price,
            "prev_close": prev_close,
            "change_pct": gap_frac,
            "change_abs": price - prev_close,
            "previous_close": prev_close,   # WS handler compat, mirrors Alpaca path
            "current_price": price,         # WS handler compat, mirrors Alpaca path
            "gap_percent": gap_frac,
            "volume": q["volume"],
            "exchange": q.get("exchange"),
        })
    rows.sort(key=lambda x: x["gap_percent"], reverse=True)
    logger.info("IBKR gappers: %d rows after %.0f%% filter", len(rows), GAPPER_MIN_GAP_PCT)
    return rows


async def _get_movers(
    scan_code: str, reverse: bool, *, below_price: float | None = None,
) -> list[dict]:
    symbols = await scan_symbols(scan_code, below_price=below_price)
    if not symbols:
        return []
    quotes = await snapshot_quotes(symbols, require_success=True)

    rows: list[dict] = []
    for sym, q in quotes.items():
        price, prev_close = q["price"], q["prev_close"]
        if price < SCANNER_MIN_PRICE or not prev_close:
            continue
        change_pct = (price - prev_close) / prev_close
        open_price = q.get("open")
        gap_percent = (
            (open_price - prev_close) / prev_close
            if open_price and prev_close else None
        )
        rows.append({
            "symbol": sym,
            "price": price,
            "change_pct": change_pct,
            "change_abs": price - prev_close,
            "volume": q["volume"],
            "gap_percent": gap_percent,
            "prev_close": prev_close,
            "exchange": q.get("exchange"),
        })
    rows.sort(key=lambda x: x["change_pct"], reverse=reverse)
    return rows


async def get_gainers() -> list[dict]:
    """Top % gainers, intraday (current price vs prior close)."""
    return await _get_movers(IBKR_SCAN_CODE_GAINERS, reverse=True)


async def get_losers() -> list[dict]:
    """Top % losers, intraday (current price vs prior close)."""
    return await _get_movers(IBKR_SCAN_CODE_LOSERS, reverse=False)


async def get_afterhours_gainers() -> list[dict]:
    """Dedicated after-hours movers scan (TOP_AFTER_HOURS_PERC_GAIN).

    Distinct IB scan universe from TOP_PERC_GAIN — the After Hours tab's
    primary source. Reshaping ``get_gainers()``'s intraday result is a
    fallback only, used when this scan is empty.
    """
    return await _get_movers(IBKR_SCAN_CODE_AH_GAINERS, reverse=True)


def reprice_gapper_row(g: dict, q: dict) -> dict:
    """Apply a fresh snapshot_quotes() entry to an existing gapper row,
    recomputing change fields from the row's own prev_close so price and
    change_pct/change_abs never drift apart (see main.py _reprice_ibkr_caches)."""
    prev_close = g.get("previous_close") or g.get("prev_close") or q.get("prev_close")
    price = q["price"]
    if not prev_close:
        return g
    gap_frac = (price - prev_close) / prev_close
    return {
        **g,
        "price": price,
        "current_price": price,
        "change_pct": gap_frac,
        "change_abs": price - prev_close,
        "gap_percent": gap_frac,
        "volume": q.get("volume", g.get("volume", 0)),
    }


def reprice_mover_row(m: dict, q: dict) -> dict:
    """Gainer/loser counterpart to reprice_gapper_row."""
    prev_close = m.get("prev_close") or q.get("prev_close")
    price = q["price"]
    if not prev_close:
        return m
    change_pct = (price - prev_close) / prev_close
    return {
        **m,
        "price": price,
        "change_pct": change_pct,
        "change_abs": price - prev_close,
        "volume": q.get("volume", m.get("volume", 0)),
    }
