"""Massive quotes archive (Stocks Advanced, bought 2026-10-05): every day's NBBO quote file, ten years, onto the data
drive. Research tooling.

Per trading day:
  A. raw    <NOVA_MARKET_DATA_DIR>/quotes_v1/YYYY/MM/YYYY-MM-DD.csv.gz          the flat file as Massive serves it (kept)
  B. movers <NOVA_MARKET_DATA_DIR>/quotes_movers_v1/YYYY/MM/YYYY-MM-DD.parquet  every quote of the day's movers and the
     lab's own names (the same ticker list as the trades archive's movers product: trades_products.movers)
Order (operator, 2026-10-05: "year by year, walking backward from 2026, finishing each year before the previous one"):
one period per calendar year, newest year first, newest day first inside it. The operator also said "keep it for the last
10 yrs, once we finish that, we can start download the other 10".
`fetch` downloads the raw file only, byte for byte as Massive serves it (a day counts as downloaded only when the file's
size equals the size Massive lists). The movers product (B) is built by `run` and is not part of the download.

Room: a day is fetched only if the drive keeps QUOTE_FLOOR_GB free after its raw file and product. The trades archive's
STOP file pauses this job too. One copy at a time (named mutex). Resumable: ranged downloads, and a day whose product
exists is never redone.
Usage (repo root): py -3 research/massive_builders/quotes_archive.py plan [year] | fetch [workers] [year] | run [workers] [year] | one YYYY-MM-DD
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import date, datetime
from multiprocessing import Event, Process, Queue
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import massive_bucket as mf  # noqa: E402
import massive_jobs as mj  # noqa: E402
import trades_products as tp  # noqa: E402
from massive_env import NY, ROOT  # noqa: E402

RAW_DIR = ROOT / "quotes_v1"
OUT_DIR = ROOT / "quotes_movers_v1"
LOG = ROOT / "quotes_archive.log"
STATE = ROOT / "quotes_state.json"
TMP = ROOT / "_qtmp"
QUOTE_FLOOR_GB = 300
NO_ROOM = "no room for the products"     # massive_archive.NO_ROOM: a worker that hits the floor stops the pass
WINDOW_START = mf.WINDOW_START          # one window for every dataset: the last ten years as whole calendar years

QSRC = """read_csv('{f}', header = true, compression = 'gzip', columns = {{'ticker': 'VARCHAR', 'ask_exchange': 'INTEGER',
    'ask_price': 'DOUBLE', 'ask_size': 'DOUBLE', 'bid_exchange': 'INTEGER', 'bid_price': 'DOUBLE', 'bid_size': 'DOUBLE',
    'conditions': 'VARCHAR', 'indicators': 'VARCHAR', 'participant_timestamp': 'BIGINT', 'sequence_number': 'BIGINT',
    'sip_timestamp': 'BIGINT', 'tape': 'INTEGER', 'trf_timestamp': 'BIGINT'}})"""
QRAW = """
COPY (
  SELECT q.ticker, q.sip_timestamp AS ts, q.participant_timestamp AS pts, q.bid_price AS bp, CAST(q.bid_size AS INTEGER) AS bs,
         CAST(q.bid_exchange AS TINYINT) AS bx, q.ask_price AS ap, CAST(q.ask_size AS INTEGER) AS asz,
         CAST(q.ask_exchange AS TINYINT) AS ax, q.conditions AS c, q.indicators AS ind, q.sequence_number AS seq
  FROM {src} q JOIN mv2 USING (ticker)
  ORDER BY q.ticker, q.sip_timestamp, q.sequence_number
) TO '{out}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 1000000)"""


def log(msg: str) -> None:
    line = f"{datetime.now(NY).strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def free_gb() -> float:
    return shutil.disk_usage(ROOT.anchor).free / 2**30


def paths(d: date) -> tuple[Path, Path]:
    return RAW_DIR / mf.sub(d, ".csv.gz"), OUT_DIR / mf.sub(d, ".parquet")


def trading_days(s3, a: date, b: date) -> dict[date, tuple[str, int]]:
    return mf.dataset_days(s3, "quotes_v1", a, b)


def plan(s3, mode: str = "both", only: str | None = None) -> list[tuple[str, date, str, int]]:
    """Days still to do, newest year first. mode 'fetch': the days whose raw file is not on disk whole; 'both': the days
    that lack the raw file or the movers product. only: one year's name."""
    jobs = []
    for name, a, b, newest_first in mf.year_periods():
        if only and name != only:
            continue
        days = trading_days(s3, max(a, WINDOW_START), min(b, date.today()))
        for d in sorted(days, reverse=newest_first):
            raw, prod = paths(d)
            key, size = days[d]
            have_raw = raw.exists() and raw.stat().st_size == size
            if have_raw and (mode == "fetch" or prod.exists()):
                continue
            jobs.append((name, d, key, size))
    return jobs


