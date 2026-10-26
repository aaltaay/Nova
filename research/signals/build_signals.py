"""Build the signal table: the Trader's Signals panel at the end of every minute of every in-play stock-day, by the
desk's own rules, written through ``research/market_reads/signals_store.py`` (owner of the files). Rules:
``signals_store.RULES``; schema: ``architecture/schema/agent-desk.md`` ("The Trader's signals on past days, and mixing
them"); reading it back is the data front door (``signal_series`` / ``signal_scan`` / ``signal_test``).

Usage (repo root):
    py -3 research/signals/build_signals.py                       # every session not built yet, newest first
    py -3 research/signals/build_signals.py --start 2024-01-01 --end 2024-12-31 --workers 12
    py -3 research/signals/build_signals.py --rebuild-from 2026-09-01   # these sessions again
    py -3 research/signals/build_signals.py --stage tape --start 2026-10-01   # the tape stage (Massive trades)
    py -3 research/signals/build_signals.py --status

Sessions are independent (a day reads only the relative-volume table and stores up to it), so ``--workers`` build
several at once, each at below-normal priority with one DuckDB and one pyarrow thread. A day is stale when
``signals_store.BUILDER`` moved or the relative-volume table rebuilt that day after it was built. ``<root>/STOP``
stops after the days in hand. About 2 s per in-play stock-day and about 230 of them a session.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for extra in (REPO / "research", REPO / "backend", HERE):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import pyarrow as pa  # noqa: E402

from market_reads import inventory, rvol  # noqa: E402
from market_reads import rvol_store as rs  # noqa: E402
from market_reads import signals_store as ss  # noqa: E402
from market_reads.signal_registry import BY_COLUMN, MINUTE_COLUMNS  # noqa: E402

DEFAULT_WORKERS = 8
_ARROW = {"state": pa.string(), "label": pa.string(), "text": pa.string(), "number": pa.float64(),
          "bool": pa.bool_()}


def minute_schema() -> pa.Schema:
    fields = [pa.field("date", pa.date32()), pa.field("symbol", pa.string()), pa.field("m", pa.int16())]
    fields += [pa.field(c, _ARROW[BY_COLUMN[c].kind]) for c in MINUTE_COLUMNS]
    return pa.schema(fields)


DAY_SCHEMA = pa.schema([pa.field("date", pa.date32()), pa.field("symbol", pa.string()),
                        pa.field("kind", pa.string()), pa.field("prev_close", pa.float64()),
                        pa.field("in_play_m", pa.int16()), pa.field("epoch", pa.int32()),
                        pa.field("basis", pa.float64())])


def _init_worker(polite: bool) -> None:
    import logging
    logging.basicConfig(level=logging.WARNING)
    if polite:
        inventory.below_normal()
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)


def build_day(day: str, built: list[str]) -> dict:
    """One session's files; returns its manifest entry (or ``{"error": ...}``, which leaves the day unbuilt)."""
    from datetime import date

    import evaluate
    import inputs
    t0 = time.monotonic()
    con = rvol.connect()
    con.execute("SET threads = 1")
    try:
        inp = inputs.load(con, day, built)
    finally:
        con.close()
    columns: dict[str, list] = {c: [] for c in ("symbol", "m", *MINUTE_COLUMNS)}
    failed = []
    for info in inp.universe.to_dict("records"):
        try:
            got = evaluate.stock_day(inp, info)
        except Exception as exc:          # one stock-day's failure is named in the manifest, never silent
            failed.append({"symbol": info["symbol"], "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        columns["symbol"] += [info["symbol"]] * len(got["m"])
        for c in ("m", *MINUTE_COLUMNS):
            columns[c] += got[c]
    n = len(columns["m"])
    schema = minute_schema()
    arrays = [pa.array([date.fromisoformat(day)] * n, pa.date32())]
    arrays += [pa.array(columns[f.name], f.type, from_pandas=True) for f in list(schema)[1:]]
    minutes = pa.Table.from_arrays(arrays, schema=schema)
    uni = inp.universe[~inp.universe["symbol"].isin({f["symbol"] for f in failed})] if failed else inp.universe
    days = pa.Table.from_pydict({
        "date": [date.fromisoformat(day)] * len(uni), "symbol": uni["symbol"].tolist(), "kind": uni["kind"].tolist(),
        "prev_close": uni["prev_close"].astype(float).tolist(), "in_play_m": uni["in_play_m"].astype(int).tolist(),
        "epoch": uni["epoch"].astype(int).tolist(), "basis": uni["basis"].astype(float).tolist()}, schema=DAY_SCHEMA)
    ss.write_day(day, minutes, days)
    return {"stock_days": len(uni), "rows": n, "failed": failed, "built_ts": time.time(),
            "seconds": round(time.monotonic() - t0, 1), "coverage": inp.coverage}


def plan(manifest: dict, rvol_manifest: dict, start: str | None, end: str | None, rebuild_from: str | None,
         stage: str) -> list[str]:
    days = rs.built_days(rvol_manifest, start, end)
    done = manifest.get("tape" if stage == "tape" else "days", {})
    out = []
    for day in days:
        entry = done.get(day)
        if rebuild_from and day >= rebuild_from:
            out.append(day)
        elif entry is None:
            out.append(day)
        elif stage == "minutes" and float(entry.get("rvol_built_ts") or 0) < float(
                rvol_manifest["days"][day].get("built_ts") or 0):
            out.append(day)
    if stage == "tape":
        out = [d for d in out if d in manifest.get("days", {})]
    return sorted(out, reverse=True)


def build(start: str | None = None, end: str | None = None, rebuild_from: str | None = None,
          max_days: int | None = None, workers: int = DEFAULT_WORKERS, stage: str = "minutes", say=print,
          polite: bool = True) -> dict:
    """Build every session the plan names, newest first; returns counts."""
    import lanes
    if polite:
        inventory.below_normal()
    rvol_manifest = rs.load_manifest(required=True)
    manifest = ss.load_manifest()
    if manifest.get("builder") != ss.BUILDER and stage == "minutes":
        manifest = ss.new_manifest()
    revs = lanes.template_revs()
    todo = plan(manifest, rvol_manifest, start, end, rebuild_from, stage)[:max_days or None]
    if not todo:
        say(f"signal table ({stage}) is up to date")
        return {"built": 0}
    built_rvol = rs.built_days(rvol_manifest)
    ss.root().mkdir(parents=True, exist_ok=True)
    say(f"building {len(todo)} session(s) ({stage}) {todo[-1]} .. {todo[0]} into {ss.root()} with {workers} worker(s)")
    import tape as tape_stage
    job = tape_stage.build_day if stage == "tape" else build_day
    key = "tape" if stage == "tape" else "days"
    count = 0

    def done(day: str, entry: dict) -> None:
        nonlocal count
        if stage == "minutes":
            entry["rvol_built_ts"] = rvol_manifest["days"][day].get("built_ts")
        def change(data: dict) -> None:   # under the manifest lock: the minutes and tape stages may run at once
            if stage == "minutes" and data.get("builder") != ss.BUILDER:
                data.update(ss.new_manifest())
            data["builder"], data["templates"] = ss.BUILDER, revs
            data.setdefault(key, {})[day] = entry

        ss.update_manifest(change)
        count += 1
        say(f"{day}  {entry.get('stock_days', 0):,} stock-days  {entry.get('rows', 0):,} rows  "
            f"{entry.get('seconds')} s" + (f"  {len(entry['failed'])} failed" if entry.get("failed") else ""))

    if workers <= 1:                      # in this process, one session after another
        for day in todo:
            if ss.stop_path().exists():
                say(f"{ss.stop_path()} is there: stopping")
                break
            done(day, job(day, built_rvol))
        return {"built": count, "root": str(ss.root())}
    queue = list(todo)
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, initargs=(polite,)) as pool:
        running = {}
        while queue or running:
            while queue and len(running) < workers and not ss.stop_path().exists():
                day = queue.pop(0)
                running[pool.submit(job, day, built_rvol)] = day
            if not running:
                say(f"{ss.stop_path()} is there: stopping")
                break
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for fut in finished:
                day = running.pop(fut)
                try:
                    entry = fut.result()
                except Exception as exc:
                    say(f"{day}: failed: {type(exc).__name__}: {exc}")
                    continue
                done(day, entry)
    return {"built": count, "root": str(ss.root())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", help="the first session to build (default: the relative-volume table's first)")
    parser.add_argument("--end", help="the last session to build (default: its newest)")
    parser.add_argument("--rebuild-from", dest="rebuild_from", help="build this session and every later one again")
    parser.add_argument("--max-days", dest="max_days", type=int, help="stop after this many sessions")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="sessions built at once")
    parser.add_argument("--stage", choices=("minutes", "tape"), default="minutes",
                        help="minutes (every signal but the tape) or tape (Massive trades, a built day only)")
    parser.add_argument("--status", action="store_true", help="what is built")
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(ss.status(), indent=1))
        return 0
    build(args.start, args.end, args.rebuild_from, args.max_days, args.workers, args.stage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
