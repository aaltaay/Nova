"""Durable historical replay jobs and ordered prints in the capture archive."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from capture.recorder import capture_root
from constants_sim import (
    SIM_HISTORY_DEFAULT_ROOT_WIN, SIM_HISTORY_DIR_ENV,
    SIM_HISTORY_MAX_PAGES, SIM_HISTORY_PAGE_SIZE, SIM_HISTORY_REQUEST_INTERVAL_SEC,
    SIM_HISTORY_REQUEST_TIMEOUT_SEC, SIM_HISTORY_RETRY_INTERVAL_SEC, SIM_SESSION_CLOSE_HOUR,
    SIM_HISTORY_SQLITE_TIMEOUT_SEC,
)
from sim import history_coverage as coverage
from sim.trading_day import last_open_day, require_supported

ET = ZoneInfo("America/New_York")
KINDS = ("bars", "trades")
ACTIVE = ("running", "pause_requested")
# Module aliases keep tests and one-off acquisition scripts able to override them.
PAGE_SIZE = SIM_HISTORY_PAGE_SIZE
REQUEST_INTERVAL = SIM_HISTORY_REQUEST_INTERVAL_SEC
RETRY_INTERVAL = SIM_HISTORY_RETRY_INTERVAL_SEC
REQUEST_TIMEOUT = SIM_HISTORY_REQUEST_TIMEOUT_SEC
MAX_PAGES = SIM_HISTORY_MAX_PAGES


def stale_after() -> float:
    """Seconds without a checkpoint before a running job counts as interrupted."""
    return REQUEST_TIMEOUT + 2 * REQUEST_INTERVAL


def window(symbol: str, date: str, start: str, end: str) -> dict:
    """Validate an operator-chosen replay window; the only gate on POST /select.

    The calendar check belongs here and nowhere deeper: this date is typed by a
    human, so a year the holiday table cannot vouch for is refused by name and
    rendered as a 422, rather than being accepted and then degrading silently
    two layers down (#386). A non-trading day INSIDE the range stays selectable
    and reports an empty tape — that is a deliberate diagnostic, pinned by
    test_weekend_holiday_selection_is_explicitly_empty_not_remapped.
    """
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9. -]{0,19}", symbol):
        raise ValueError("Enter a stock ticker")
    for value in (start, end):
        if not re.fullmatch(r"\d{2}:\d{2}", value):
            raise ValueError("Session times must be HH:MM Eastern")
    a = datetime.fromisoformat(f"{date}T{start}").replace(tzinfo=ET)
    b = datetime.fromisoformat(f"{date}T{end}").replace(tzinfo=ET)
    if a >= b or b.timestamp() > time.time():
        raise ValueError("Choose a completed historical window with start before end")
    require_supported(a.date())
    return dict(symbol=symbol, date=a.date().isoformat(), start=start, end=end,
                start_ts=int(a.timestamp()), end_ts=int(b.timestamp()),
                timezone="America/New_York", source="ibkr_historical")


def default_date(now: datetime | None = None) -> str:
    """Latest weekday, not an NYSE holiday, whose default session has closed.

    A pre-filled picker value, derived from the wall clock rather than chosen,
    so it degrades with ``last_open_day`` instead of refusing: a clock outside
    the supported range must not make the acquisition listing unanswerable.
    """
    now = (now or datetime.now(ET)).astimezone(ET)
    day = now.date()
    while True:
        day = last_open_day(day)
        close = datetime.combine(day, datetime.min.time(), tzinfo=ET).replace(hour=SIM_SESSION_CLOSE_HOUR)
        if close <= now:
            return day.isoformat()
        day -= timedelta(days=1)


def path():
    """``NOVA_SIM_HISTORY_DIR``; else, when the capture root was redirected
    (``NOVA_SIM_CAPTURE_DIR``), inside it -- an isolated stack must never write
    the operator's archive; else the durable F: archive, else the capture root."""
    configured = os.environ.get(SIM_HISTORY_DIR_ENV)
    default = Path(SIM_HISTORY_DEFAULT_ROOT_WIN)
    if configured:
        root = Path(configured)
    elif (os.environ.get("NOVA_SIM_CAPTURE_DIR") or "").strip():
        root = capture_root() / "historical"
    else:
        root = default if Path("F:/").exists() else capture_root() / "historical"
    root.mkdir(parents=True, exist_ok=True)
    return root / "replay.sqlite3"


@contextmanager
def connect():
    from sim.history_schema import initialize
    database = path()
    db = sqlite3.connect(database, timeout=SIM_HISTORY_SQLITE_TIMEOUT_SEC)
    db.row_factory = sqlite3.Row
    try:
        initialize(db, database)
        with db:
            yield db
    finally:
        db.close()


def save(job: dict, db=None):
    if db is None:
        with connect() as conn:
            save(job, conn)
        return
    db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?)", (job["id"], json.dumps(job)))


