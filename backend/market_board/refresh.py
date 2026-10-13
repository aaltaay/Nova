"""The Market page's refreshers (ADR 053): every read on its own cadence, and only while someone is looking.

Two daemon threads start on the first ask: ``ibkr`` (snapshots, paced bars, the movers scan, industries -- all on
the IB loop through ``run_coro``) and ``files`` (State Street, BEA, Finnhub earnings, the leaderboard store). Each
takes the first due read, runs it, and records the answer or the failure in ``market_board.state``. Nothing runs
while the page has not asked within ``MARKET_WANTED_SEC`` -- except the NYSE breadth sample, once a minute in the
regular session -- and nothing runs with ``NOVA_MARKET_BOARD=0``. ``run_once`` is the whole step for tests.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable

from constants_market_board import (
    MARKET_BARS_LINE_TTL_SEC,
    MARKET_BARS_MOVERS_MAX,
    MARKET_BARS_QUOTES_TTL_SEC,
    MARKET_BREADTH_SAMPLE_SEC,
    MARKET_CLIMATE_BASELINE_DAYS,
    MARKET_CLIMATE_CHART_SESSIONS,
    MARKET_CLIMATE_TTL_SEC,
    MARKET_CLOSES_RETRY_SEC,
    MARKET_ENV,
    MARKET_ETF_TTL_SEC,
    MARKET_FILES_TTL_SEC,
    MARKET_HISTORY_GAP_SEC,
    MARKET_HOLDINGS_QUOTES_TTL_SEC,
    MARKET_HOLDINGS_TTL_SEC,
    MARKET_INDUSTRIES,
    MARKET_INDUSTRY_BATCH,
    MARKET_LEADER_POOL,
    MARKET_LINES_TTL_SEC,
    MARKET_MOVERS_TTL_SEC,
    MARKET_PERIOD_SESSIONS,
    MARKET_QUOTES,
    MARKET_QUOTES_TTL_SEC,
    MARKET_SECTORS,
    MARKET_SHED_RETRY_SEC,
    MARKET_TICK_SEC,
)
from constants_scanner import SESSION_RTH_OPEN_MIN_ET
from market_board import breadth, climate, clock, contracts, events, holdings, ibkr_reads, industries
from market_board.state import Stated, store

logger = logging.getLogger(__name__)
FOREVER = 1e12
SECTOR_ETFS = tuple(e for _, e in MARKET_SECTORS)
INDUSTRY_ETFS = tuple(e for _, e, _ in MARKET_INDUSTRIES)
FILE_ETFS = SECTOR_ETFS + tuple(e for _, e, has in MARKET_INDUSTRIES if has)
QUOTE_SPECS = tuple(s for s in MARKET_QUOTES if s["sec_type"] != "SPREAD")
CLIMATE_SESSIONS = MARKET_PERIOD_SESSIONS["30D"] + max(MARKET_CLIMATE_BASELINE_DAYS, MARKET_CLIMATE_CHART_SESSIONS)


@dataclass(frozen=True)
class Job:
    key: str
    source: str
    ttl: float
    fetch: Callable[[], Any]
    gap_group: str | None = None
    gap: float = 0.0
    fresh: Callable[[Any], bool] | None = None
    retry: float = 60.0


_group_last: dict[str, float] = {}
_threads: dict[str, threading.Thread] = {}
_threads_lock = threading.Lock()
_wake = {"ibkr": threading.Event(), "files": threading.Event()}


def enabled() -> bool:
    return (os.environ.get(MARKET_ENV) or "1").strip() != "0"


def want(now: float | None = None, top_kind: str | None = None) -> None:
    store().want(time.time() if now is None else now, top_kind)
    _start()


def _members(etfs: tuple[str, ...], limit: int | None = None) -> list[str]:
    out: list[str] = []
    for etf in etfs:
        now = time.time()
        h = store().get(f"holdings:{etf}", now, MARKET_HOLDINGS_TTL_SEC) or holdings.usable(etf, now)
        for row in ((h or {}).get("rows") or [])[:limit]:
            if row["symbol"] not in out:
                out.append(row["symbol"])
    return out


def _has_session(day: str, rows: Any) -> bool:
    """Daily closes that already hold the session before ``day`` (today's bar is not needed)."""
    return isinstance(rows, list) and any(d >= day for d, _ in rows)


def _movers() -> dict[str, Any]:
    ranked = ibkr_reads.movers()
    universe = set(_members(SECTOR_ETFS) + _members(tuple(e for _, e, has in MARKET_INDUSTRIES if has)))
    picked = [s for s in ranked if s in universe]
    return {"symbols": picked, "quotes": ibkr_reads.stock_quotes(picked)}


def _movers_bars(today: str) -> dict[str, Any]:
    """The movers without a market-data line: IBKR's scan ranks them (a scan holds no line), bars price them."""
    ranked = ibkr_reads.movers_ranked()
    universe = set(_members(SECTOR_ETFS) + _members(tuple(e for _, e, has in MARKET_INDUSTRIES if has)))
    picked = [s for s in ranked if s in universe][:MARKET_BARS_MOVERS_MAX]
    return {"symbols": picked, "quotes": ibkr_reads.bar_quotes(picked, today)}


def _breadth_sample(day_iso: str) -> dict | None:
    from datetime import date

    quotes = ibkr_reads.reference_quotes(contracts.breadth_specs(), day_iso)
    sample = breadth.sample_from(quotes)
    if sample is None:
        why = next((q.get("error") for q in quotes.values() if q.get("error")), None)
        raise ibkr_reads.SourceError(why or "IBKR gave no NYSE advancing / declining counts")
    breadth.record(sample, date.fromisoformat(day_iso), time.time())
    return sample


def breadth_due(now: float) -> bool:
    day = clock.trading_date(now)
    if clock.phase(now) != "regular" or now < clock.at(day, SESSION_RTH_OPEN_MIN_ET):
        return False
    return store().due("breadth_latest", now, MARKET_BREADTH_SAMPLE_SEC)


def ibkr_jobs(now: float) -> list[Job]:
    day = clock.trading_date(now)
    iso = day.isoformat()
    prior_session = clock.prior_open_day(day).isoformat()
    st = store()
    lines_free = ibkr_reads.headroom_ok()
    jobs: list[Job] = []
    if lines_free:
        jobs.append(Job("quotes", ibkr_reads.SOURCE, MARKET_QUOTES_TTL_SEC,
                        partial(ibkr_reads.reference_quotes, list(QUOTE_SPECS), iso)))
        jobs.append(Job("etf_quotes", ibkr_reads.SOURCE, MARKET_ETF_TTL_SEC,
                        partial(ibkr_reads.stock_quotes, list(SECTOR_ETFS + INDUSTRY_ETFS))))
        jobs.append(Job("movers", ibkr_reads.SOURCE, MARKET_MOVERS_TTL_SEC, _movers))
    else:
        # No spare line: prices from bars, which hold none (the tiles' lines, ETFs' and movers' daily bars).
        jobs.append(Job("etf_bars", ibkr_reads.SOURCE, MARKET_BARS_QUOTES_TTL_SEC,
                        partial(ibkr_reads.bar_quotes, list(SECTOR_ETFS + INDUSTRY_ETFS), iso),
                        gap_group="history", gap=MARKET_HISTORY_GAP_SEC, retry=MARKET_SHED_RETRY_SEC))
        jobs.append(Job("movers_bars", ibkr_reads.SOURCE, MARKET_BARS_QUOTES_TTL_SEC, partial(_movers_bars, iso),
                        gap_group="history", gap=MARKET_HISTORY_GAP_SEC, retry=MARKET_SHED_RETRY_SEC))
    # Every tile's prior daily close, once a session, lines or not: IBKR's Cboe index snapshots (VIX, TNX) came back
    # with no last and no close on 2026-10-13 while their bars answered.
    for spec in QUOTE_SPECS:
        jobs.append(Job(f"prior:{spec['id']}", ibkr_reads.SOURCE, FOREVER,
                        partial(ibkr_reads.prior_close, spec, iso), gap_group="history",
                        gap=MARKET_HISTORY_GAP_SEC, fresh=partial(_prior_fresh, prior_session),
                        retry=MARKET_SHED_RETRY_SEC))
    line_ttl = MARKET_LINES_TTL_SEC if lines_free else MARKET_BARS_LINE_TTL_SEC
    for spec in QUOTE_SPECS:
        jobs.append(Job(f"line:{spec['id']}", ibkr_reads.SOURCE, line_ttl,
                        partial(ibkr_reads.line_bars, spec, iso), gap_group="history", gap=MARKET_HISTORY_GAP_SEC,
                        retry=MARKET_SHED_RETRY_SEC))
    pool = _members(SECTOR_ETFS, MARKET_LEADER_POOL) + _members(
        tuple(e for _, e, has in MARKET_INDUSTRIES if has), MARKET_LEADER_POOL)
    if st.top_kind_wanted("biggest", now):
        jobs.append(Job("pool_quotes", ibkr_reads.SOURCE, MARKET_HOLDINGS_QUOTES_TTL_SEC,
                        partial(ibkr_reads.stock_quotes, pool)))
    for sym in SECTOR_ETFS + INDUSTRY_ETFS + tuple(pool):
        jobs.append(Job(f"closes:{sym}", ibkr_reads.SOURCE, FOREVER, partial(ibkr_reads.rth_closes, sym),
                        gap_group="history", gap=MARKET_HISTORY_GAP_SEC, fresh=partial(_has_session, prior_session),
                        retry=MARKET_CLOSES_RETRY_SEC))
    runners = st.get("climate", now, 3600.0) or []
    todo = industries.missing(runners, now)[:MARKET_INDUSTRY_BATCH]
    if todo:
        jobs.append(Job(f"industries:{todo[0]}", ibkr_reads.SOURCE, 0.0, partial(_industries, todo)))
    return jobs


def _prior_fresh(prior_session: str, value: Any) -> bool:
    """A tile's prior daily close that is already the last session's (a future's may be the evening before)."""
    return isinstance(value, dict) and str(value.get("date") or "") >= prior_session


def _industries(symbols: list[str]) -> int:
    answers = ibkr_reads.industries(symbols)
    industries.put_many(answers, time.time())
    return len(answers)


def files_jobs(now: float) -> list[Job]:
    jobs = [Job("climate", climate.SOURCE, MARKET_CLIMATE_TTL_SEC,
                partial(climate.refresh, now, sessions_needed=CLIMATE_SESSIONS))]
    for etf in FILE_ETFS:
        jobs.append(Job(f"holdings:{etf}", holdings.SOURCE, MARKET_HOLDINGS_TTL_SEC, partial(_holdings, etf)))
    jobs.append(Job("bea", events.BEA_SOURCE, MARKET_FILES_TTL_SEC, events.fetch_bea))
    jobs.append(Job("earnings", "finnhub", MARKET_FILES_TTL_SEC, _earnings))
    return jobs


def _holdings(etf: str) -> dict:
    """The kept file when it is fresh enough, else State Street's current one."""
    got = holdings.cached(etf)
    if got and time.time() - float(got.get("fetched_at") or 0) < MARKET_HOLDINGS_TTL_SEC:
        return got
    return holdings.fetch(etf)


def _earnings() -> list[dict]:
    from earnings_calendar import get_calendar_rows

    rows, _, error = get_calendar_rows()
    if error and not rows:
        raise Stated(error)
    return rows


def run_once(lane: str, now: float | None = None) -> bool:
    """Run the first due read of ``lane`` (``ibkr`` | ``files``); False when none was due."""
    now = time.time() if now is None else now
    st = store()
    if lane == "ibkr":
        if not ibkr_reads.ready():
            st.source_down(ibkr_reads.SOURCE, "IBKR is not connected")
            return False
        st.source_down(ibkr_reads.SOURCE, None)
        if breadth_due(now):
            _run(Job("breadth_latest", ibkr_reads.SOURCE, MARKET_BREADTH_SAMPLE_SEC,
                     partial(_breadth_sample, clock.trading_date(now).isoformat())), now, error_key="breadth")
            return True
        if not st.wanted(now):
            return False
    elif not st.wanted(now):
        return False
    for job in ibkr_jobs(now) if lane == "ibkr" else files_jobs(now):
        if _due(job, now):
            _run(job, now)
            return True
    return False


def _due(job: Job, now: float) -> bool:
    st = store()
    if job.gap_group and now - _group_last.get(job.gap_group, -FOREVER) < job.gap:
        return False
    if job.fresh is None:
        return st.due(job.key, now, job.ttl)
    if not st.due(job.key, now, 0.0):
        return False
    value = st.get(job.key, now, FOREVER)
    return value is None or not job.fresh(value)


def _run(job: Job, now: float, error_key: str | None = None) -> None:
    st = store()
    if job.gap_group:
        _group_last[job.gap_group] = now
    started = time.monotonic()
    try:
        value = job.fetch()
    except ibkr_reads.NoHeadroom as exc:
        st.defer(job.key, now + MARKET_SHED_RETRY_SEC)   # the desk's lines come first; not a failure
        if error_key:
            st.fail(error_key, job.source, f"waiting for spare market-data lines: {exc}", now, MARKET_SHED_RETRY_SEC)
        return
    except Exception as exc:  # noqa: BLE001 -- any failure is stated on the page, never raised into the loop
        at = now + (time.monotonic() - started)
        if type(exc).__name__ == "HistoricalShed":
            st.defer(job.key, at + MARKET_SHED_RETRY_SEC)
            return
        logger.warning("market_board: %s failed: %s", job.key, exc, exc_info=not isinstance(exc, Stated))
        message = f"{exc}"[:200] or type(exc).__name__
        st.fail(job.key, job.source, message, at, job.retry)
        if error_key:
            st.fail(error_key, job.source, message, at, job.retry)
        return
    at = now + (time.monotonic() - started)
    st.put(job.key, job.source, value, at)
    if error_key:
        st.put(error_key, job.source, None, at)
    if job.fresh is not None and not job.fresh(value):
        st.defer(job.key, at + job.retry)


def _start() -> None:
    if not enabled():
        return
    with _threads_lock:
        for lane in ("ibkr", "files"):
            thread = _threads.get(lane)
            if thread is None or not thread.is_alive():
                thread = threading.Thread(target=_loop, args=(lane,), daemon=True, name=f"market_board_{lane}")
                _threads[lane] = thread
                thread.start()
    for event in _wake.values():
        event.set()


def start_breadth_sampler() -> None:
    """Start the IBKR lane at process start, so the breadth line exists before anyone opens the page."""
    _start()


def _loop(lane: str) -> None:
    while True:
        try:
            now = time.time()
            if not enabled():
                _wake[lane].wait(30.0)
                _wake[lane].clear()
                continue
            if not run_once(lane, now):
                if store().wanted(now):
                    time.sleep(MARKET_TICK_SEC)
                else:
                    _wake[lane].wait(5.0)
                    _wake[lane].clear()
        except Exception:  # noqa: BLE001 -- the refresher must outlive any one bad read
            logger.exception("market_board refresher %s", lane)
            time.sleep(5.0)


def reset_for_tests() -> None:
    _group_last.clear()
    store().reset()
