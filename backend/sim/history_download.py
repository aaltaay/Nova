"""Bounded resumable acquisition; Gateway adapter is injected for verification."""
from __future__ import annotations

import asyncio
import logging
import math
import threading
import time

from sim import history_store as store

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


async def run(job_id: str, gateway, stop: threading.Event, *, paced=True):
    job = store.begin_run(job_id)
    if job["status"] == "complete":
        return job
    logger.info("Historical replay started job=%s symbol=%s cursor=%s", job_id, job["symbol"], job["cursor"])
    try:
        identity = await asyncio.wait_for(gateway.open(job["symbol"]), store.REQUEST_TIMEOUT)
        if job["contract"] and job["contract"] != identity:
            raise ValueError("Contract identity changed; refusing to mix downloads")
        job = store.update(job_id, contract=identity)  # also refreshes the liveness heartbeat
        while job["pages"] < store.MAX_PAGES:
            if stop.is_set() or store.get(job_id)["status"] == "pause_requested":
                return store.update(job_id, status="paused")
            if paced:
                wait = store.reserve_send()
                if wait:
                    await asyncio.sleep(min(wait, 1))
                    continue
            if job["kind"] == "bars":
                bars = await asyncio.wait_for(gateway.bars(job), store.REQUEST_TIMEOUT)
                return store.update(job_id, status="complete", cursor=job["end_ts"], error=None,
                                    **persist_candles(job, bars))
            response = await asyncio.wait_for(gateway.trades(job["cursor"]), store.REQUEST_TIMEOUT)
            rows, following, complete = page(response, job["cursor"], job["end_ts"])
            job = store.commit_page(job_id, job["cursor"], rows, following, complete)
            logger.info("Historical replay checkpoint job=%s pages=%s count=%s cursor=%s status=%s",
                        job_id, job["pages"], job["count"], job["cursor"], job["status"])
            if complete:
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
        from ibkr.replay_history_gateway import ReplayHistoryGateway
        try:
            asyncio.run(run(job_id, ReplayHistoryGateway(), stop))
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


def list_jobs():
    with _lock:
        active = set(_active)
    result = store.jobs()
    for job in result:
        if (job["status"] in store.ACTIVE and job["id"] not in active
                and time.time() - job["updated"] > store.stale_after()):
            job["status"] = "interrupted"
    from sim.history_progress import progress
    return [progress(job) for job in result]
