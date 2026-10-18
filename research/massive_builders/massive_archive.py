"""Keep the Massive tick-trade history offline. Research tooling (the trades archive).

Per trading day, the day's trades flat file (0.5-3 GB gzip) is downloaded in ranged chunks and turned into
  A. trades_flow_v1/YYYY/MM/YYYY-MM-DD.parquet   -- one row per (ticker, minute): counts and shares by kind
     (off exchange, retail buy / sell by the sub-penny rule, midpoint, sweeps, odd lots, big prints, venues)
  B. trades_movers_v1/YYYY/MM/YYYY-MM-DD.parquet -- every raw trade of that day's movers and the lab's own names
(trades_products.py builds both; docs/massive-builders.md defines every column.)
The raw file is kept when a raw folder has room (archive_config.json: raw_dirs, keep_raw, other_drive_floor_gb), else
deleted after processing (ten years of raw files are 3.35 TB). On the products' drive a raw file is kept only while that
leaves room for the products of every day still to do. Minute and day aggregates older than what is on disk are fetched
first. Resumable; one line per day in archive.log; state in archive_state.json (process_state.json for `process`).
Nothing is downloaded once the drive is at its floor; a day that failed is tried again in a later pass; a second copy
of the job refuses to start.

It runs whenever it is started, at any hour. Create <NOVA_MARKET_DATA_DIR>/STOP to make it stop after the file in hand.
Credentials: the MASSIVE_S3_* pair from the environment or the .env (massive_env.py; never printed). CPU priority: below normal.

Order (operator, 2026-10-05: "year by year, walking backward from 2026, finishing each year before the previous one"):
one period per calendar year, newest year first, newest day first inside it. Downloading and building are separate jobs:
`fetch` only downloads the raw files, byte for byte as Massive serves them (a day counts as downloaded only when the file's
size equals the size Massive lists); `process` builds the two derived tables from raw files already on disk. A crashed
table build can no longer take a download with it, and a failed build no longer deletes a finished download.

Usage (repo root):
  py -3 research/massive_builders/massive_archive.py plan [year]               # what is left, sizes
  py -3 research/massive_builders/massive_archive.py one 2016-11-01            # one day, for checking
  py -3 research/massive_builders/massive_archive.py fetch [workers] [year]    # raw files only (and the year's minute / day bars)
  py -3 research/massive_builders/massive_archive.py process [workers]         # derived tables, for days whose raw file is on disk
  py -3 research/massive_builders/massive_archive.py verify [workers] [year]   # read every whole raw file through gzip (raw_verify.py)
  py -3 research/massive_builders/massive_archive.py run [workers] [year]      # both in one worker per day (the old way)
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import date, datetime
from multiprocessing import Event, Process, Queue, Value
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import massive_bucket as mf  # noqa: E402
import trades_products as tp  # noqa: E402
from massive_env import NY, ROOT, TMP  # noqa: E402
from massive_jobs import (  # noqa: E402
    STOP, idle_priority, log, parent_gone, pid_alive, single_instance, wait_for_memory, wait_for_quiet,
)

STATE = ROOT / "archive_state.json"
FREE_FLOOR_GB = 200                     # nothing is downloaded or written under this much free space on the products' drive
RAW_FLOOR_GB = 250                       # a raw file stays on the products' drive only above this, after the room set aside for products
PRODUCT_SHARE = 0.17                     # products are about 14% of a day's raw gzip (pilot: 177 MB from 1.26 GB)
MAX_PASSES = 6
NO_ROOM = "no room for the products"


def free_gb() -> float:
    """Free space on the products' drive."""
    root = tp.products_root()
    return shutil.disk_usage(root if root.exists() else root.anchor).free / 2**30


def cleanup_scratch() -> None:
    """Scratch folders of table builds that were killed (a power cut, a restart) hold gigabytes of spill files: remove those whose process is gone."""
    base = TMP / "duck"
    for d in (list(base.iterdir()) if base.exists() else []):
        if d.is_dir() and d.name.isdigit() and not pid_alive(int(d.name)):
            shutil.rmtree(d, ignore_errors=True)


