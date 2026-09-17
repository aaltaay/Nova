"""Nasdaq Trade Halt RSS poller (owner of the in-memory overlay cache).

Owner: this module.
Invalidation: successful fetch replaces the cache; ``reset()`` (tests).
schema_version: 1 (in-memory only -- not persisted).

Polls the official RSS at most once per minute. Failed fetches keep the
last good symbol rows for IBKR+clock but mark exchange status down so
the chip never invents resume times. MWCB Level 1/2/3 is desk-wide.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

import requests

from constants import (
    NASDAQ_TRADE_HALT_RSS_HTTP_TIMEOUT_SEC,
    NASDAQ_TRADE_HALT_RSS_POLL_SEC,
    NASDAQ_TRADE_HALT_RSS_URL,
    NASDAQ_TRADE_HALT_RSS_USER_AGENT,
)
from ibkr.nasdaq_halt_rss import (
    HaltRssRow,
    better_overlay_row,
    parse_trade_halt_rss,
    prepare_rss_xml,
    row_to_overlay,
    normalize_symbol,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

FetchFn = Callable[[], str]

_rows: dict[str, HaltRssRow] = {}
_mwcb: dict[str, Any] | None = None
_feed_status = "pending"  # ok | pending | down | empty
_last_fetch_at: float | None = None
_last_success_at: float | None = None
_last_error: str | None = None


def reset() -> None:
    """Drop overlay cache (tests)."""
    global _mwcb, _feed_status, _last_fetch_at, _last_success_at, _last_error
    _rows.clear()
    _mwcb = None
    _feed_status = "pending"
    _last_fetch_at = None
    _last_success_at = None
    _last_error = None


def _default_fetch() -> str:
    response = requests.get(
        NASDAQ_TRADE_HALT_RSS_URL,
        timeout=NASDAQ_TRADE_HALT_RSS_HTTP_TIMEOUT_SEC,
        headers={"User-Agent": NASDAQ_TRADE_HALT_RSS_USER_AGENT},
    )
    response.raise_for_status()
    return prepare_rss_xml(response.content)


def overlay_for(symbol: str) -> dict[str, Any]:
    """Per-symbol Nasdaq overlay. Missing / down => pending or down, no times."""
    key = normalize_symbol(symbol)
    row = _rows.get(key)
    if row is not None:
        return row_to_overlay(row, status="ok")
    status = "down" if _feed_status == "down" else "pending"
    return row_to_overlay(None, status=status)


def open_symbols() -> list[str]:
    """Symbols whose latest overlay row has no trade_resume (still halted)."""
    return sorted(
        symbol
        for symbol, row in _rows.items()
        if symbol and row.trade_resume is None and row.mwcb_level is None
    )


def desk_snapshot(*, now: float | None = None) -> dict[str, Any]:
    ts = time.time() if now is None else float(now)
    age = None if _last_success_at is None else max(0.0, ts - _last_success_at)
    mwcb = None
    if _mwcb is not None:
        mwcb = {
            **_mwcb,
            "stale": _feed_status == "down",
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "mwcb": mwcb,
        "feed": {
            "status": _feed_status,
            "age_sec": age,
            "source": "nasdaq_trade_halt_rss",
            "url": NASDAQ_TRADE_HALT_RSS_URL,
            "error": _last_error,
        },
    }


def refresh(
    *,
    now: float | None = None,
    xml_text: str | None = None,
    fetch: FetchFn | None = None,
    min_interval_sec: float | None = None,
) -> dict[str, Any]:
    """Fetch+parse or apply recorded XML. Refuses a second fetch inside TTL."""
    global _mwcb, _feed_status, _last_fetch_at, _last_success_at, _last_error
    ts = time.time() if now is None else float(now)
    interval = (
        NASDAQ_TRADE_HALT_RSS_POLL_SEC
        if min_interval_sec is None
        else float(min_interval_sec)
    )
    if (
        xml_text is None
        and _last_fetch_at is not None
        and (ts - _last_fetch_at) < interval
    ):
        return {"skipped": True, "reason": "poll_interval", **desk_snapshot(now=ts)}

    _last_fetch_at = ts
    try:
        body = xml_text if xml_text is not None else (fetch or _default_fetch)()
        parsed = parse_trade_halt_rss(body)
    except (requests.RequestException, OSError, ValueError) as exc:
        _feed_status = "down"
        _last_error = str(exc)
        logger.warning("Nasdaq Trade Halt RSS fetch failed: %s", exc)
        return {"skipped": False, "ok": False, **desk_snapshot(now=ts)}

    if not parsed["ok"]:
        _feed_status = "down"
        _last_error = parsed.get("error") or "parse"
        logger.warning("Nasdaq Trade Halt RSS parse failed: %s", _last_error)
        return {"skipped": False, "ok": False, **desk_snapshot(now=ts)}

    _rows.clear()
    for row in parsed["rows"]:
        if not row.symbol:
            continue
        prev = _rows.get(row.symbol)
        _rows[row.symbol] = row if prev is None else better_overlay_row(prev, row)
    _mwcb = parsed["mwcb"]
    _last_success_at = ts
    _last_error = None
    _feed_status = "empty" if not _rows and _mwcb is None else "ok"
    return {
        "skipped": False,
        "ok": True,
        "row_count": len(_rows),
        **desk_snapshot(now=ts),
    }


async def poll_loop() -> None:
    """Background RSS poll -- at most once per NASDAQ_TRADE_HALT_RSS_POLL_SEC."""
    while True:
        try:
            result = await asyncio.to_thread(refresh)
            if not result.get("skipped"):
                from ibkr import halt_status

                await halt_status.broadcast_live_halts()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Nasdaq Trade Halt RSS poll iteration failed")
        await asyncio.sleep(NASDAQ_TRADE_HALT_RSS_POLL_SEC)
