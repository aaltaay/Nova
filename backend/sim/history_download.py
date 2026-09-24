"""Bounded resumable acquisition; Gateway adapter is injected for verification."""
from __future__ import annotations

import asyncio
import logging
import math
import threading
import time

from constants_sim import SIM_HISTORY_GATEWAY_NOT_ANSWERING, SIM_HISTORY_PRIOR_CLOSE_SOURCE
from sim import history_coverage as coverage, history_store as store

logger = logging.getLogger(__name__)
_lock = threading.RLock()
_active: dict[str, threading.Event] = {}


def page(rows: list[dict], cursor: int, end: int) -> tuple[list[dict], int, bool]:
    if not rows:
        if cursor < end:
            raise ValueError("IBKR returned an empty page before the window ended; progress preserved, resume to retry")
        return [], end, True
    stamps = [r["ts"] for r in rows]
    if stamps != sorted(stamps) or stamps[0] < cursor:
        raise ValueError("IBKR returned an overlapping or unordered page; progress preserved")
    if any(int(t) != t for t in stamps):
        raise ValueError("Historical TRADES must have whole-second timestamps")
    if any(not math.isfinite(r["price"]) or not math.isfinite(r["size"])
           or r["price"] <= 0 or r["size"] < 0 for r in rows):
        raise ValueError("Invalid historical trade price or size")
    # IBKR completes the final second, including >1000 trades when necessary.
    following = min(end, stamps[-1] + 1)
    if following <= cursor:
        raise ValueError("Historical download did not advance")
    return [r for r in rows if r["ts"] < end], following, following == end


def persist_candles(job: dict, bars: list[dict]) -> dict:
    """Keep the job's candles, then upsert the shared chart store (ADR 012)."""
    from bars_store import write_payload
    from ibkr.historical_derive import BUCKET_SEC, bar_unix, derive_from_1min
    store.save_candles(job["id"], bars)
    write_payload(dict(symbol=job["symbol"], timeframe="1Min", bars=bars))
    for tf in BUCKET_SEC:
        write_payload(dict(symbol=job["symbol"], timeframe=tf, bars=[
            r for r in derive_from_1min(bars, tf)
            if bar_unix(r) >= job["start_ts"] and bar_unix(r) + BUCKET_SEC[tf] <= job["end_ts"]]))
    return {"count": len(bars), "volume": sum(r["v"] for r in bars), "pages": 1}


async def _answered(awaitable, stage: str):
    """Await one IBKR round trip; a timeout says where and what it likely means.

    A bare ``TimeoutError`` reached the operator as the whole error. It almost
    always means Gateway accepted the socket but IBKR's side is not answering --
    a logged-out session, a pending 2FA prompt, or overnight maintenance.
    """
    try:
        return await asyncio.wait_for(awaitable, store.REQUEST_TIMEOUT)
    except TimeoutError as exc:
        raise TimeoutError(
            f"{SIM_HISTORY_GATEWAY_NOT_ANSWERING} within {store.REQUEST_TIMEOUT:g}s while {stage}: "
            "IB Gateway accepted the connection but IBKR is not responding -- check the Gateway "
            "window for a login, 2FA prompt or maintenance notice"
        ) from exc


async def record_prior_close(job_id: str, job: dict, gateway) -> dict:
    """Store IBKR's regular-hours close of the session before the job's day (#542).

    The replay's previous close reads it when neither a recorded tick 9 nor the
    leaderboard has one (``sim.prior_close``). A series that lacks that session
    stores ``prior_close: None`` -- IBKR answered, and an older close is never
    taken. A failed request, or an empty answer (ib_async's timeout returns
    one), stores nothing, so the next run asks again. It never fails the
    download: the prints do not depend on it.
    """
    from sim.prior_close import prior_session_close

    try:
        closes = await _answered(gateway.daily_closes(job["date"]), "fetching the prior close")
    except Exception:
        logger.warning("Historical replay: prior close unavailable for %s %s; the download continues",
                       job["symbol"], job["date"], exc_info=True)
        return job
    if not closes:
        logger.warning("Historical replay: IBKR sent no daily closes for %s before %s; asked again next run",
                       job["symbol"], job["date"])
        return job
    found = prior_session_close(closes, job["date"])
    prior = (dict(close=found[1], date=found[0], source=SIM_HISTORY_PRIOR_CLOSE_SOURCE)
             if found else None)
    return store.update(job_id, prior_close=prior)