def trading_days(s3, a: date, b: date) -> dict[date, tuple[str, int]]:
    return mf.dataset_days(s3, "trades_v1", a, b)


def raw_dirs() -> list[Path]:
    return [Path(p) for p in tp.config().get("raw_dirs", [str(ROOT / "trades_v1")])]


def raw_kept(d: date, size: int) -> Path | None:
    for root in raw_dirs():
        p = root / mf.sub(d, ".csv.gz")
        try:
            if p.exists() and p.stat().st_size == size:
                return p
        except OSError:
            continue
    return None


def on_products_drive(p: Path) -> bool:
    return p.anchor.lower() == tp.products_root().anchor.lower()


def raw_home(d: date, size: int, reserve_gb: float = 0.0) -> Path | None:
    """Where this day's raw file would be kept: the first configured folder whose drive exists and has room.

    On the products' own drive the room set aside for the products still to make (reserve_gb) comes first."""
    cfg = tp.config()
    if not cfg.get("keep_raw", True):
        return None
    for root in raw_dirs():
        try:
            if not Path(root.anchor).exists():
                continue
            floor = RAW_FLOOR_GB + reserve_gb if on_products_drive(root) else float(cfg.get("other_drive_floor_gb", 20))
            root.mkdir(parents=True, exist_ok=True)
            if (shutil.disk_usage(root).free - size) / 2**30 >= floor:
                return root / mf.sub(d, ".csv.gz")
        except OSError:
            continue
    return None


def reserve_gb(todo_bytes: float) -> float:
    """Room on the products' drive set aside for the products of the days still to do."""
    return PRODUCT_SHARE * max(todo_bytes, 0.0) / 2**30


def fetch_day(s3, d: date, key: str, size: int) -> str:
    """Raw file only, exactly as Massive serves it, kept where raw_home says. 'have' | 'raw' | the reason nothing was done."""
    if raw_kept(d, size) is not None:
        return "have"
    home = raw_home(d, size)
    if home is None:
        log(f"{d} not fetched: no raw folder has room")
        return NO_ROOM
    try:
        secs = mf.fetch(s3, key, home, size)
    except PermissionError:
        log(f"{d} the server refused the file (403, asked four times)"); return "forbidden"
    log(f"{d} trades raw: {size / 2**30:.2f} GB in {secs:.0f}s ({size / 2**20 / max(secs, 0.1):.1f} MB/s)")
    return "raw" if mf.check_new_file(home, size) else "damaged"


