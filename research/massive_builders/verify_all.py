"""End-to-end check that every Massive dataset is on disk from 2016-01-01 to today. Research tooling. Read-only: it downloads
nothing into the store, deletes nothing and changes no state; it only reads, and asks Massive again where that is the check.

Operator, 2026-10-09: "verify that all info end to end is downloaded from 2016 to 2026". Each check is made against something
other than our own bookkeeping wherever one exists:
 Price files (trades, quotes, 1-minute bars, day bars)
  P1  Massive's file list, read fresh from its S3 now (not plan_cache.json): every file it lists for 2016-01-01 to today is on
      disk at exactly Massive's size, and nothing else is.
  P2  The four datasets hold the same days, and those days are the NYSE trading days (calendar built here from the exchange's
      holiday rules and its two special closures in the window).
  P3  Every file was read whole through gzip when it landed (verified.jsonl); a sample is read whole through gzip again now:
      every day-bar file, and one random day per year of minute bars, trades and quotes.
  P4  Our derived tables (flow, movers) exist for every trades day.
 Other data (reference_archive.py)
  R1  Every month 2016-01 to now of every dataset is on disk, fetched the current way; the file's size and line count match
      the state; every line parses; every row sits in its month; no key is there twice.
  R2  Coverage: empty months only before Massive's first date; an empty month after it is asked of Massive again; short volume
      has every trading day from its first date to its last; short interest has two settlement dates in every whole month.
  R3  Massive asked again now: three random closed months per dataset at a different page size (for the one-page financial
      statements, a whole year in one page) must return exactly the keys on disk.
  R4  The single files the research code reads (dividends.json, splits.json, short_interest.jsonl, short_volume.jsonl) hold the
      same rows as their month files.
  R5  Today's ratios and float snapshots are on disk.
Writes <NOVA_MARKET_DATA_DIR>/verify_all.json (the download page shows it) and prints the report.

Usage: py -3 research/massive_builders/verify_all.py [--quick]     (--quick skips the gzip re-read of trades and quotes, the slow part)
"""
from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import disk_scan  # noqa: E402
import massive_access as mac  # noqa: E402
import massive_bucket as mf  # noqa: E402
import reference_archive as ra  # noqa: E402
from massive_env import ROOT  # noqa: E402

OUT = ROOT / "verify_all.json"
PRICE = ["trades_v1", "quotes_v1", "minute_aggs_v1", "day_aggs_v1"]
FIRST = date(2016, 1, 1)
# the key that names one row; a dataset without one is keyed by the whole row
KEYS = {"news": ("id",), "dividends": ("id",), "splits": ("id",), "short_interest": ("ticker", "settlement_date"),
        "short_volume": ("ticker", "date")}