def process(d: date, raw: Path, threads: int = 3, mem: str = "3GB") -> dict:
    import duckdb
    _, out = paths(d)
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET threads TO {threads}"); con.execute(f"SET memory_limit = '{mem}'")
    scratch = TMP / "duck" / str(os.getpid())            # one scratch folder per worker (see trades_products.process)
    scratch.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory = '{scratch.as_posix()}'")
    t0 = time.time()
    try:
        n_mv = tp.movers(con, d)
        tmp = out.with_name(out.name + ".tmp")
        con.execute(QRAW.format(src=QSRC.format(f=raw.as_posix()), out=tmp.as_posix()))
        n = con.execute(f"SELECT count(*) FROM read_parquet('{tmp.as_posix()}')").fetchone()[0]
    finally:
        con.close()
        shutil.rmtree(scratch, ignore_errors=True)
    tmp.replace(out)
    return {"movers": n_mv, "quotes": n, "mb": out.stat().st_size / 2**20, "s": time.time() - t0}


def fetch_day(s3, d: date, key: str, size: int) -> str:
    """The raw file only, exactly as Massive serves it. 'have' | 'raw' | the reason nothing was done."""
    raw, _ = paths(d)
    if raw.exists() and raw.stat().st_size == size:
        return "have"
    need = size * 1.02 / 2**30 + 1.0
    if free_gb() - need < QUOTE_FLOOR_GB:
        log(f"{d} not fetched: {free_gb():.0f} GB free on {ROOT.anchor}, floor {QUOTE_FLOOR_GB} GB (this day needs {need:.1f} GB)")
        return NO_ROOM
    try:
        secs = mf.fetch(s3, key, raw, size)
    except PermissionError:
        log(f"{d} the server refused the file (403, asked four times)"); return "forbidden"
    log(f"{d} quotes raw: {size / 2**30:.2f} GB in {secs:.0f}s ({size / 2**20 / max(secs, 0.1):.1f} MB/s)")
    return "raw" if mf.check_new_file(raw, size) else "damaged"


def do_day(s3, d: date, key: str, size: int, threads: int = 3) -> str:
    raw, prod = paths(d)
    have_raw = raw.exists() and raw.stat().st_size == size
    if prod.exists() and have_raw:
        return "have"
    if not tp.agg_file("minute_aggs_v1", d).exists() and not (tp.EVT / f"d={d.isoformat()}" / "part.parquet").exists():
        log(f"{d} waits: its minute aggregates are not on disk, so the day's movers cannot be named")
        return "no minute aggregates"
    need = ((0 if have_raw else size) * 1.02) / 2**30 + 1.0
    if free_gb() - need < QUOTE_FLOOR_GB:
        log(f"{d} not fetched: {free_gb():.0f} GB free on {ROOT.anchor}, floor {QUOTE_FLOOR_GB} GB (this day needs {need:.1f} GB)")
        return NO_ROOM
    try:
        secs = mf.fetch(s3, key, raw, size) if not have_raw else 0.0
    except PermissionError:
        log(f"{d} forbidden (outside the plan's window)"); return "forbidden"
    rate = f"{size / 2**30:.2f} GB in {secs:.0f}s ({size / 2**20 / max(secs, 0.1):.1f} MB/s)" if secs else f"{size / 2**30:.2f} GB on disk"
    if prod.exists():
        log(f"{d} raw kept: {rate}"); return "raw"
    try:
        r = process(d, raw, threads)
    except Exception as exc:  # noqa: BLE001 - the product is built again next run
        msg = str(exc)
        log(f"{d} FAILED to process: {msg[:200]}")
        if "gzip" in msg.lower():                           # only a damaged file is thrown away: a full memory or a crash is not the
            raw.unlink(missing_ok=True)                     # download's fault, and the file cost up to 20 GB to fetch
        return "failed"
    log(f"{d} ok: {rate}; movers {r['movers']} tickers, {r['quotes']:,} quotes {r['mb']:.0f} MB ({r['s']:.0f}s)")
    return "ok"


def worker(q: Queue, threads: int, noroom, mode: str = "both") -> None:
    mj.idle_priority()
    s3 = mf.client()
    while True:
        if mj.parent_gone() or not mj.wait_for_quiet(False) or (mode != "fetch" and not mj.wait_for_memory()):
            return
        job = q.get()
        if job is None or noroom.is_set():
            return
        d, key, size = job
        try:
            st = fetch_day(s3, d, key, size) if mode == "fetch" else do_day(s3, d, key, size, threads)
        except Exception as exc:  # noqa: BLE001
            log(f"{d} FAILED: {str(exc)[:200]}")
            try:
                s3 = mf.client()
            except Exception:  # noqa: BLE001
                time.sleep(60)
            continue
        if st == NO_ROOM:
            noroom.set(); return


