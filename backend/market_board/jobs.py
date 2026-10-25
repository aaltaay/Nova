"""The Market page's reads (ADR 053): what each refresher thread reads, from which source, and how often.

``ibkr`` reads quotes from lines held for a moment and IBKR's movers scan; ``history`` reads paced bars and contract
details, so it never waits behind a quote (ADR 053 amendment 2026-10-13); ``files`` reads State Street, BEA, Finnhub
earnings and the leaderboard store. A ``Job`` names its store key, its source, its page cadence (``ttl``) and its
background cadence while nobody looks (``idle``, ADR 053 amendment 2026-10-13 evening); ``market_board.refresh``
runs them. Building a list asks nothing: every read happens in ``Job.fetch``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable

from constants_market_board import (
    MARKET_BARS_LINE_TTL_SEC,
    MARKET_BARS_MOVERS_MAX,
    MARKET_BARS_QUOTES_TTL_SEC,
    MARKET_CLIMATE_BASELINE_DAYS,
    MARKET_CLIMATE_CHART_SESSIONS,
    MARKET_CLIMATE_TTL_SEC,
    MARKET_CLOSES_RETRY_SEC,
    MARKET_ETF_TTL_SEC,
    MARKET_FILES_TTL_SEC,
    MARKET_HISTORY_GAP_SEC,
    MARKET_HOLDINGS_QUOTES_TTL_SEC,
    MARKET_HOLDINGS_TTL_SEC,
    MARKET_IDLE_BARS_TTL_SEC,
    MARKET_IDLE_CLIMATE_TTL_SEC,
    MARKET_IDLE_ETF_TTL_SEC,
    MARKET_IDLE_LINES_TTL_SEC,
    MARKET_IDLE_MOVERS_TTL_SEC,
    MARKET_IDLE_POOL_TTL_SEC,
    MARKET_IDLE_QUOTES_TTL_SEC,
    MARKET_INDUSTRIES,
    MARKET_INDUSTRY_BATCH,
    MARKET_LEADER_POOL,
    MARKET_LINES_TTL_SEC,
    MARKET_MOVERS_TTL_SEC,
    MARKET_PERIOD_SESSIONS,
    MARKET_POOL_CHUNK,
    MARKET_QUOTES,
    MARKET_QUOTES_TTL_SEC,
    MARKET_SECTORS,
    MARKET_SHED_RETRY_SEC,
    MARKET_TEMP_BASELINE_DAYS,
)
from market_board import climate, clock, events, holdings, ibkr_reads, industries
from market_board.state import Stated, store

FOREVER = 1e12
SECTOR_ETFS = tuple(e for _, e in MARKET_SECTORS)
INDUSTRY_ETFS = tuple(e for _, e, _ in MARKET_INDUSTRIES)
FILE_ETFS = SECTOR_ETFS + tuple(e for _, e, has in MARKET_INDUSTRIES if has)
QUOTE_SPECS = tuple(s for s in MARKET_QUOTES if s["sec_type"] != "SPREAD")
CLIMATE_SESSIONS = MARKET_PERIOD_SESSIONS["30D"] + max(MARKET_CLIMATE_BASELINE_DAYS, MARKET_CLIMATE_CHART_SESSIONS,
                                                       MARKET_TEMP_BASELINE_DAYS)


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
    idle: float | None = None   # the TTL while nobody looks (warm); None: the same as ``ttl``
    whole: Callable[[Any], bool] | None = None   # False: the source cut the pass short, read the rest after ``retry``

    def ttl_now(self, wanted: bool) -> float:
        return self.ttl if wanted or self.idle is None else max(self.ttl, self.idle)


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


def _bars_pass(symbols: list[str], today: str, kept: dict[str, dict]) -> dict[str, dict]:
    """One pass of ``bar_quotes`` on top of the last passes' answers for ``today``.

    The historical service sheds a pass part way at the open (2026-10-16: only XLK of 26 ETFs priced, every pass
    starting over at XLK), so a pass reads the symbols with no answer first, then the oldest, and keeps what it
    did not reach.
    """
    have = {s: q for s, q in kept.items() if s in symbols and isinstance(q, dict) and q.get("date") == today}
    order = sorted(symbols, key=lambda s: (s in have, (have.get(s) or {}).get("at") or 0.0))
    return {**have, **ibkr_reads.bar_quotes(order, today)}


def _kept(key: str) -> Any:
    return store().get(key, time.time(), FOREVER)


def _etf_bars(today: str) -> dict[str, dict]:
    return _bars_pass(list(SECTOR_ETFS + INDUSTRY_ETFS), today, _kept("etf_bars") or {})


def _etf_bars_whole(value: Any) -> bool:
    return isinstance(value, dict) and all(s in value for s in SECTOR_ETFS + INDUSTRY_ETFS)


def _movers_bars(today: str) -> dict[str, Any]:
    """The movers without a market-data line: IBKR's scan ranks them (a scan holds no line), bars price them."""
    ranked = ibkr_reads.movers_ranked()
    universe = set(_members(SECTOR_ETFS) + _members(tuple(e for _, e, has in MARKET_INDUSTRIES if has)))
    picked = [s for s in ranked if s in universe][:MARKET_BARS_MOVERS_MAX]
    kept = (_kept("movers_bars") or {}).get("quotes") or {}
    return {"symbols": picked, "quotes": _bars_pass(picked, today, kept)}


def _movers_bars_whole(value: Any) -> bool:
    quotes = (value or {}).get("quotes") or {}
    return all(s in quotes for s in (value or {}).get("symbols") or [])