# ---- the NYSE calendar ------------------------------------------------------------------------------------------------------
def easter(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31; day = (h + l_ - 7 * m + 114) % 31 + 1
    return date(y, month, day)


def nth_weekday(y: int, m: int, wd: int, n: int) -> date:
    d = date(y, m, 1); d += timedelta((wd - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def last_weekday(y: int, m: int, wd: int) -> date:
    d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(1)
    return d - timedelta((d.weekday() - wd) % 7)


def observed(d: date, saturday_to_friday: bool = True) -> date | None:
    if d.weekday() == 6:
        return d + timedelta(1)
    if d.weekday() == 5:
        return d - timedelta(1) if saturday_to_friday else None
    return d


def nyse_holidays(y: int) -> set[date]:
    h = {observed(date(y, 1, 1), saturday_to_friday=False), nth_weekday(y, 1, 0, 3), nth_weekday(y, 2, 0, 3),
         easter(y) - timedelta(2), last_weekday(y, 5, 0), observed(date(y, 7, 4)), nth_weekday(y, 9, 0, 1),
         nth_weekday(y, 11, 3, 4), observed(date(y, 12, 25))}
    if y >= 2022:
        h.add(observed(date(y, 6, 19)))
    h |= {d for d in (date(2018, 12, 5), date(2025, 1, 9)) if d.year == y}   # national days of mourning (Bush, Carter)
    h.discard(None)
    return h


def trading_days(a: date, b: date) -> list[str]:
    hol = set().union(*(nyse_holidays(y) for y in range(a.year, b.year + 1)))
    out, d = [], a
    while d <= b:
        if d.weekday() < 5 and d not in hol:
            out.append(d.isoformat())
        d += timedelta(1)
    return out


# ---- report -----------------------------------------------------------------------------------------------------------------
checks: list[dict] = []


def check(cid: str, name: str, ok: bool, detail: str, level: str | None = None) -> None:
    checks.append({"id": cid, "name": name, "ok": ok, "level": level or ("ok" if ok else "fail"), "detail": detail})
    print(f"[{'PASS' if ok else level.upper() if level else 'FAIL'}] {cid} {name}: {detail}", flush=True)


def short(xs, n: int = 6) -> str:
    xs = sorted(xs)
    return ", ".join(map(str, xs[:n])) + (f" ... ({len(xs)} in all)" if len(xs) > n else "")


# ---- price files ----------------------------------------------------------------------------------------------------------------
def list_massive(today: date) -> dict[str, dict[str, int]]:
    s3 = mf.client()
    jobs = [(ds, y, m) for ds in PRICE for y, m in mf.months(FIRST, today)]

    def one(job):
        ds, y, m = job
        for attempt in range(5):
            try:
                return ds, mf.listing(s3, ds, y, m)
            except Exception:  # noqa: BLE001 - a dropped connection: try again after a moment
                time.sleep(3 * (attempt + 1))
        raise RuntimeError(f"Massive did not answer the file list for {ds} {y}-{m:02d}")
    out: dict[str, dict[str, int]] = {ds: {} for ds in PRICE}
    with ThreadPoolExecutor(8) as pool:
        for ds, items in pool.map(one, jobs):
            for key, size in items.items():
                if key.endswith(".csv.gz"):
                    out[ds][key.rsplit("/", 1)[1][:-7]] = size
    return out


def gz_check(path: str) -> tuple[str, bool, str]:
    ok, why = mf.verify_gzip(Path(path))
    return path, ok, why


def price_checks(today: date, quick: bool) -> list[str]:
    t0 = time.time()
    listed = list_massive(today)
    print(f"  Massive's file list read fresh: {', '.join(f'{ds} {len(v)}' for ds, v in listed.items())} files ({time.time() - t0:.0f} s)", flush=True)
    disk = {ds: disk_scan.whole_raw_files(ds) for ds in PRICE}
    for ds in PRICE:
        lst = {d: s for d, s in listed[ds].items() if d >= FIRST.isoformat()}
        have = {d: s for d, s in disk[ds].items() if d >= FIRST.isoformat()}
        missing = [d for d in lst if d not in have]
        wrong = [f"{d} ({have[d]:,} on disk, {lst[d]:,} listed)" for d in lst if d in have and have[d] != lst[d]]
        extra = [d for d in have if d not in lst]
        check("P1", f"{ds}: every listed file on disk at Massive's size", not missing and not wrong and not extra,
              f"{len(lst)} listed, {len(lst) - len(missing) - len(wrong)} on disk at the listed size, {sum(lst.values()) / 1e12:.3f} TB"
              + (f"; missing {short(missing)}" if missing else "") + (f"; wrong size {short(wrong, 3)}" if wrong else "")
              + (f"; on disk but not listed {short(extra)}" if extra else ""))
    days = {ds: {d for d in listed[ds] if d >= FIRST.isoformat()} for ds in PRICE}
    same = all(days[ds] == days["trades_v1"] for ds in PRICE)
    diffs = {ds: sorted(days[ds] ^ days["trades_v1"]) for ds in PRICE if days[ds] != days["trades_v1"]}
    check("P2", "the four datasets hold the same days", same, f"{len(days['trades_v1'])} days each" if same else f"differ: {diffs}")
    last = max(days["trades_v1"])
    cal = set(trading_days(FIRST, date.fromisoformat(last)))
    not_listed = sorted(cal - days["trades_v1"]); not_trading = sorted(days["trades_v1"] - cal)
    check("P2", "those days are the NYSE trading days, 2016-01-04 to the last listed day", not not_listed and not not_trading,
          f"{len(cal)} NYSE trading days {min(cal)} to {last}" + (f"; trading days with no file: {short(not_listed)}" if not_listed else "")
          + (f"; files on non-trading days: {short(not_trading)}" if not_trading else ""))
    ver = mf.load_verified()
    unread = []
    for ds in PRICE:
        for d, size in listed[ds].items():
            if d >= FIRST.isoformat() and ver.get(f"{ds}/{d[:4]}/{d[5:7]}/{d}.csv.gz") != (size, True):
                unread.append(f"{ds} {d}")
    check("P3", "every file was read whole through gzip when it landed (verified.jsonl)", not unread,
          f"{sum(len(v) for v in listed.values()) - len(unread)} of {sum(len(v) for v in listed.values())} files recorded intact at their size"
          + (f"; not recorded: {short(unread)}" if unread else ""))
    rng = random.Random(20261009)
    sample = [f"{ROOT}/day_aggs_v1/{d[:4]}/{d[5:7]}/{d}.csv.gz" for d in sorted(days["day_aggs_v1"])]
    by_year = defaultdict(list)
    for d in sorted(days["trades_v1"]):
        by_year[d[:4]].append(d)
    for ds in (["minute_aggs_v1"] if quick else ["minute_aggs_v1", "trades_v1", "quotes_v1"]):
        for ds_days in by_year.values():
            d = rng.choice(ds_days); sample.append(f"{ROOT}/{ds}/{d[:4]}/{d[5:7]}/{d}.csv.gz")
    t0 = time.time(); nbytes = sum(Path(p).stat().st_size for p in sample)
    with ProcessPoolExecutor(4) as pool:
        res = list(pool.map(gz_check, sample, chunksize=8))
    bad = [f"{p} ({why})" for p, ok, why in res if not ok]
    picked = sorted({Path(p).parent.parent.parent.name + " " + Path(p).name[:10] for p in sample if "day_aggs" not in p})
    check("P3", "a sample read whole through gzip again now", not bad,
          f"{len(sample)} files, {nbytes / 1e9:,.1f} GB in {time.time() - t0:.0f} s: every day-bar file, and one day per year of "
          f"{'minute bars' if quick else 'minute bars, trades and quotes'} ({short(picked, 4)})" + (f"; DAMAGED: {short(bad, 3)}" if bad else ""))
    flow, mov = disk_scan.table_days()
    no_table = sorted(d for d in days["trades_v1"] if not (d in flow and d in mov))
    check("P4", "our derived tables (flow, movers) exist for every trades day", not no_table,
          f"{len(days['trades_v1']) - len(no_table)} of {len(days['trades_v1'])} days" + (f"; missing {short(no_table)}" if no_table else ""))
    return sorted(days["trades_v1"])


# ---- other data ------------------------------------------------------------------------------------------------------------------
def scan_month_file(args) -> dict:
    """One month file read whole: lines, parse errors, rows dated outside the month, duplicate keys, the dates seen."""
    ds, k, bounded, last_key = args
    field = ra.DATED[ds][1]; keyf = KEYS.get(ds)
    a = k + "-01"; b = ra.next_month(date.fromisoformat(a)).isoformat()
    n = bad = outside = 0; seen: set = set(); dup = 0; dates: Counter = Counter()
    p = ra.REF / ds / f"{k}.jsonl"
    try:
        size = p.stat().st_size
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                n += 1
                try:
                    r = json.loads(line)
                except ValueError:
                    bad += 1; continue
                d = str(r.get(field) or "")[:10]
                if d and (d < a or (bounded and d >= b)):
                    outside += 1
                if d:
                    dates[d] += 1
                key = tuple(str(r.get(f)) for f in keyf) if keyf else hash(line)
                if key in seen:
                    dup += 1
                seen.add(key)
    except OSError as exc:
        return {"ds": ds, "k": k, "error": str(exc)}
    return {"ds": ds, "k": k, "size": size, "lines": n, "bad": bad, "outside": outside, "dup": dup, "dates": dict(dates)}


def keys_of_file(ds: str, k: str) -> set:
    keyf = KEYS.get(ds); out = set()
    with open(ra.REF / ds / f"{k}.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            out.add(tuple(str(r.get(f)) for f in keyf) if keyf else json.dumps(r, sort_keys=True))
    return out


def keys_from_massive(ds: str, a: str, b: str, limit: int, one_page: bool = False) -> set | None:
    path, field, _lim, style = ra.DATED[ds]
    params = {f"{field}.gte": a, f"{field}.lt": b, "limit": limit}
    if style == "v3":
        params.update({"order": "asc", "sort": field})
    keyf = KEYS.get(ds); out = set()
    for n, batch in enumerate(ra.pages(path, params)):
        if n and one_page:
            return None
        for r in batch:
            out.add(tuple(str(r.get(f)) for f in keyf) if keyf else json.dumps(r, sort_keys=True))
    return out


def reference_checks(trade_days: list[str]) -> None:
    st = ra.load_state(); today = ra.today_ny()
    months = ra.month_list(today); keys = [f"{m:%Y-%m}" for m in months]
    jobs, absent = [], []
    for ds in ra.DATED:
        for k in keys:
            e = ra.valid(ds, st["months"].get(ds, {}).get(k))
            if e is None:
                absent.append(f"{ds} {k}")
            else:
                jobs.append((ds, k, e["bounded"], k == keys[-1]))
    t0 = time.time()
    with ProcessPoolExecutor(4) as pool:
        scanned = list(pool.map(scan_month_file, jobs, chunksize=4))
    print(f"  read every month file whole: {len(scanned)} files in {time.time() - t0:.0f} s", flush=True)
    res = {(r["ds"], r["k"]): r for r in scanned}
    for ds in ra.DATED:
        rs = [res[(ds, k)] for k in keys if (ds, k) in res]
        ent = st["months"].get(ds, {})
        errs = [f"{r['k']}: {r['error']}" for r in rs if "error" in r]
        mismatch = [r["k"] for r in rs if "error" not in r and (r["size"] != ent[r["k"]]["bytes"] or r["lines"] != ent[r["k"]]["rows"])]
        badp = sum(r.get("bad", 0) for r in rs); outside = sum(r.get("outside", 0) for r in rs); dup = sum(r.get("dup", 0) for r in rs)
        miss = [a for a in absent if a.startswith(ds + " ")]
        rows = sum(r.get("lines", 0) for r in rs)
        check("R1", f"{ra.LABEL[ds]}: every month on disk and intact",
              not (miss or errs or mismatch or badp or outside or dup),
              f"{len(rs)} of {len(keys)} months, {rows:,} rows" + (f"; not on disk: {short(miss)}" if miss else "")
              + (f"; unreadable: {short(errs, 2)}" if errs else "") + (f"; size or count differs from the state: {short(mismatch)}" if mismatch else "")
              + (f"; {badp} lines do not parse" if badp else "") + (f"; {outside} rows outside their month" if outside else "")
              + (f"; {dup} keys twice" if dup else ""))
        # coverage
        with_rows = [r["k"] for r in rs if r.get("lines")]
        if not with_rows:
            check("R2", f"{ra.LABEL[ds]}: coverage", False, "no rows at all"); continue
        first = with_rows[0]
        empty_after = [r["k"] for r in rs if r["k"] > first and not r.get("lines")]
        recheck = []
        for k in empty_after:              # ask Massive again: an empty month must be empty at the source too
            got = keys_from_massive(ds, k + "-01", ra.next_month(date.fromisoformat(k + "-01")).isoformat(), ra.DATED[ds][2])
            if got:
                recheck.append(f"{k} ({len(got)} rows at Massive)")
        all_dates = set().union(*(r.get("dates", {}).keys() for r in rs))
        detail = f"first row {min(all_dates)}, last {max(all_dates)}" + (f" (Massive has none before {first})" if first != keys[0] else "")
        ok = not recheck
        if empty_after:
            detail += f"; empty months after the first: {short(empty_after)}, " + ("Massive has none either" if not recheck else f"MASSIVE HAS ROWS: {short(recheck)}")
        if ds == "short_volume":
            lo, hi = min(all_dates), max(all_dates)
            want = [d for d in trade_days if lo <= d <= hi]
            gone = sorted(set(want) - all_dates)
            per_day = Counter()
            for r in rs:
                per_day.update(r.get("dates", {}))
            thin = sorted(d for d in want if 0 < per_day[d] < 5000)
            ok = ok and not gone
            detail += f"; {len(want) - len(gone)} of {len(want)} trading days {lo} to {hi} present" + (f", missing {short(gone)}" if gone else "") \
                + (f"; days under 5,000 tickers: {short(thin)}" if thin else f"; every day has {min(per_day[d] for d in want):,} to {max(per_day[d] for d in want):,} tickers")
        if ds == "short_interest":
            per_month = defaultdict(set)
            for d in all_dates:
                per_month[d[:7]].add(d)
            whole = [k for k in keys if first < k <= keys[-3]]      # Massive's first month starts on its first date (2017-12-29), and
            #                                                         the last two may still wait for FINRA's publication
            few = [f"{k} ({len(per_month[k])})" for k in whole if len(per_month[k]) < 2]
            ok = ok and not few
            detail += f"; {len(whole) - len(few)} of {len(whole)} whole months have two settlement dates" + (f", fewer: {short(few)}" if few else "")
        check("R2", f"{ra.LABEL[ds]}: coverage from 2016-01 to now", ok, detail)
    # R3: Massive asked again at another page size
    rng = random.Random(20261009 + 1)
    for ds in ra.DATED:
        closed = [k for k in keys[:-2] if res.get((ds, k), {}).get("lines")]
        if not closed:
            continue
        diffs = []; asked = []
        if ds in ra.ONE_PAGE:
            years = sorted({k[:4] for k in closed if k[:4] != str(today.year)})
            for y in rng.sample(years, min(2, len(years))):
                got = keys_from_massive(ds, f"{y}-01-01", f"{int(y) + 1}-01-01", 50000, one_page=True)
                mine = set().union(*(keys_of_file(ds, k) for k in keys if k.startswith(y)))
                asked.append(f"{y} whole year in one page")
                if got is None:
                    asked[-1] = f"{y} (more than one page: compared by month instead)"
                    for k in [k for k in keys if k.startswith(y)]:
                        g = keys_from_massive(ds, k + "-01", ra.next_month(date.fromisoformat(k + "-01")).isoformat(), 50000, one_page=True)
                        if g is not None and g != keys_of_file(ds, k):
                            diffs.append(f"{k}: {len(keys_of_file(ds, k) - g)} only on disk, {len(g - keys_of_file(ds, k))} only at Massive")
                elif got != mine:
                    diffs.append(f"{y}: {len(mine - got)} only on disk, {len(got - mine)} only at Massive")
        else:
            limit = 7000 if ra.DATED[ds][3] == "none" else 250
            for k in rng.sample(closed, min(3, len(closed))):
                got = keys_from_massive(ds, k + "-01", ra.next_month(date.fromisoformat(k + "-01")).isoformat(), limit)
                mine = keys_of_file(ds, k); asked.append(k)
                if got != mine:
                    diffs.append(f"{k}: {len(mine - got)} only on disk, {len(got - mine)} only at Massive")
        check("R3", f"{ra.LABEL[ds]}: Massive asked again matches the disk", not diffs,
              f"asked {', '.join(asked)}" + ("" if ds in ra.ONE_PAGE else f" at {7000 if ra.DATED[ds][3] == 'none' else 250} a page")
              + (f"; DIFFERENT: {'; '.join(diffs)}" if diffs else "; same rows"))
    # R4: the single files
    for name, (ds, as_array) in ra.SINGLE.items():
        target = ra.REF / name
        want = sum(res[(ds, k)]["lines"] for k in keys if (ds, k) in res)
        if as_array:
            got = len(json.loads(target.read_text(encoding="utf-8")))
        else:
            with open(target, "rb") as fh:
                got = sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(64 * 2**20), b""))
        newest = max((ra.REF / ds / f"{k}.jsonl").stat().st_mtime for k in keys)
        fresh = target.stat().st_mtime >= newest
        check("R4", f"{name} holds the rows of its month files", got == want and fresh,
              f"{got:,} rows, the months hold {want:,}" + ("" if fresh else "; older than its newest month file (the next run rebuilds it)"))
    snaps = st.get("snapshots", {})
    okd = [n for n in ra.SNAPSHOTS if (snaps.get(n) or {}).get("date") == today.isoformat() and snaps[n]["rows"] > 0]
    check("R5", "today's ratios and float snapshots", len(okd) == len(ra.SNAPSHOTS),
          "; ".join(f"{ra.LABEL[n]} {snaps[n]['rows']:,} tickers on {snaps[n]['date']}" for n in ra.SNAPSHOTS if n in snaps)
          + "; Massive keeps no history of these, so nothing before the first snapshot exists anywhere")


def main() -> int:
    if any(a in ("-h", "--help", "help") for a in sys.argv[1:]):
        print(__doc__); return 0
    quick = "--quick" in sys.argv
    if mac.ended():      # P1 and R3 ask Massive; once the subscription ended they can only fail, so the last run stands
        print(f"Massive access has ended ({mac.describe(mac.load())}). This check asks Massive, so it cannot run now; "
              f"the last run in {OUT} stands. A resubscribe makes it runnable again.")
        return 2
    ra.KEY = ra.api_key()
    t0 = time.time(); today = ra.today_ny()
    print(f"End-to-end check, {FIRST} to {today}{' (quick)' if quick else ''}", flush=True)
    days = price_checks(today, quick)
    reference_checks(days)
    fails = [c for c in checks if not c["ok"]]
    report = {"at": datetime.now(ra.NY).strftime("%Y-%m-%d %H:%M:%S"), "ts": time.time(), "from": FIRST.isoformat(), "to": today.isoformat(),
              "quick": quick, "pass": not fails, "passed": len(checks) - len(fails), "checks": checks, "took_s": round(time.time() - t0)}
    tmp = OUT.with_suffix(".tmp"); tmp.write_text(json.dumps(report, indent=1), encoding="utf-8"); ra.replace(tmp, OUT)
    print(f"\n{'ALL PASS' if not fails else f'{len(fails)} CHECK(S) FAILED'}: {len(checks) - len(fails)} of {len(checks)} checks, {(time.time() - t0) / 60:.1f} min -> {OUT}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
