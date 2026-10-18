"""What the reference archive holds, read from its state file and its folders: ``reference_archive.py status`` and the
download page's "Other data" rows (``page``). Read-only: nothing here fetches or writes.
"""
from __future__ import annotations

import time
from datetime import date, datetime

import reference_archive as ra

FRESH_SEC = 26 * 3600                    # the page calls a month current when it was fetched this recently
GROUPS = [  # the page's rows
    ("Financial statements", "income statement, balance sheet and cash flow of every company, by filing date",
     ("income_statements", "balance_sheets", "cash_flow_statements")),
    ("Short interest and short volume", "how much of each stock is sold short, by date", ("short_interest", "short_volume")),
    ("News", "every headline, with the tickers it names", ("news",)),
    ("Dividends, splits and IPOs", "corporate actions", ("dividends", "splits", "ipos")),
]


def dataset_summary(st: dict, ds: str, today: date, now: float) -> dict:
    months = ra.month_list(today); ent = {k: e for k, e in st.get("months", {}).get(ds, {}).items() if ra.valid(ds, e)}
    keys = [f"{m:%Y-%m}" for m in months]
    have = [k for k in keys if k in ent]
    missing = [k for k in keys if k not in ent]
    current = [k for k, m in zip(keys, months, strict=True) if k in ent and (ra.is_final(ent[k], m) or now - ent[k]["at"] < FRESH_SEC)]
    with_rows = [k for k in have if ent[k]["rows"]]
    starts = None                                      # Massive's own first month, when every month before it came back empty
    if with_rows and with_rows[0] != keys[0] and all(k in ent and ent[k]["bounded"] and not ent[k]["rows"]
                                                     for k in keys[:keys.index(with_rows[0])]):
        starts = ent[with_rows[0]]["first"] or with_rows[0]
    # where Massive's coverage turns real: from this month on, no closed month holds under 5% of the median month (news: about
    # 20 headlines a month until 2021-03, thousands after); before it the dataset exists but is thin, and the page says so
    dense = thin_rows = None
    vals = sorted(ent[k]["rows"] for k in with_rows)
    if vals:
        floor = 0.05 * vals[len(vals) // 2]; closed = [k for k in keys[:-1] if k >= with_rows[0]]
        for i, k in enumerate(closed):
            if all(ent.get(x, {}).get("rows", 0) >= floor for x in closed[i:]):
                dense = k; break
        if dense and dense > with_rows[0]:
            thin_rows = sum(ent[k]["rows"] for k in with_rows if k < dense)
        else:
            dense = None
    return {"id": ds, "label": ra.LABEL[ds], "months": len(keys), "on_disk": len(have), "current": len(current),
            "final": sum(1 for k, m in zip(keys, months, strict=True) if ra.is_final(ent.get(k), m)), "missing": missing,
            "rows": sum(ent[k]["rows"] for k in have), "bytes": sum(ent[k]["bytes"] for k in have),
            "first": ent[with_rows[0]]["first"] if with_rows else None,
            "last": max((ent[k]["last"] for k in with_rows if ent[k]["last"]), default=None),
            "massive_starts": starts, "dense_from": dense, "thin_rows": thin_rows, "errors": dict(st.get("errors", {}).get(ds, {})),
            "done": not missing and len(current) == len(keys)}


def last_log_line() -> str:
    try:
        with open(ra.LOG, "rb") as fh:
            fh.seek(0, 2); fh.seek(max(0, fh.tell() - 4096))
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
        return lines[-1][11:] if lines else ""
    except OSError:
        return ""


def page(running: bool, now: float | None = None) -> dict:
    """The page's "Other data": one row per group with its months on disk against the months 2016-01 to now (its bar), what is
    on disk, what is not and why; and the progress over all of it (months, rows, pace, the latest log line)."""
    now = now or time.time(); today = ra.today_ny()
    try:
        st = ra.load_state()
    except SystemExit as exc:
        return {"rows": [{"label": "Reference data", "what": "", "state": "stuck", "have": "", "missing": str(exc), "note": "",
                          "path": str(ra.STATE), "months": 0, "on_disk": 0, "current": 0}], "progress": None}
    rows: list[dict] = []
    every: list[dict] = []
    for label, what, ids in GROUPS:
        sums = [dataset_summary(st, ds, today, now) for ds in ids]
        every += sums
        have = "; ".join(f"{s['label']}: {s['rows']:,} rows, {s['first']} to {s['last']}" for s in sums if s["rows"])
        miss = []
        for s in sums:
            if s["missing"]:
                miss.append(f"{s['label']}: {len(s['missing'])} of {s['months']} months not on disk yet ({s['missing'][0]} to {s['missing'][-1]})")
            elif not s["done"]:
                miss.append(f"{s['label']}: {s['months'] - s['current']} months waiting for their refresh")
            if s["errors"]:
                miss.append(f"{s['label']}: {len(s['errors'])} months did not download ({', '.join(sorted(s['errors'])[:3])}); the next run asks again")
        note = "; ".join([f"Massive has no {s['label']} before {s['massive_starts']}" for s in sums if s["massive_starts"]]
                         + [f"Massive's {s['label']} is thin before {s['dense_from']}: {s['thin_rows']:,} rows in all before it"
                            for s in sums if s["dense_from"]])
        done = all(s["done"] for s in sums)
        state = "done" if done else "run" if running else "part" if any(s["rows"] for s in sums) else "none"
        if done:
            note = (note + "; " if note else "") + f"from {ra.START:%Y-%m} on, checked again every {ra.REFRESH_SEC // 3600} h"
        rows.append({"label": label, "what": what, "state": state, "have": have, "missing": "; ".join(miss), "note": note,
                     "path": str(ra.REF), "months": sum(s["months"] for s in sums), "on_disk": sum(s["on_disk"] for s in sums),
                     "current": sum(s["current"] for s in sums), "rows": sum(s["rows"] for s in sums), "bytes": sum(s["bytes"] for s in sums),
                     "datasets": [{**s, "missing": len(s["missing"])} for s in sums]})
    snaps = st.get("snapshots", {})
    days = {n: sorted(p.stem for p in (ra.REF / "snapshots" / n).glob("*.jsonl")) for n in ra.SNAPSHOTS}
    fresh = [n for n in ra.SNAPSHOTS if n in snaps and now - snaps[n]["at"] < FRESH_SEC]
    first = min((d[0] for d in days.values() if d), default=None)
    have = "; ".join(f"{ra.LABEL[n]}: {snaps[n]['rows']:,} tickers as of {snaps[n]['date']}" for n in ra.SNAPSHOTS if n in snaps)
    if have:
        have += f"; one snapshot kept every day since {first} ({max(len(d) for d in days.values())} so far)"
    all_fresh = len(fresh) == len(ra.SNAPSHOTS)
    rows.append({"label": "Ratios and float", "what": "today's values only: Massive keeps no history of them",
                 "state": "done" if all_fresh else "run" if running else "part" if have else "none", "have": have,
                 "missing": "" if all_fresh else "today's snapshot is not on disk yet",
                 "note": f"No history before {first}: Massive serves today's values only" if first else "", "path": str(ra.REF / "snapshots"),
                 "months": len(ra.SNAPSHOTS), "on_disk": sum(1 for n in ra.SNAPSHOTS if n in snaps), "current": len(fresh), "unit": "snapshots today",
                 "rows": sum(snaps[n]["rows"] for n in ra.SNAPSHOTS if n in snaps), "bytes": sum(snaps[n]["bytes"] for n in ra.SNAPSHOTS if n in snaps),
                 "datasets": []})
    # ---- progress over every dated month: the overall bar, its pace and what is arriving now
    total = sum(s["months"] for s in every); cur = sum(s["current"] for s in every); disk = sum(s["on_disk"] for s in every)
    recent = sum(1 for ds in ra.DATED for e in st.get("months", {}).get(ds, {}).values() if ra.valid(ds, e) and now - e["at"] < 300)
    per_min = recent / 5 if running else 0.0
    left = total - cur
    lr = st.get("last_run") or {}
    progress = {"months": total, "current": cur, "on_disk": disk, "left": left, "running": running,
                "pct": round(100 * cur / total, 1) if total else 0.0, "rows": sum(s["rows"] for s in every),
                "bytes": sum(s["bytes"] for s in every), "per_min": round(per_min, 1),
                "eta_min": round(left / per_min) if per_min and left else None, "now": last_log_line() if running else "",
                "last_run_at": datetime.fromtimestamp(lr["at"], ra.NY).strftime("%Y-%m-%d %H:%M") if lr.get("at") else None,
                "errors": sum(len(s["errors"]) for s in every)}
    return {"rows": rows, "progress": progress}


def status() -> int:
    st = ra.load_state(); today = ra.today_ny(); now = time.time()
    for ds in ra.DATED:
        s = dataset_summary(st, ds, today, now)
        print(f"{ds:22s} {s['on_disk']:4d}/{s['months']} months on disk, {s['final']:4d} final, {s['current']:4d} current, "
              f"{s['rows']:>12,} rows {s['bytes'] / 1e9:7.2f} GB  {s['first']} to {s['last']}"
              f"{'  Massive starts ' + s['massive_starts'] if s['massive_starts'] else ''}{'  ERRORS ' + str(len(s['errors'])) if s['errors'] else ''}")
    for n, v in st.get("snapshots", {}).items():
        print(f"{n:22s} snapshot {v['date']}: {v['rows']:,} tickers")
    lr = st.get("last_run")
    if lr:
        print(f"last run {datetime.fromtimestamp(lr['at'], ra.NY):%Y-%m-%d %H:%M} ET: {lr['months']} months, {lr['rows']:,} rows, "
              f"{lr['errors']} did not download{' (paused)' if lr['stopped'] else ''}")
    return 0