def do_day(s3, d: date, key: str, size: int, threads: int = 3, reserve: float = 0.0) -> str:
    """'ok' = products made; 'raw' = raw file fetched for a day that had its products; else why nothing was done."""
    a_out, b_out = tp.out_paths(d)
    products = a_out.exists() and b_out.exists()
    keep_raw = tp.config().get("keep_raw", True)
    kept = raw_kept(d, size)
    if products and (kept is not None or not keep_raw):
        return "have"
    home = kept or raw_home(d, size, reserve)
    if products and home is None:
        return "no room for the raw file"            # products exist; the raw file waits for a drive with room
    raw = home or TMP / f"{d.isoformat()}.csv.gz"
    have_raw = raw.exists() and raw.stat().st_size == size
    if not products and not tp.agg_file("minute_aggs_v1", d).exists() and not (tp.EVT / f"d={d.isoformat()}" / "part.parquet").exists():
        log(f"{d} waits: its minute aggregates are not on disk, so the day's movers cannot be named")
        return "no minute aggregates"
    if not products:                                  # room is checked BEFORE the download, never after it
        need = ((0 if have_raw or not on_products_drive(raw) else size) + PRODUCT_SHARE * size) / 2**30 + 1.0
        if free_gb() - need < FREE_FLOOR_GB:
            log(f"{d} not fetched: {free_gb():.0f} GB free on the products' drive, floor {FREE_FLOOR_GB} (this day needs {need:.1f} GB)")
            return NO_ROOM
    try:
        secs = mf.fetch(s3, key, raw, size) if not have_raw else 0.0
    except PermissionError:
        log(f"{d} forbidden (outside the plan's window)"); return "forbidden"
    rate = f"{size / 2**30:.2f} GB in {secs:.0f}s ({size / 2**20 / max(secs, 0.1):.1f} MB/s)" if secs else f"{size / 2**30:.2f} GB on disk"
    if products:
        log(f"{d} raw kept: {rate} -> {raw.parent}")
        return "raw"
    try:
        r = tp.process(d, raw, threads)
    except Exception as exc:  # noqa: BLE001 - the table is built again next run
        msg = str(exc)
        log(f"{d} FAILED to process: {msg[:200]}")
        if home is None or "gzip" in msg.lower():           # only a damaged file (or a scratch copy) is thrown away: a full memory or a
            raw.unlink(missing_ok=True)                     # crashed build is not the download's fault, and it cost up to 3 GB to fetch
        return "failed"
    if home is None:
        raw.unlink(missing_ok=True)
    log(f"{d} ok: {rate}, {'raw kept' if home else 'raw deleted (no room)'}; {r['trades']:,} trades -> flow {r['flow_rows']:,} rows "
        f"{r['flow_mb']:.0f} MB ({r['flow_s']:.0f}s), movers {r['movers']} tickers {r['mover_trades']:,} trades {r['movers_mb']:.0f} MB ({r['raw_s']:.0f}s)")
    return "ok"


def fetch_aggs(s3, year: int | None = None) -> None:
    """Minute and day aggregates the disk does not have yet (one year when asked: the year in hand)."""
    first, last = (date(year, 1, 1), min(date(year, 12, 31), date.today())) if year else (mf.WINDOW_START, date.today())
    for ds in ("day_aggs_v1", "minute_aggs_v1"):
        got = nbytes = 0
        for y, m in mf.months(max(first, mf.WINDOW_START), last):
            if not wait_for_quiet(light=True):
                return
            for key, size in sorted(mf.listing(s3, ds, y, m).items()):
                try:
                    d = date.fromisoformat(key.rsplit("/", 1)[-1].removesuffix(".csv.gz"))
                except ValueError:
                    continue
                dest = tp.agg_file(ds, d)
                if d < mf.WINDOW_START or (dest.exists() and dest.stat().st_size == size):
                    continue
                try:
                    mf.fetch(s3, key, dest, size); got += 1; nbytes += size
                except PermissionError:
                    continue
        log(f"{ds}: {got} new files, {nbytes / 2**30:.2f} GB")


def aggs_proc(year: int | None = None) -> None:
    idle_priority()
    try:
        fetch_aggs(mf.client(), year)
    except Exception as exc:  # noqa: BLE001 - the next run asks again
        log(f"aggregates FAILED: {str(exc)[:200]}")


def worker(q: Queue, threads: int, left, noroom, light: bool = False, mode: str = "both") -> None:
    """left: raw bytes of the days still without products (shared); noroom: set when the drive reaches its floor.
    mode: 'fetch' downloads raw files only (it never waits for memory: a download needs almost none), 'process' and
    'both' build the tables (they hold while the PC has under MIN_FREE_RAM_GB free).
    light: unused since the quiet hours were removed (kept for the callers)."""
    idle_priority()
    s3 = mf.client()
    while True:
        if parent_gone() or not wait_for_quiet(light) or (mode != "fetch" and not wait_for_memory()):   # the STOP file; the PC's free memory
            return
        job = q.get()
        if job is None or noroom.is_set():
            return
        d, key, size = job
        try:
            st = fetch_day(s3, d, key, size) if mode == "fetch" else do_day(s3, d, key, size, threads, reserve_gb(left.value))
        except Exception as exc:  # noqa: BLE001
            log(f"{d} FAILED: {str(exc)[:200]}")
            try:
                s3 = mf.client()
            except Exception:  # noqa: BLE001
                time.sleep(60)
            continue
        if st == "ok":
            with left.get_lock():
                left.value -= size
        elif st == NO_ROOM:
            noroom.set()
            return