def progress() -> tuple[int, int]:
    """(days with their movers product, raw files on disk): what a pass is judged by."""
    prods = sum(1 for _ in OUT_DIR.rglob("*.parquet")) if OUT_DIR.exists() else 0
    raws = sum(1 for _ in RAW_DIR.rglob("*.csv.gz")) if RAW_DIR.exists() else 0
    return prods, raws


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd in ("-h", "--help", "help"):
        print(__doc__); return 0
    mj.idle_priority()
    RAW_DIR.mkdir(parents=True, exist_ok=True); OUT_DIR.mkdir(parents=True, exist_ok=True); TMP.mkdir(parents=True, exist_ok=True)
    s3 = mf.client()
    if cmd == "one":
        d = date.fromisoformat(sys.argv[2])
        days = trading_days(s3, d, d)
        print(do_day(s3, d, *days[d], threads=4)); return 0
    mode = "fetch" if cmd == "fetch" else "both"
    workers = int(sys.argv[2]) if cmd != "plan" and len(sys.argv) > 2 else 4
    only = (sys.argv[2] if cmd == "plan" else sys.argv[3]) if len(sys.argv) > (2 if cmd == "plan" else 3) else None
    jobs = plan(s3, mode, only)
    by: dict[str, list] = {}
    for name, _, _, size in jobs:
        by.setdefault(name, [0, 0]); by[name][0] += 1; by[name][1] += size
    print(json.dumps({"mode": mode, "year": only, "left": {k: {"days": v[0], "tb": round(v[1] / 1e12, 3)} for k, v in by.items()},
                      "free_gb_E": round(free_gb()), "floor_gb": QUOTE_FLOOR_GB}, indent=1))
    if cmd == "plan":
        return 0
    if not mj.single_instance("NovaLabQuotesArchive"):
        print("another copy of the quotes archive is already running: nothing started"); return 0
    for npass in range(1, 4):
        if npass > 1:
            jobs = plan(s3, mode, only)
        if not jobs:
            log(f"quotes: nothing left to {mode}{f' for {only}' if only else ''}"); break
        log(f"quotes {mode} pass {npass} starts{f' ({only})' if only else ''}: {len(jobs)} days left; {workers} workers; {free_gb():.0f} GB free on {ROOT.anchor}")
        before = progress()
        q: Queue = Queue()
        for _, d, key, size in jobs:
            q.put((d, key, size))
        for _ in range(workers):
            q.put(None)
        noroom = Event()
        procs = [Process(target=worker, args=(q, 3, noroom, mode)) for _ in range(workers)]
        for p in procs:
            p.start()
        respawns = 0; next_state = 0.0
        while any(p.is_alive() for p in procs):
            time.sleep(15)
            for i, p in enumerate(procs):                # a worker that crashed (not one that ended) is replaced
                if p.exitcode not in (None, 0) and respawns < 4 * workers and not mj.STOP.exists() and not noroom.is_set():
                    log(f"a quotes worker ended with exit code {p.exitcode}; a new one takes its place ({respawns + 1} so far this pass)")
                    procs[i] = Process(target=worker, args=(q, 3, noroom, mode)); procs[i].start(); respawns += 1
            if time.time() < next_state:
                continue
            next_state = time.time() + 60
            try:
                prods, raws = progress()
                STATE.write_text(json.dumps({"at": datetime.now(NY).isoformat(timespec="seconds"), "mode": mode, "year": only, "pass": npass,
                                             "days_with_product": prods, "raw_files": raws, "free_gb_E": round(free_gb(), 1),
                                             "workers_alive": sum(p.is_alive() for p in procs), "workers_replaced": respawns}), encoding="utf-8")
            except OSError:
                pass
        try:
            while True:
                q.get_nowait()
        except Exception:  # noqa: BLE001 - queue.Empty ends the drain
            pass
        q.close(); q.cancel_join_thread()
        after = progress()
        log(f"quotes {mode} pass {npass} ends: {after[0] - before[0]} products built, {after[1] - before[1]} raw files added; {free_gb():.0f} GB free on {ROOT.anchor}")
        if mj.STOP.exists():
            log("quotes: stopped by the STOP file"); break
        if noroom.is_set():
            log(f"quotes: stopped, the drive at its floor ({QUOTE_FLOOR_GB} GB)"); break
        if after == before:
            log("quotes: no progress in this pass, stopping"); break
    log(f"quotes {mode} run ends")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
