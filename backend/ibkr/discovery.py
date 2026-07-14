"""
IBKR market-data discovery — a clean, self-contained counterpart to
Alpaca's gapper/gainer/loser pipeline in main.py (_run_discovery_scan /
_run_gainers_update). Alpaca stays the default and is never removed —
this module only runs when DISCOVERY_PROVIDER=ibkr (see constants.py and
knowledge/obsidian/03-Nova-Decisions/Scanner-Provider-IBKR-Primary.md).

Two-step pipeline, per IB's own scanner API:
  1. reqScannerDataAsync — up to 50 ranked candidate symbols per scan code
     (https://interactivebrokers.github.io/tws-api/market_scanners.html)
  2. reqTickersAsync     — one live snapshot quote per candidate, batched

Output rows use the exact same dict keys Alpaca's path already produces
(see main.py's _compute_gappers / _build_mover_entry), so the existing
news / fundamentals / RVOL / exchange enrichment step in main.py works
unchanged regardless of which provider found the symbols.
"""
from __future__ import annotations

import logging
import math

from constants import (
    GAPPER_MIN_GAP_PCT,
    IBKR_SCAN_ABOVE_PRICE,
    IBKR_SCAN_CODE_GAINERS,
    IBKR_SCAN_CODE_GAPPERS,
    IBKR_SCAN_CODE_LOSERS,
    IBKR_SCAN_INSTRUMENT,
    IBKR_SCAN_LOCATION,
    IBKR_SCAN_MAX_ROWS,
    SCANNER_MIN_PRICE,
)
from ibkr import client as _client

logger = logging.getLogger(__name__)

_Stock = None
_ScannerSubscription = None


def _load_ib_types() -> bool:
    global _Stock, _ScannerSubscription
    if _Stock is not None:
        return True
    try:
        from ib_async import ScannerSubscription, Stock
        _Stock = Stock
        _ScannerSubscription = ScannerSubscription
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


async def scan_symbols(scan_code: str, num_rows: int = IBKR_SCAN_MAX_ROWS) -> list[str]:
    """One-shot market scan. Returns up to num_rows unique ranked symbols."""
    ib = _client.get_ib()
    if ib is None or not _load_ib_types():
        return []
    sub = _ScannerSubscription(
        numberOfRows=num_rows,
        instrument=IBKR_SCAN_INSTRUMENT,
        locationCode=IBKR_SCAN_LOCATION,
        scanCode=scan_code,
        abovePrice=IBKR_SCAN_ABOVE_PRICE,
    )
    try:
        rows = await ib.reqScannerDataAsync(sub)
    except Exception as exc:
        logger.error("IBKR scanner %s failed: %s", scan_code, exc)
        return []

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
    if not symbols:
        logger.warning(
            "IBKR scanner %s returned 0 symbols (common for TOP_OPEN_PERC_GAIN before RTH open)",
            scan_code,
        )
    else:
        logger.info("IBKR scanner %s → %d symbols", scan_code, len(symbols))
    return symbols


async def snapshot_quotes(symbols: list[str]) -> dict[str, dict]:
    """Qualify + snapshot each symbol. Returns {symbol: {price, prev_close, open, volume}}."""
    ib = _client.get_ib()
    if ib is None or not symbols or not _load_ib_types():
        return {}

    contracts = [_Stock(sym, "SMART", "USD") for sym in symbols]
    try:
        qualified = await ib.qualifyContractsAsync(*contracts)
    except Exception as exc:
        logger.error("IBKR: qualify batch failed: %s", exc)
        return {}
    qualified = [c for c in qualified if c is not None]
    if not qualified:
        return {}

    try:
        tickers = await ib.reqTickersAsync(*qualified)
    except Exception as exc:
        logger.error("IBKR: snapshot batch failed: %s", exc)
        return {}

    out: dict[str, dict] = {}
    for t in tickers:
        sym = getattr(t.contract, "symbol", None)
        if not sym:
            continue
        price = _clean(t.last) or _clean(t.close)
        prev_close = _clean(t.close)
        if price is None or prev_close is None:
            continue
        out[sym] = {
            "price": price,
            "prev_close": prev_close,
            "open": _clean(t.open),
            "volume": int(_clean(t.volume) or 0),
            "exchange": getattr(t.contract, "primaryExchange", None) or None,
        }
    return out


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
    quotes = await snapshot_quotes(symbols)

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


async def _get_movers(scan_code: str, reverse: bool) -> list[dict]:
    symbols = await scan_symbols(scan_code)
    quotes = await snapshot_quotes(symbols)

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