def plan(s3, mode: str = "both", only: str | None = None) -> tuple[list[tuple[str, date, str, int]], int]:
    """(jobs in fetch order, raw bytes of the days that still lack their products).
    mode 'fetch': the days whose raw file is not on disk whole; 'process': the days with their raw file and without both
    tables; 'both': the old rule. only: one year's name (the periods are years)."""
    keep_raw = tp.config().get("keep_raw", True)
    rows = []
    for name, a, b, newest_first in mf.year_periods():
        if only and name != only:
            continue
        days = trading_days(s3, max(a, mf.WINDOW_START), min(b, date.today()))
        for d in sorted(days, reverse=newest_first):
            key, size = days[d]
            a_out, b_out = tp.out_paths(d)
            rows.append((name, d, key, size, a_out.exists() and b_out.exists()))
    todo = sum(size for _, _, _, size, products in rows if not products)
    res = reserve_gb(todo)
    if mode == "fetch":
        jobs = [(name, d, key, size) for name, d, key, size, _products in rows if raw_kept(d, size) is None]
    elif mode == "process":
        jobs = [(name, d, key, size) for name, d, key, size, products in rows if not products and raw_kept(d, size) is not None]
    else:
        jobs = [(name, d, key, size) for name, d, key, size, products in rows
                if not products or (keep_raw and raw_kept(d, size) is None and raw_home(d, size, res) is not None)]
    return jobs, todo


def progress() -> tuple[int, int]:
    """(days with their flow file, raw day files kept) -- what a pass is judged by."""
    fdir = tp.products_root() / "trades_flow_v1"
    flow = sum(1 for _ in fdir.rglob("*.parquet")) if fdir.exists() else 0
    raw = 0
    for root in raw_dirs():
        try:
            raw += sum(1 for _ in root.rglob("*.csv.gz")) if root.exists() else 0
        except OSError:
            pass
    return flow, raw


def summarize(js) -> dict:
    by: dict[str, list] = {}
    for name, _, _, size in js:
        by.setdefault(name, [0, 0]); by[name][0] += 1; by[name][1] += size
    return {k: {"days": v[0], "gb": round(v[1] / 2**30, 1)} for k, v in by.items()}


