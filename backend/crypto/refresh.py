"""The Cryptos page's refreshers (ADR 040): every read on its own cadence, and only while someone is looking.

Two daemon threads start on the first ask: ``web`` (the public sources; a chart the page asked for goes first)
and ``ibkr`` (the bridge stocks' quotes and closes, the coins' listing check -- all through ``run_coro`` on the
IB loop, cold or background priority). Each takes the first due read, runs it, and records the answer or the
failure in ``crypto.state``. Nothing runs while the page has not asked within ``CRYPTO_WANTED_SEC`` or with
``NOVA_CRYPTO=0``. ``run_once`` is the whole step, so tests drive it without threads.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable

from constants_crypto import (
    CRYPTO_BRIDGE,
    CRYPTO_BRIDGE_CLOSES_RETRY_SEC,
    CRYPTO_BRIDGE_DRIVERS,
    CRYPTO_BRIDGE_QUOTE_TTL_SEC,
    CRYPTO_BRIDGE_REQUEST_GAP_SEC,
    CRYPTO_BRIDGE_SHED_RETRY_SEC,
    CRYPTO_CANDLES_TTL_SEC,
    CRYPTO_COINS,
    CRYPTO_CORR_SYMBOL,
    CRYPTO_ENV,
    CRYPTO_GLOBAL_TTL_SEC,
    CRYPTO_HOURLY_DAYS,
    CRYPTO_HOURLY_TTL_SEC,
    CRYPTO_LISTING_GAP_SEC,
    CRYPTO_LISTING_RETRY_SEC,
    CRYPTO_MARKETS_TTL_SEC,
    CRYPTO_NEWS_TTL_SEC,
    CRYPTO_PERPS_TTL_SEC,
    CRYPTO_RETRY_SEC,
    CRYPTO_SLOW_TTL_SEC,
    CRYPTO_TICK_SEC,
    CRYPTO_VOLUME_HISTORY_GAP_SEC,
    CRYPTO_VOLUME_HISTORY_TTL_SEC,
)
from crypto import clock, coinbase, coingecko, feeds, ibkr_reads, news
from crypto.state import store
from crypto.web import SourceError

logger = logging.getLogger(__name__)

COIN_BY_SYMBOL = {c["symbol"]: c for c in CRYPTO_COINS}
BRIDGE_SYMBOLS = tuple(b["symbol"] for b in CRYPTO_BRIDGE)
FOREVER = 1e12


@dataclass(frozen=True)
class Job:
    key: str
    source: str
    ttl: float
    fetch: Callable[[], Any]
    gap_group: str | None = None      # reads of one group run at least ``gap`` seconds apart
    gap: float = 0.0
    fresh: Callable[[Any], bool] | None = None  # an answer that is not fresh enough is asked for again
    retry: float = CRYPTO_RETRY_SEC


_group_last: dict[str, float] = {}
_threads: dict[str, threading.Thread] = {}
_threads_lock = threading.Lock()
_wake = {"web": threading.Event(), "ibkr": threading.Event()}


def enabled() -> bool:
    return (os.environ.get(CRYPTO_ENV) or "1").strip() != "0"


def want(now: float | None = None) -> None:
    """The board was asked for: keep every read fresh for ``CRYPTO_WANTED_SEC``."""
    store().want(time.time() if now is None else now)
    _start()


def want_candles(symbol: str, tf: str, now: float | None = None) -> None:
    store().want_candles(symbol, tf, time.time() if now is None else now)
    _start()


def candle_job(symbol: str, tf: str) -> Job:
    product = COIN_BY_SYMBOL[symbol]["coinbase"]
    return Job(f"candles:{symbol}:{tf}", coinbase.SOURCE, CRYPTO_CANDLES_TTL_SEC[tf],
               partial(coinbase.fetch_series, product, tf))


def web_jobs(now: float) -> list[Job]:
    """Every public read, the charts the page asked for first."""
    jobs: list[Job] = []
    for symbol, tf in store().wanted_candles(now):
        jobs.append(candle_job(symbol, tf))
        if tf != "15m":
            jobs.append(candle_job(symbol, "15m"))  # the chart's levels come from the 15-minute series
    jobs += [
        Job("markets", coingecko.SOURCE, CRYPTO_MARKETS_TTL_SEC, coingecko.fetch_markets),
        Job("global", coingecko.SOURCE, CRYPTO_GLOBAL_TTL_SEC, coingecko.fetch_global),
        Job("perps", "hyperliquid", CRYPTO_PERPS_TTL_SEC, feeds.fetch_perps),
        Job("fear_greed", "fear_greed", CRYPTO_SLOW_TTL_SEC, feeds.fetch_fear_greed),
        Job("news", news.SOURCE, CRYPTO_NEWS_TTL_SEC, news.fetch_news),
        Job("stablecoins", "defillama", CRYPTO_SLOW_TTL_SEC, feeds.fetch_stablecoins),
        Job("expiries", "deribit", CRYPTO_SLOW_TTL_SEC, feeds.fetch_option_expiries),
    ]
    for driver in CRYPTO_BRIDGE_DRIVERS:
        product = COIN_BY_SYMBOL[driver]["coinbase"]
        jobs.append(candle_job(driver, "15m"))
        jobs.append(Job(f"hourly:{driver}", coinbase.SOURCE, CRYPTO_HOURLY_TTL_SEC,
                        partial(coinbase.fetch_history, product, 3600, CRYPTO_HOURLY_DAYS * 86400)))
    for coin in CRYPTO_COINS:
        jobs.append(Job(f"volume:{coin['symbol']}", coingecko.SOURCE, CRYPTO_VOLUME_HISTORY_TTL_SEC,
                        partial(coingecko.fetch_volume_history, coin["coingecko"]),
                        gap_group="coingecko_history", gap=CRYPTO_VOLUME_HISTORY_GAP_SEC))
    return _unique(jobs)


def ibkr_jobs(now: float) -> list[Job]:
    """The bridge stocks' quotes and regular-hours closes, then the coins' listing check."""
    _, session_day = clock.reference_close(now)
    jobs = [Job("bridge_quotes", ibkr_reads.SOURCE, CRYPTO_BRIDGE_QUOTE_TTL_SEC,
                partial(ibkr_reads.quotes, list(BRIDGE_SYMBOLS)))]
    for symbol in (*BRIDGE_SYMBOLS, CRYPTO_CORR_SYMBOL):
        jobs.append(Job(f"closes:{symbol}", ibkr_reads.SOURCE, FOREVER, partial(ibkr_reads.rth_closes, symbol),
                        gap_group="ibkr_history", gap=CRYPTO_BRIDGE_REQUEST_GAP_SEC,
                        fresh=partial(_has_session, session_day), retry=CRYPTO_BRIDGE_CLOSES_RETRY_SEC))
    for coin in CRYPTO_COINS:
        jobs.append(Job(f"listing:{coin['symbol']}", ibkr_reads.SOURCE, FOREVER,
                        partial(ibkr_reads.listing, coin["symbol"]), gap_group="ibkr_listing",
                        gap=CRYPTO_LISTING_GAP_SEC, retry=CRYPTO_LISTING_RETRY_SEC))
    return jobs


def run_once(lane: str, now: float | None = None) -> bool:
    """Run the first due read of ``lane`` (``web`` | ``ibkr``); False when none was due."""
    now = time.time() if now is None else now
    st = store()
    if lane == "ibkr":
        if not ibkr_reads.ready():
            st.source_down(ibkr_reads.SOURCE, "IBKR is not connected")
            return False
        st.source_down(ibkr_reads.SOURCE, None)
    for job in web_jobs(now) if lane == "web" else ibkr_jobs(now):
        if _due(job, now):
            _run(job, now)
            return True
    return False


def _has_session(day: str, closes: Any) -> bool:
    return isinstance(closes, dict) and day in closes


def _unique(jobs: list[Job]) -> list[Job]:
    seen: set[str] = set()
    out = []
    for job in jobs:
        if job.key not in seen:
            seen.add(job.key)
            out.append(job)
    return out


def _due(job: Job, now: float) -> bool:
    st = store()
    if job.gap_group and now - _group_last.get(job.gap_group, -FOREVER) < job.gap:
        return False
    if job.fresh is None:
        return st.due(job.key, job.source, now, job.ttl)
    if not st.due(job.key, job.source, now, 0.0):  # waiting out a retry or a 429
        return False
    value = st.get(job.key, now, job.ttl)
    return value is None or not job.fresh(value)


def _run(job: Job, now: float) -> None:
    """Run one read; stamp its answer or failure on the tick's clock plus the time the read took."""
    st = store()
    if job.gap_group:
        _group_last[job.gap_group] = now
    started = time.monotonic()
    try:
        value = job.fetch()
    except SourceError as exc:
        st.fail(job.key, job.source, str(exc), now + (time.monotonic() - started), job.retry)
    except Exception as exc:  # noqa: BLE001 -- any failure is stated on the page, never raised into the loop
        at = now + (time.monotonic() - started)
        if type(exc).__name__ == "HistoricalShed":
            st.defer(job.key, at + CRYPTO_BRIDGE_SHED_RETRY_SEC)  # IBKR's budget said later
            return
        logger.warning("crypto: %s failed", job.key, exc_info=True)
        st.fail(job.key, job.source, f"{type(exc).__name__}: {exc}"[:160], at, job.retry)
    else:
        at = now + (time.monotonic() - started)
        st.put(job.key, job.source, value, at)
        if job.fresh is not None and not job.fresh(value):
            st.defer(job.key, at + job.retry)


def _start() -> None:
    if not enabled():
        return
    with _threads_lock:
        for lane in ("web", "ibkr"):
            thread = _threads.get(lane)
            if thread is None or not thread.is_alive():
                thread = threading.Thread(target=_loop, args=(lane,), daemon=True, name=f"crypto_{lane}")
                _threads[lane] = thread
                thread.start()
    for event in _wake.values():
        event.set()


def _loop(lane: str) -> None:
    while True:
        try:
            now = time.time()
            if not enabled() or not store().wanted(now):
                _wake[lane].wait(5.0)
                _wake[lane].clear()
                continue
            if not run_once(lane, now):
                time.sleep(CRYPTO_TICK_SEC)
        except Exception:  # noqa: BLE001 -- the refresher must outlive any one bad read
            logger.exception("crypto refresher %s", lane)
            time.sleep(5.0)


def reset_for_tests() -> None:
    _group_last.clear()
    store().reset()