async def run(job_id: str, gateway, stop: threading.Event, *, paced=True):
    job = store.begin_run(job_id)
    if job["status"] == "complete":
        return job
    logger.info("Historical replay started job=%s symbol=%s cursor=%s", job_id, job["symbol"], job["cursor"])
    try:
        identity = await _answered(gateway.open(job["symbol"]), f"identifying {job['symbol']}")
        if job["contract"] and job["contract"] != identity:
            raise ValueError("Contract identity changed; refusing to mix downloads")
        job = store.update(job_id, contract=identity)  # also refreshes the liveness heartbeat
        prior_asked = "prior_close" in job
        while job["pages"] < store.MAX_PAGES:
            if stop.is_set() or store.get(job_id)["status"] == "pause_requested":
                # A seek belongs to the moment it was asked; a later resume starts clean.
                return store.update(job_id, status="paused", seek=None)
            if paced:
                wait = store.reserve_send()
                if wait:
                    await asyncio.sleep(min(wait, 1))
                    continue
            if not prior_asked:
                # Once per run, paced like any page, before the first one.
                prior_asked = True
                job = await record_prior_close(job_id, job, gateway)
                continue
            if job["kind"] == "bars":
                bars = await _answered(gateway.bars(job), "fetching candles")
                # One request fetches the whole window's candles, so a finished
                # candle job covers it -- "complete - 0%" read otherwise (C40).
                return store.update(job_id, status="complete", cursor=job["end_ts"], error=None,
                                    ranges=[[job["start_ts"], job["end_ts"]]], **persist_candles(job, bars))
            # Playhead-first: jump to where the operator scrubbed, just before the
            # request (never mid-page), then stop this page at data already held.
            job = store.apply_seek(job_id)
            limit = min(coverage.next_covered_start(coverage.job_ranges(job), job["cursor"])
                        or job["end_ts"], job["end_ts"])
            response = await _answered(gateway.trades(job["cursor"]), "fetching trades")
            rows, following, _ = page(response, job["cursor"], limit)
            job = store.commit_page(job_id, job["cursor"], rows, following)
            logger.info("Historical replay checkpoint job=%s pages=%s count=%s cursor=%s status=%s",
                        job_id, job["pages"], job["count"], job["cursor"], job["status"])
            if job["status"] == "complete":
                return job
        raise ValueError("Page limit reached; narrow the requested session window")
    except Exception as exc:
        logger.exception("Historical replay download failed: %s", job_id)
        return store.update(job_id, status="failed", error=str(exc) or type(exc).__name__)
    finally:
        gateway.close()


def ensure_idle(job_id: str | None = None):
    """Refuse a new download before its job row exists (no orphan queued jobs)."""
    with _lock:
        if _active and job_id not in _active:
            raise ValueError("Another historical download is running; pause it first")
    store.ensure_idle(job_id)


def begin(spec: dict, kind: str) -> dict:
    """Reserve before creating a row; refused simultaneous requests leave no orphan."""
    with _lock:
        wanted = store.job_id_for(spec, kind)
        if _active:
            if wanted in _active:
                return store.get(wanted)
            raise ValueError("Another historical download is running; pause it first")
        return start(store.reserve_job(spec, kind)["id"], reserved=True)


def start(job_id: str, *, reserved: bool = False) -> dict:
    with _lock:
        if _active:
            if job_id in _active:
                return store.get(job_id)
            raise ValueError("Another historical download is running; pause it first")
        job = store.get(job_id)
        if job["status"] == "complete":
            return job
        if (not reserved and job["status"] in store.ACTIVE
                and time.time() - job["updated"] < store.stale_after()):
            raise ValueError("Download is active in another worker; wait for its checkpoint")
        if job["status"] == "failed" and time.time() - job["updated"] < store.RETRY_INTERVAL:
            raise ValueError(f"Wait {store.RETRY_INTERVAL:.0f} seconds before retrying an IBKR request")
        job = job if reserved else store.claim(job_id)
        stop = threading.Event()
        _active[job_id] = stop

    def worker():
        # Everything the worker does is inside the try: a worker that dies before
        # its first request (an import or gateway construction error) used to leave
        # its id in ``_active`` and the job "running" -- a phantom that refused
        # every other download until a restart (QA 2026-09-22, R23).
        try:
            from ibkr.replay_history_gateway import ReplayHistoryGateway

            asyncio.run(run(job_id, ReplayHistoryGateway(), stop))
        except Exception as exc:
            logger.exception("Historical replay worker died before finishing: %s", job_id)
            try:
                store.update(job_id, status="failed", error=f"Download worker failed: {exc}")
            except Exception:
                logger.exception("Historical replay: could not mark job %s failed", job_id)
        finally:
            with _lock:
                _active.pop(job_id, None)
    threading.Thread(target=worker, daemon=True, name="historical-replay").start()
    return job


def pause(job_id: str):
    with _lock:
        if job_id in _active:
            _active[job_id].set()
    return store.request_pause(job_id)


def _interrupted(job: dict, active: set[str], now: float) -> bool:
    """An active status no worker in this process is advancing, past its liveness window."""
    return job["status"] in store.ACTIVE and job["id"] not in active and now - job["updated"] > store.stale_after()


def effective_status(job: dict) -> str:
    """The status the desk should read for ``job`` -- ``interrupted`` for a dead worker's
    ``running`` (the rule ``list_jobs`` applies; also read by the replay snapshot, C38)."""
    with _lock:
        active = set(_active)
    return "interrupted" if _interrupted(job, active, time.time()) else job["status"]


def list_jobs():
    with _lock:
        active = set(_active)
    result = store.jobs()
    now = time.time()
    for job in result:
        if _interrupted(job, active, now):
            job["status"] = "interrupted"
    from sim.history_progress import progress
    return [progress(job) for job in result]


def follow_playhead(ts: float) -> dict | None:
    """Point the loaded selection's running trades download at the playhead.

    Called when the operator commits a scrub. If the selection's own trades job
    is running and that second is not downloaded yet, the worker fetches there
    next (``store.request_seek``). Anything else -- no selection, a paused or
    finished job, a covered second -- does nothing. Never raises into the clock.
    """
    from sim import history_playback
    try:
        selected = history_playback.status()
        if not selected:
            return None
        job = store.find({k: selected[k] for k in (
            "symbol", "date", "start", "end", "start_ts", "end_ts", "timezone", "source")}, "trades")
        return store.request_seek(job["id"], ts) if job else None
    except Exception:
        logger.warning("Historical replay: could not follow the playhead", exc_info=True)
        return None