def run_passes(s3, mode: str, only: str | None, workers: int, jobs: list, todo: int) -> None:
    """Up to MAX_PASSES passes of worker processes over the plan, with the year's minute / day bars beside them."""
    state_file = STATE.with_name("process_state.json") if mode == "process" else STATE
    if mode != "fetch":
        cleanup_scratch()                            # spill folders of builds that were killed
    aggs = None
    if mode != "process":                            # the minute and day bars come beside the trades, in their own process; this job waits for them at the end
        aggs = Process(target=aggs_proc, args=(int(only) if only else None,), daemon=True); aggs.start()
    summary = summarize(jobs)
    for npass in range(1, MAX_PASSES + 1):
        if npass > 1:
            jobs, todo = plan(s3, mode, only); summary = summarize(jobs)
        if not jobs:
            log(f"{mode}: nothing left to do{f' for {only}' if only else ''}"); break
        log(f"{mode} pass {npass} starts{f' ({only})' if only else ''}: {len(jobs)} days left {summary}; {workers} workers; {free_gb():.0f} GB free on "
            f"{tp.products_root().anchor}, {reserve_gb(todo):.0f} GB of it set aside for products")
        if not wait_for_quiet(light=True):
            break
        before = progress()
        q: Queue = Queue()
        for _, d, key, size in jobs:
            q.put((d, key, size))
        for _ in range(workers):
            q.put(None)
        left = Value("d", float(todo)); noroom = Event()
        procs = [Process(target=worker, args=(q, 3, left, noroom, i == 0, mode)) for i in range(workers)]
        for p in procs:
            p.start()
        respawns = 0; next_state = 0.0
        while any(p.is_alive() for p in procs):
            time.sleep(15)
            for i, p in enumerate(procs):                # a worker that crashed (not one that ended) is replaced: its day is picked up again next pass
                if p.exitcode not in (None, 0) and respawns < 4 * workers and not STOP.exists() and not noroom.is_set():
                    log(f"a {mode} worker ended with exit code {p.exitcode}; a new one takes its place ({respawns + 1} so far this pass)")
                    procs[i] = Process(target=worker, args=(q, 3, left, noroom, False, mode)); procs[i].start(); respawns += 1
            if time.time() < next_state:
                continue
            next_state = time.time() + 60
            try:
                flow_days, raw_files = progress()
                state_file.write_text(json.dumps({"at": datetime.now(NY).isoformat(timespec="seconds"), "mode": mode, "year": only, "pass": npass,
                                                  "days_with_products": flow_days, "raw_files_kept": raw_files, "days_in_this_pass": len(jobs),
                                                  "free_gb_products_drive": round(free_gb(), 1), "workers_alive": sum(p.is_alive() for p in procs),
                                                  "workers_replaced": respawns}), encoding="utf-8")
            except OSError:
                pass
        try:                                         # jobs nobody took (STOP, the floor) must not hold the process at exit
            while True:
                q.get_nowait()
        except Exception:  # noqa: BLE001 - queue.Empty ends the drain
            pass
        q.close(); q.cancel_join_thread()
        after = progress()
        log(f"{mode} pass {npass} ends: {after[0] - before[0]} table days built, {after[1] - before[1]} raw files added; {free_gb():.0f} GB free on {tp.products_root().anchor}")
        if STOP.exists():
            log("stopped by the STOP file"); break
        if noroom.is_set():
            log(f"stopped: the drive is at its floor ({FREE_FLOOR_GB} GB free). The rest waits for room or for another folder in archive_config.json raw_dirs"); break
        if after == before:
            log(f"no progress in this {mode} pass: stopping (see the lines above)"); break
    if aggs is not None:
        aggs.join()                                  # the year's minute and day bars finish before this job ends
    log(f"{mode} run ends")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd in ("-h", "--help", "help"):
        print(__doc__); return 0
    idle_priority()
    ROOT.mkdir(parents=True, exist_ok=True); TMP.mkdir(parents=True, exist_ok=True)
    if cmd == "verify":
        from raw_verify import verify_sweep
        return verify_sweep(int(sys.argv[2]) if len(sys.argv) > 2 else 2, sys.argv[3] if len(sys.argv) > 3 else None)
    s3 = mf.client()
    if cmd == "one":
        d = date.fromisoformat(sys.argv[2])
        days = trading_days(s3, d, d)
        if d not in days:
            sys.exit(f"no trades file for {d}")
        print(do_day(s3, d, *days[d], threads=4)); return 0
    mode = {"fetch": "fetch", "process": "process"}.get(cmd, "both")
    workers = int(sys.argv[2]) if cmd != "plan" and len(sys.argv) > 2 else 3
    only = (sys.argv[2] if cmd == "plan" else sys.argv[3]) if len(sys.argv) > (2 if cmd == "plan" else 3) else None
    jobs, todo = plan(s3, mode, only)
    print(json.dumps({"mode": mode, "year": only, "left": summarize(jobs), "free_gb_products_drive": round(free_gb(), 1),
                      "products_root": str(tp.products_root()), "raw_dirs": [str(p) for p in raw_dirs()],
                      "set_aside_for_products_gb": round(reserve_gb(todo), 1), "raw_kept_above_gb": round(RAW_FLOOR_GB + reserve_gb(todo), 1),
                      "stop_under_gb": FREE_FLOOR_GB}, indent=1))
    if cmd == "plan":
        return 0
    if not single_instance("NovaLabMassiveProcess" if mode == "process" else "NovaLabMassiveArchive"):
        print("another copy of this archive job is already running: nothing started"); return 0
    run_passes(s3, mode, only, workers, jobs, todo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
