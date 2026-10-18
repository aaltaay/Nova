"""``massive_archive.py verify``: read every whole raw file that has no record yet through gzip and note the result in
``verified.jsonl`` (one line per file: {f, size, ok, why, at}). A damaged file is deleted, so the fetchers take it again;
an unreadable one (a disk error) is left alone and tried again next time. Four failures in one run halt the check
(``verify_halted.txt``): the checker may be the thing that is wrong, so nothing more is deleted until a person looks.
"""
from __future__ import annotations

import json
from datetime import datetime

from massive_env import NY, ROOT
from massive_bucket import PLAN_CACHE, VERIFY_HALT, WINDOW_START, load_verified, record_verified, verify_gzip
from massive_jobs import STOP, idle_priority, log, single_instance


def _verify_job(job: tuple[str, int]) -> tuple[str, int, bool, str]:
    rel, size = job
    ok, why = verify_gzip(ROOT / rel)
    return rel, size, ok, why


def verify_sweep(workers: int, only: str | None) -> int:
    """Read every whole raw file that has no record yet through gzip, newest first, and record the result."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    if VERIFY_HALT.exists():
        print(f"the integrity check halted itself earlier: read {VERIFY_HALT}, then delete it to start again"); return 2
    if not single_instance("NovaLabMassiveVerify"):
        print("another verify job is already running: nothing started"); return 0
    try:
        plan = json.loads(PLAN_CACHE.read_text(encoding="utf-8"))["plan"]
    except (OSError, ValueError, KeyError):
        print("no file list yet (plan_cache.json)"); return 1
    known = load_verified(); jobs = []
    for ds in ("trades_v1", "quotes_v1", "minute_aggs_v1", "day_aggs_v1"):
        for iso, size in plan.get(ds, {}).items():
            if iso[:4] < str(WINDOW_START.year) or (only and iso[:4] != only):
                continue
            rel = f"{ds}/{iso[:4]}/{iso[5:7]}/{iso}.csv.gz"
            try:
                whole = (ROOT / rel).stat().st_size == size
            except OSError:
                continue
            if whole and known.get(rel) is None:        # a file with a record (intact, or judged damaged and kept) is not read again
                jobs.append((iso, rel, size))
            elif whole and known[rel][0] != size:       # its size changed since the record: read it again
                jobs.append((iso, rel, size))
    jobs.sort(reverse=True)
    log(f"verify: {len(jobs)} files to read through gzip, {workers} workers")
    done = bad = 0
    with ProcessPoolExecutor(max_workers=workers, initializer=idle_priority) as ex:
        futs = [ex.submit(_verify_job, (rel, size)) for _iso, rel, size in jobs]
        for fut in as_completed(futs):
            rel, size, ok, why = fut.result(); done += 1
            record_verified(ROOT / rel, size, ok, why)
            if not ok:
                bad += 1
                if bad > 3:                             # four failures in one run: the checker may be the thing that is wrong, so delete nothing more
                    VERIFY_HALT.write_text(f"{datetime.now(NY).isoformat(timespec='seconds')}: {bad} files failed in one verify run (last: {rel}: {why}). "
                                           "Nothing more is deleted and the check does not start again until this file is removed. See verified.jsonl.", encoding="utf-8")
                    log("verify: HALTED after 4 failures in one run; nothing more is deleted (verify_halted.txt)")
                    ex.shutdown(wait=False, cancel_futures=True); break
                if not why.startswith("unreadable"):
                    log(f"DAMAGED {rel}: {why}; deleted, it is fetched again")
                    (ROOT / rel).unlink(missing_ok=True)
            if STOP.exists():
                ex.shutdown(wait=False, cancel_futures=True); log("verify: stopped by the STOP file"); break
    log(f"verify run ends: {done} files read, {bad} not intact")
    return 0
