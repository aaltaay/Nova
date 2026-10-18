"""Every Massive dataset that is not a flat file, month by month from 2016, and kept current. Research tooling.

2026-10-09, operator: "make sure we are all downloaded all the way everything down to 2016". The download page's "Other
data" rows said Partly: one hand-run pull (research/orb/massive_reference_dump.py, last run 2026-10-06) started at 2021-09,
never asked for the financial statements or the IPOs, and nothing topped it up afterwards.

Under <NOVA_MARKET_DATA_DIR>/store/reference (the folder the research code already reads):
  <dataset>/<YYYY-MM>.jsonl  one file per month, each row filed by its own date (DATED below): news, dividends, splits, IPOs,
                             short interest, short volume, and the income statements, balance sheets and cash-flow statements
                             (by filing date). news/ keeps the month files the research code already reads.
  dividends.json, splits.json, short_interest.jsonl, short_volume.jsonl
                             the single files the research code reads (research/leaderboard/lb_io.py reads splits.json),
                             rebuilt from the month files once every month of the dataset is on disk and a month is newer
                             than the single file
  snapshots/<name>/<YYYY-MM-DD>.jsonl and <name>.jsonl (the latest)
                             ratios and free float: Massive serves today's values only, so one is kept per day from 2026-10-09
  reference_state.json       every month's rows, bytes and fetch time (schema_version 1); reference.log
A month is final once it was fetched with both date bounds at least SETTLE_DAYS after it ended; until then a run fetches it
again when its last fetch is REFRESH_SEC old, so late rows and corrections land. The month holding today has no upper bound, so
announced dividends, splits and IPOs are kept. Massive's own first dates are measured, not assumed: every month from 2016-01 is
asked for and an empty one is recorded as empty (on 2026-10-09: news starts 2016-06, short interest 2017-12, short volume 2024-02).

Usage (repo root):
  py -3 research/massive_builders/reference_archive.py run [workers] [--only name,name]   one pass over everything due, then exit
  py -3 research/massive_builders/reference_archive.py status                             months on disk, final and due, per dataset
The research lab's download supervisor starts `run` every half hour; a run with nothing due exits at once and writes nothing.
The STOP file ends a run at its next page. Key: MASSIVE_API_KEY (else POLYGON_API_KEY, else the S3 secret, which Massive
issues as the same value), from the environment or the .env; never printed.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import massive_jobs as mj  # noqa: E402
from massive_env import NY, ROOT, env_values  # noqa: E402
from massive_bucket import WINDOW_START  # noqa: E402

REF = ROOT / "store" / "reference"
STATE = REF / "reference_state.json"
LOG = REF / "reference.log"
SCHEMA = 1
START = WINDOW_START                     # 2016-01-01: the same ten years as the flat files
SETTLE_DAYS = 14                         # late short interest, late filings and corrections land within this after a month ends
REFRESH_SEC = 12 * 3600                  # a month that is not final is fetched again once its last fetch is this old
BASE = "https://api.massive.com"
MUTEX = "NovaLabReference"
TRIES = 8

# name: (path, the row's own date field, page size Massive accepts, sort style). "v3": order=asc&sort=<field>; "none": no sort.
# The /stocks/v1 endpoints are never sorted: sorted by date, their cursor skips the rest of a day that straddles a page (2026-10-09:
# short volume 2025-03 came back 263,559 rows of 281,732, short on exactly the days a 50,000-row page ended); unsorted, every row
# arrives at any page size. The financial statements refuse sort=filing_date (400) and lose rows across pages even unsorted
# (2025-03: 5,119 at 1,000 a page against 5,123 in one page), so their month must fit one page (ONE_PAGE).
DATED = {
    "news": ("/v2/reference/news", "published_utc", 1000, "v3"),
    "dividends": ("/v3/reference/dividends", "ex_dividend_date", 1000, "v3"),
    "splits": ("/v3/reference/splits", "execution_date", 1000, "v3"),
    "ipos": ("/vX/reference/ipos", "listing_date", 1000, "v3"),
    "short_interest": ("/stocks/v1/short-interest", "settlement_date", 50000, "none"),
    "short_volume": ("/stocks/v1/short-volume", "date", 50000, "none"),
    "income_statements": ("/stocks/financials/v1/income-statements", "filing_date", 50000, "none"),
    "balance_sheets": ("/stocks/financials/v1/balance-sheets", "filing_date", 50000, "none"),
    "cash_flow_statements": ("/stocks/financials/v1/cash-flow-statements", "filing_date", 50000, "none"),
}
ONE_PAGE = {"income_statements", "balance_sheets", "cash_flow_statements"}
VERSION = {"short_interest": 2, "short_volume": 2}   # how a month was fetched; a month fetched the older way is fetched again
SNAPSHOTS = {"ratios": ("/stocks/financials/v1/ratios", 1000), "float": ("/stocks/vX/float", 5000)}
SINGLE = {"dividends.json": ("dividends", True), "splits.json": ("splits", True),       # file -> (dataset, a JSON array?)
          "short_interest.jsonl": ("short_interest", False), "short_volume.jsonl": ("short_volume", False)}
LABEL = {"news": "news", "dividends": "dividends", "splits": "splits", "ipos": "IPOs", "short_interest": "short interest",
         "short_volume": "short volume", "income_statements": "income statements", "balance_sheets": "balance sheets",
         "cash_flow_statements": "cash-flow statements", "ratios": "ratios", "float": "free float"}


class Refused(Exception):
    """Massive answered that it does not serve this query (a 4xx other than 429)."""


class Stopped(Exception):
    """The STOP file asks every job to end."""


def log(msg: str) -> None:
    line = f"{datetime.now(NY).strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def api_key() -> str:
    vals = env_values()
    key = vals.get("MASSIVE_API_KEY") or vals.get("POLYGON_API_KEY") or vals.get("MASSIVE_S3_SECRET_ACCESS_KEY")
    if not key:
        sys.exit("no Massive key in the environment or the .env (NOVA_ENV_PATH)")
    return key


# ---- months -------------------------------------------------------------------------------------------------------------------
def next_month(m: date) -> date:
    return date(m.year + (m.month == 12), m.month % 12 + 1, 1)


def month_list(today: date) -> list[date]:
    out, m = [], date(START.year, START.month, 1)
    while m <= today:
        out.append(m); m = next_month(m)
    return out


def today_ny() -> date:
    return datetime.now(NY).date()


def valid(ds: str, e: dict | None) -> dict | None:
    """The month's entry, or None when it was fetched the older way (VERSION): such a month counts as not on disk."""
    return e if e is not None and e.get("v", 1) == VERSION.get(ds, 1) else None