def ibkr_jobs(now: float) -> list[Job]:
    """Reads that open a line for a moment, or a scan: nothing here waits on the historical service."""
    if not ibkr_reads.headroom_ok():
        return []   # no spare line: ``history_jobs`` prices from bars
    iso = clock.trading_date(now).isoformat()
    jobs = [
        Job("quotes", ibkr_reads.SOURCE, MARKET_QUOTES_TTL_SEC,
            partial(ibkr_reads.reference_quotes, list(QUOTE_SPECS), iso), idle=MARKET_IDLE_QUOTES_TTL_SEC),
        Job("etf_quotes", ibkr_reads.SOURCE, MARKET_ETF_TTL_SEC,
            partial(ibkr_reads.stock_quotes, list(SECTOR_ETFS + INDUSTRY_ETFS)), idle=MARKET_IDLE_ETF_TTL_SEC),
        Job("movers", ibkr_reads.SOURCE, MARKET_MOVERS_TTL_SEC, _movers, idle=MARKET_IDLE_MOVERS_TTL_SEC),
    ]
    # The biggest names fill every sector's top-stocks card and its leader: always read, a chunk at a time, so the
    # tile quotes above (first due, first run) get their turn between chunks.
    for i, chunk in enumerate(pool_chunks()):
        jobs.append(Job(f"pool_quotes:{i}", ibkr_reads.SOURCE, MARKET_HOLDINGS_QUOTES_TTL_SEC,
                        partial(ibkr_reads.stock_quotes, chunk), idle=MARKET_IDLE_POOL_TTL_SEC))
    return jobs


def _leader_pool() -> list[str]:
    return _members(SECTOR_ETFS, MARKET_LEADER_POOL) + _members(
        tuple(e for _, e, has in MARKET_INDUSTRIES if has), MARKET_LEADER_POOL)


def pool_chunks() -> list[list[str]]:
    pool = _leader_pool()
    return [pool[i:i + MARKET_POOL_CHUNK] for i in range(0, len(pool), MARKET_POOL_CHUNK)]


def _tiles_first(now: float) -> list[dict]:
    """The tiles, those the last quote read left without a price first (VIX and TNX price only from bars)."""
    quotes = store().get("quotes", now, MARKET_QUOTES_TTL_SEC) or {}
    return sorted(QUOTE_SPECS, key=lambda spec: (quotes.get(spec["id"]) or {}).get("last") is not None)


def history_jobs(now: float) -> list[Job]:
    """Paced bars and contract details: each tile's prior close and line together, then daily closes, industries."""
    day = clock.trading_date(now)
    iso = day.isoformat()
    prior_session = clock.prior_open_day(day).isoformat()
    lines_free = ibkr_reads.headroom_ok()
    jobs: list[Job] = []
    if not lines_free:
        # No spare line: prices from bars, which hold none (the tiles' lines, ETFs' and movers' daily bars).
        jobs.append(Job("etf_bars", ibkr_reads.SOURCE, MARKET_BARS_QUOTES_TTL_SEC, partial(_etf_bars, iso),
                        gap_group="history", gap=MARKET_HISTORY_GAP_SEC, retry=MARKET_SHED_RETRY_SEC,
                        idle=MARKET_IDLE_BARS_TTL_SEC, whole=_etf_bars_whole))
        jobs.append(Job("movers_bars", ibkr_reads.SOURCE, MARKET_BARS_QUOTES_TTL_SEC, partial(_movers_bars, iso),
                        gap_group="history", gap=MARKET_HISTORY_GAP_SEC, retry=MARKET_SHED_RETRY_SEC,
                        idle=MARKET_IDLE_BARS_TTL_SEC, whole=_movers_bars_whole))
    # Every tile's prior daily close, once a session, lines or not: IBKR's Cboe index snapshots (VIX, TNX) came back
    # with no last and no close on 2026-10-13 while their bars answered.
    line_ttl = MARKET_LINES_TTL_SEC if lines_free else MARKET_BARS_LINE_TTL_SEC
    line_idle = MARKET_IDLE_LINES_TTL_SEC if lines_free else MARKET_LINES_TTL_SEC
    for spec in _tiles_first(now):
        jobs.append(Job(f"prior:{spec['id']}", ibkr_reads.SOURCE, FOREVER,
                        partial(ibkr_reads.prior_close, spec, iso), gap_group="history",
                        gap=MARKET_HISTORY_GAP_SEC, fresh=partial(_prior_fresh, prior_session),
                        retry=MARKET_SHED_RETRY_SEC))
        jobs.append(Job(f"line:{spec['id']}", ibkr_reads.SOURCE, line_ttl,
                        partial(ibkr_reads.line_bars, spec, iso), gap_group="history", gap=MARKET_HISTORY_GAP_SEC,
                        retry=MARKET_SHED_RETRY_SEC, idle=line_idle))
    for sym in SECTOR_ETFS + INDUSTRY_ETFS + tuple(_leader_pool()):
        jobs.append(Job(f"closes:{sym}", ibkr_reads.SOURCE, FOREVER, partial(ibkr_reads.rth_closes, sym),
                        gap_group="history", gap=MARKET_HISTORY_GAP_SEC, fresh=partial(_has_session, prior_session),
                        retry=MARKET_CLOSES_RETRY_SEC))
    runners = store().get("climate", now, 3600.0) or []
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
                partial(climate.refresh, now, sessions_needed=CLIMATE_SESSIONS), idle=MARKET_IDLE_CLIMATE_TTL_SEC)]
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


def for_lane(lane: str, now: float) -> list[Job]:
    return {"ibkr": ibkr_jobs, "history": history_jobs, "files": files_jobs}[lane](now)