def _load(db, job_id: str) -> dict:
    row = db.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise ValueError("Download not found")
    return json.loads(row[0])


def get(job_id: str) -> dict:
    with connect() as db:
        return _load(db, job_id)


def jobs() -> list[dict]:
    with connect() as db:
        return [json.loads(r[0]) for r in db.execute("SELECT payload FROM jobs ORDER BY rowid DESC")]


def job_id_for(spec: dict, kind: str) -> str:
    if kind not in KINDS:
        raise ValueError("kind must be bars or trades")
    return hashlib.sha256(json.dumps([spec, kind], sort_keys=True).encode()).hexdigest()[:24]


def find(spec: dict, kind: str) -> dict | None:
    """Existing job for this exact window, without creating one."""
    try:
        return get(job_id_for(spec, kind))
    except ValueError as exc:
        if str(exc) != "Download not found":
            raise
        return None


def _new_job(spec: dict, kind: str) -> dict:
    return dict(spec, id=job_id_for(spec, kind), kind=kind, status="queued", cursor=spec["start_ts"],
                ranges=[], seek=None,
                count=0, volume=0, pages=0, error=None, contract=None,
                storage=str(path()), precision="seconds", updated=time.time(), started=None)


def create(spec: dict, kind: str) -> dict:
    existing = find(spec, kind)
    if existing is not None:
        return existing
    job = _new_job(spec, kind)
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO jobs VALUES (?,?)", (job["id"], json.dumps(job)))
    return get(job["id"])


def reserve_job(spec: dict, kind: str) -> dict:
    """Admission and ownership are atomic, including simultaneous API processes."""
    wanted = job_id_for(spec, kind)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        all_jobs = [json.loads(row[0]) for row in db.execute("SELECT payload FROM jobs")]
        if _active_elsewhere(all_jobs, None):
            raise ValueError("Another historical download is running; pause it first")
        job = next((row for row in all_jobs if row["id"] == wanted), None)
        if job and job["status"] == "complete":
            return job
        if (job and job["status"] == "failed"
                and time.time() - job["updated"] < RETRY_INTERVAL):
            raise ValueError(f"Wait {RETRY_INTERVAL:.0f} seconds before retrying an IBKR request")
        job = job or _new_job(spec, kind)
        job.update(status="running", error=None, updated=time.time())
        save(job, db)
        return job


def update(job_id: str, **fields) -> dict:
    """Atomic read-modify-write; never overwrites a newer row with a stale copy."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        job = _load(db, job_id)
        job.update(fields, updated=time.time())
        save(job, db)
        return job


def begin_run(job_id: str) -> dict:
    """Mark a worker's start without clobbering a pause requested meanwhile."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        job = _load(db, job_id)
        if job["status"] != "complete":
            job.update(status="pause_requested" if job["status"] == "pause_requested" else "running",
                       error=None, updated=time.time(), started=time.time(), run_cursor=job["cursor"],
                       run_covered=coverage.covered_seconds(coverage.job_ranges(job)))
            save(job, db)
        return job


def commit_page(job_id: str, cursor: int, rows: list[dict], next_cursor: int,
                complete: bool | None = None):
    """Rows, coverage and cursor are one transaction; ordinal preserves identical prints.

    The page covers [cursor, next_cursor). It is clipped at the next range already
    downloaded, so a jump-ahead can never store a print twice, and merged into the
    job's coverage. The cursor then moves to the next gap -- forward first, then
    wrapping to backfill from the window start. Completion is read off coverage
    (one range spanning the window); ``complete`` is accepted for old callers.
    """
    del complete
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        job = _load(db, job_id)
        if job["cursor"] != cursor:
            raise ValueError("Page cursor changed; committed page must not be replayed")
        ranges = coverage.job_ranges(job)
        stop = coverage.next_covered_start(ranges, cursor)
        if stop is not None and next_cursor > stop:
            next_cursor = stop
        rows = [row for row in rows if row["ts"] < next_cursor and not coverage.contains(ranges, row["ts"])]
        for offset, row in enumerate(rows):
            db.execute("INSERT INTO prints VALUES (?,?,?,?)",
                       (job_id, job["count"] + offset, row["ts"], json.dumps(row)))
        ranges = coverage.add(ranges, cursor, next_cursor)
        target = coverage.next_fetch(ranges, next_cursor, job["start_ts"], job["end_ts"])
        status = "complete" if target is None else (
            "pause_requested" if job["status"] == "pause_requested" else "running")
        job.update(ranges=ranges, cursor=job["end_ts"] if target is None else target,
                   count=job["count"] + len(rows),
                   volume=job["volume"] + sum(r["size"] for r in rows),
                   pages=job["pages"] + 1, status=status, error=None, updated=time.time())
        save(job, db)
    return job