def is_final(e: dict | None, m: date) -> bool:
    return bool(e) and e["bounded"] and date.fromisoformat(e["fetched_at"][:10]) >= next_month(m) + timedelta(days=SETTLE_DAYS)


def due(e: dict | None, m: date, today: date, now: float) -> bool:
    if e is None or is_final(e, m):
        return e is None
    if e["bounded"] != (next_month(m) <= today):        # the month closed since its last fetch: fetch it again with both bounds
        return True
    return now - e["at"] >= REFRESH_SEC


# ---- state ----------------------------------------------------------------------------------------------------------------------
def load_state() -> dict:
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema_version": SCHEMA, "months": {}, "errors": {}, "snapshots": {}, "last_run": None}
    if st.get("schema_version") != SCHEMA:
        raise SystemExit(f"{STATE} has schema_version {st.get('schema_version')!r}; this code reads {SCHEMA}. Nothing was fetched.")
    return st


def replace(tmp: Path, dest: Path, tries: int = 20) -> bool:
    """os.replace that waits out a reader holding the file for a moment (Windows refuses a replace while it is open)."""
    for i in range(tries):
        try:
            os.replace(tmp, dest); return True
        except PermissionError:
            time.sleep(0.25 * (i + 1))
    return False


def save_state(st: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
    if not replace(tmp, STATE):
        log("the state file was in use; it is written again on the next change")


# ---- fetching -------------------------------------------------------------------------------------------------------------------
_tl = threading.local()
KEY = ""


def session() -> requests.Session:
    s = getattr(_tl, "s", None)
    if s is None:
        s = _tl.s = requests.Session()
    return s


def get(url: str, params: dict) -> dict:
    """One page. Retries a dropped or corrupted connection on a fresh one (this PC's link corrupts a TLS record now and then)."""
    err = ""
    for attempt in range(1, TRIES + 1):
        if mj.STOP.exists():
            raise Stopped()
        wait = min(60, 3 * attempt)
        try:
            r = session().get(url, params=params, timeout=120)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = 15 * attempt
            elif 400 <= r.status_code < 500:
                raise Refused(f"HTTP {r.status_code}: {r.text[:160]}")
            err = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as exc:
            err = f"{type(exc).__name__}: {str(exc)[:100]}"
            _tl.s = None
        time.sleep(wait)
    raise RuntimeError(f"no answer after {TRIES} tries ({err})")


def pages(path: str, params: dict):
    url, p = BASE + path, dict(params, apiKey=KEY)
    while url:
        body = get(url, p)
        yield body.get("results") or []
        url, p = body.get("next_url"), {"apiKey": KEY}


def fetch_month(ds: str, m: date, bounded: bool) -> dict:
    """Every row of one month into <dataset>/<YYYY-MM>.jsonl (written whole, then put in place). A row dated outside the month
    is counted and left out: Massive's filter should never send one, and a month file holds its own month only."""
    path, field, limit, style = DATED[ds]
    a, b = m.isoformat(), next_month(m).isoformat()
    params = {f"{field}.gte": a, "limit": limit}
    if bounded:
        params[f"{field}.lt"] = b
    if style == "v3":
        params.update({"order": "asc", "sort": field})
    out = REF / ds / f"{m:%Y-%m}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".jsonl.tmp")
    rows = outside = 0; first = last = None
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for n, batch in enumerate(pages(path, params)):
            if n and ds in ONE_PAGE:
                raise RuntimeError(f"more than {limit:,} rows in one month: this endpoint loses rows across pages, so the month needs splitting")
            for r in batch:
                d = str(r.get(field) or "")[:10]
                if d and (d < a or (bounded and d >= b)):
                    outside += 1; continue
                fh.write(json.dumps(r) + "\n"); rows += 1
                if d:
                    first = d if first is None or d < first else first; last = d if last is None or d > last else last
    if not replace(tmp, out):
        raise RuntimeError(f"{out.name} is held open by another program")
    return {"rows": rows, "bytes": out.stat().st_size, "at": time.time(), "fetched_at": datetime.now(NY).isoformat(timespec="seconds"),
            "bounded": bounded, "first": first, "last": last, "outside": outside, "v": VERSION.get(ds, 1)}


def fetch_snapshot(name: str) -> dict:
    """Today's values of every ticker into snapshots/<name>/<date>.jsonl, and the same file as <name>.jsonl (the latest)."""
    path, limit = SNAPSHOTS[name]
    day = today_ny().isoformat()
    out = REF / "snapshots" / name / f"{day}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".jsonl.tmp"); rows = 0; dates: set[str] = set()
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for batch in pages(path, {"limit": limit}):
            for r in batch:
                fh.write(json.dumps(r) + "\n"); rows += 1
                d = r.get("date") or r.get("effective_date")
                if d:
                    dates.add(str(d)[:10])
    if not replace(tmp, out):
        raise RuntimeError(f"{out.name} is held open by another program")
    latest = REF / f"{name}.jsonl"; ltmp = latest.with_suffix(".jsonl.tmp")
    shutil.copyfile(out, ltmp)
    if not replace(ltmp, latest):
        log(f"{latest.name} was in use: the latest {name} is in {out}")
    return {"date": day, "rows": rows, "bytes": out.stat().st_size, "at": time.time(),
            "values_from": min(dates) if dates else None, "values_to": max(dates) if dates else None}


# ---- the single files the research code reads ---------------------------------------------------------------------------------
def rebuild_singles(st: dict, today: date) -> None:
    """dividends.json, splits.json, short_interest.jsonl, short_volume.jsonl from the month files. Only once every month of the
    dataset is on disk (a half-fetched set would drop rows the old single file holds), and only when a month file is newer."""
    keys = [f"{m:%Y-%m}" for m in month_list(today)]
    for name, (ds, as_array) in SINGLE.items():
        months = {k: e for k, e in st["months"].get(ds, {}).items() if valid(ds, e)}
        if any(k not in months for k in keys):
            continue
        files = [REF / ds / f"{k}.jsonl" for k in keys]
        target = REF / name
        if target.exists() and target.stat().st_mtime >= max(f.stat().st_mtime for f in files):
            continue
        tmp = target.with_suffix(target.suffix + ".tmp"); n = 0; t0 = time.time()
        with open(tmp, "w", encoding="utf-8", newline="\n") as out:
            out.write("[" if as_array else "")
            for k, f in zip(keys, files, strict=True):
                cut = None if months[k]["bounded"] or k == keys[-1] else next_month(date.fromisoformat(k + "-01")).isoformat()
                field = DATED[ds][1]
                with open(f, encoding="utf-8") as fh:
                    if not as_array and cut is None:
                        shutil.copyfileobj(fh, out); n += months[k]["rows"]; continue
                    for line in fh:
                        line = line.rstrip("\n")
                        if not line or (cut and str(json.loads(line).get(field) or "")[:10] >= cut):
                            continue           # an open month that closed: its next month's rows live in the next month's file
                        out.write(("," if as_array and n else "") + line + ("" if as_array else "\n")); n += 1
            out.write("]" if as_array else "")
        if replace(tmp, target):
            log(f"{name} rebuilt from {len(keys)} month files: {n:,} rows, {target.stat().st_size / 1e6:,.0f} MB in {time.time() - t0:.0f} s")
        else:
            tmp.unlink(missing_ok=True)
            log(f"{name} is held open by another program; the next run rebuilds it")


# ---- one run ----------------------------------------------------------------------------------------------------------------------
def run(workers: int, only: set[str] | None) -> int:
    global KEY
    if not mj.single_instance(MUTEX):
        print("a reference run is already going"); return 0
    mj.idle_priority()
    REF.mkdir(parents=True, exist_ok=True)
    st = load_state(); today = today_ny(); now = time.time()
    order = {ds: i for i, ds in enumerate(DATED)}
    jobs = [(m, ds, next_month(m) <= today) for ds in DATED if not only or ds in only
            for m in month_list(today) if due(valid(ds, st["months"].get(ds, {}).get(f"{m:%Y-%m}")), m, today, now)]
    jobs.sort(key=lambda j: (j[0], -order[j[1]]), reverse=True)            # newest month first, as the flat files went
    snaps = [n for n in SNAPSHOTS if (not only or n in only) and (st["snapshots"].get(n) or {}).get("date") != today.isoformat()]
    if not jobs and not snaps:
        rebuild_singles(st, today)
        return 0
    KEY = api_key()
    per = {}
    for _m, ds, _b in jobs:
        per[ds] = per.get(ds, 0) + 1
    log(f"reference pull starts: {len(jobs)} months due ({', '.join(f'{LABEL[d]} {n}' for d, n in per.items()) or 'none'}), "
        f"snapshots {', '.join(snaps) or 'none'}; {workers} at a time")
    t0 = time.time(); got = rows = bad = 0; stopped = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_month, ds, m, b): (ds, f"{m:%Y-%m}") for m, ds, b in jobs}
        futs.update({pool.submit(fetch_snapshot, n): ("snapshot", n) for n in snaps})
        for fut in as_completed(futs):
            ds, k = futs[fut]
            try:
                res = fut.result()
            except Stopped:
                stopped = True; continue
            except Exception as exc:  # noqa: BLE001 - one month does not hold up the rest; the page and the next run see it
                msg = f"{type(exc).__name__}: {str(exc)[:200]}"
                st["errors"].setdefault(ds, {})[k] = msg; bad += 1
                log(f"{LABEL.get(ds, ds)} {k} did not download: {msg}")
            else:
                st["errors"].get(ds, {}).pop(k, None)
                if ds == "snapshot":
                    st["snapshots"][k] = res
                    log(f"{LABEL[k]} snapshot {res['date']}: {res['rows']:,} tickers (values dated {res['values_from']} to {res['values_to']})")
                else:
                    st["months"].setdefault(ds, {})[k] = res; got += 1; rows += res["rows"]
                    extra = f", {res['outside']:,} rows dated outside the month left out" if res["outside"] else ""
                    log(f"{LABEL[ds]} {k}: {res['rows']:,} rows, {res['bytes'] / 1e6:,.1f} MB{'' if res['bounded'] else ' (month in progress)'}{extra}")
            save_state(st)
    if not stopped:
        rebuild_singles(st, today)
    st["last_run"] = {"at": time.time(), "months": got, "rows": rows, "errors": bad, "stopped": stopped, "took_s": round(time.time() - t0)}
    save_state(st)
    log(f"reference pull {'paused' if stopped else 'ends'}: {got} months, {rows:,} rows, {bad} did not download, {(time.time() - t0) / 60:.1f} min")
    return 1 if bad else 0


def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else "status"
    if cmd in ("-h", "--help", "help"):
        print(__doc__); return 0
    if cmd == "run":
        only = None
        if "--only" in args:
            i = args.index("--only"); only = set(args[i + 1].split(",")); args = args[:i] + args[i + 2:]
            unknown = only - set(DATED) - set(SNAPSHOTS)
            if unknown:
                sys.exit(f"unknown dataset(s): {', '.join(sorted(unknown))}")
        return run(int(args[1]) if len(args) > 1 else 6, only)
    if cmd == "status":
        from reference_status import status
        return status()
    sys.exit(__doc__)


if __name__ == "__main__":
    raise SystemExit(main())