def request_seek(job_id: str, ts: float) -> dict:
    """Ask a running download to fetch at ``ts`` next (playhead-first acquisition).

    Only records the wish; the worker moves its own cursor in ``apply_seek``
    before its next request, so no in-flight page is ever invalidated. A second
    already downloaded, outside the window, or a job that is not running is a
    no-op.
    """
    second = int(ts)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        job = _load(db, job_id)
        if (job["status"] not in ACTIVE or job["kind"] != "trades"
                or not job["start_ts"] <= second < job["end_ts"]
                or coverage.contains(coverage.job_ranges(job), second)):
            return job
        job["seek"] = second
        save(job, db)
        return job


def apply_seek(job_id: str) -> dict:
    """Worker-side: move the cursor to the gap at the pending seek, if any."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        job = _load(db, job_id)
        seek = job.get("seek")
        if seek is None:
            return job
        target = coverage.next_fetch(coverage.job_ranges(job), seek, job["start_ts"], job["end_ts"])
        job["seek"] = None
        if target is not None:
            job["cursor"] = target
        save(job, db)
        return job


def read_prints(job_id: str, *, through: int | None = None, limit: int = -1) -> list[dict]:
    """Prints in time order, same-second prints in their returned order.

    Ordered by (ts, ordinal), not ordinal alone: once the worker can jump ahead
    and backfill, insertion order stops being time order. A second is never split
    across pages, so ordinal still preserves IBKR's order within one. ``seq`` is
    the stored ordinal -- the print's stable identity within the job.
    """
    with connect() as db:
        return [dict(json.loads(r[1]), seq=r[0]) for r in db.execute(
            "SELECT ordinal, payload FROM prints WHERE job_id=? AND (? IS NULL OR ts<?) "
            "ORDER BY ts, ordinal LIMIT ?", (job_id, through, through, limit))]


def reserve_send() -> float:
    """Shared durable interval across process restarts and workers."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT sent FROM pacing WHERE id=1").fetchone()
        now = time.time()
        wait = max(0, (row[0] if row else 0) + REQUEST_INTERVAL - now)
        if not wait:
            db.execute("INSERT OR REPLACE INTO pacing VALUES (1,?)", (now,))
        return wait


def request_pause(job_id: str):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        job = _load(db, job_id)
        if job["status"] == "running":
            job["status"] = "pause_requested"
            save(job, db)
        return job


def save_candles(job_id: str, bars: list[dict]):
    with connect() as db:
        for row in bars:
            ts = int(datetime.fromisoformat(row["t"].replace("Z", "+00:00")).timestamp())
            db.execute("INSERT OR REPLACE INTO candles VALUES (?,?,?)", (job_id, ts, json.dumps(row)))


def read_candles(symbol: str, start: int, end: int):
    with connect() as db:
        rows = db.execute("""SELECT c.payload FROM candles c JOIN jobs j ON j.id=c.job_id
            WHERE json_extract(j.payload, '$.symbol')=?
            AND json_extract(j.payload, '$.status')='complete'
            AND c.ts>=? AND c.ts<? ORDER BY c.ts""", (symbol, start, end))
        return list({json.loads(r[0])["t"]: json.loads(r[0]) for r in rows}.values())


def _active_elsewhere(all_jobs: list[dict], job_id: str | None) -> bool:
    now = time.time()
    return any(item["id"] != job_id and item["status"] in ACTIVE
               and now - item["updated"] < stale_after() for item in all_jobs)


def ensure_idle(job_id: str | None = None):
    """Refuse before any job row is created while another download is active."""
    if _active_elsewhere(jobs(), job_id):
        raise ValueError("Another historical download is running; pause it first")


def claim(job_id: str):
    """One active acquisition across API processes sharing this archive."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        all_jobs = [json.loads(r[0]) for r in db.execute("SELECT payload FROM jobs")]
        if _active_elsewhere(all_jobs, None):
            raise ValueError("Another historical download is running; pause it first")
        job = next((j for j in all_jobs if j["id"] == job_id), None)
        if job is None:
            raise ValueError("Download not found")
        job.update(status="running", error=None, updated=time.time())
        save(job, db)
        return job
