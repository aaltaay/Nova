"""Build the relative-volume table (#1100) from the Massive minute and day files, one session at a time, oldest first.

Every minute bar of every common stock (``CS``, ``ADRC``, untyped) with its baselines, and one row per stock-day,
written through ``research/market_reads/rvol_store.py`` (owner of the files). The rules are ``rvol_store.RULES``; the
schema is ``architecture/schema/agent-desk.md`` ("Relative volume across every stock, and what came next"). Reading
the table back is the data front door: ``rvol_scan`` / ``rvol_triggers`` / ``rvol_outcomes`` (``docs/market-data.md``).

Usage (repo root):
    py -3 research/rvol/build_rvol.py                         # every session not built yet, then stop
    py -3 research/rvol/build_rvol.py --end 2021-12-31        # up to a day
    py -3 research/rvol/build_rvol.py --rebuild-from 2024-03-01   # that day and every later one again
    py -3 research/rvol/build_rvol.py --start 2026-08-03 --max-days 20   # a new table's first day; a short slice
    py -3 research/rvol/build_rvol.py --status

Sessions are built in order because a baseline reads the sessions before it: a missing or stale day (its minute
file, day file or movers session changed, the split list changed, or ``rvol_store.BUILDER`` moved) is built again with
every later day. A build that starts after the table's first day replays the last ``BASE_MAX_AGE_DAYS`` of built
sessions from the table itself first, so it writes what a build from the start would. ``<root>/STOP`` stops after
the day in hand. Below-normal priority, two pyarrow threads, about 0.7 GB of memory and 2 s a session.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for extra in (REPO / "research", REPO / "backend", REPO / "research" / "leaderboard", HERE):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.csv as pacsv  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import rvol_state  # noqa: E402

from market_reads import inventory, tickers  # noqa: E402
from market_reads import rvol_store as rs  # noqa: E402

ET = ZoneInfo("America/New_York")
MINUTES, DAYS = "minute_aggs_v1", "day_aggs_v1"
MINUTE_COLUMNS = {"ticker": pa.string(), "volume": pa.float64(), "close": pa.float64(), "high": pa.float64(),
                  "low": pa.float64(), "window_start": pa.int64()}
DAY_COLUMNS = {"ticker": pa.string(), "volume": pa.float64(), "open": pa.float64(), "close": pa.float64(),
               "high": pa.float64(), "low": pa.float64()}


def _csv(path: Path, columns: dict) -> pa.Table:
    return pacsv.read_csv(path, convert_options=pacsv.ConvertOptions(
        include_columns=list(columns), column_types=columns, strings_can_be_null=False))


def read_minutes(path: Path, day: str) -> rvol_state.Bars:
    """The day's minute bars 04:00-20:00 ET (m = the bar's start in minutes after ET midnight)."""
    table = _csv(path, MINUTE_COLUMNS)
    midnight = int(datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), tzinfo=ET).timestamp())
    m = (table.column("window_start").to_numpy() // 10**9 - midnight) // 60
    keep = (m >= rs.SESSION_START_M) & (m < rs.SESSION_END_M)
    table = table.filter(pa.array(keep))
    return rvol_state.Bars.from_arrow(table.column("ticker"), m[keep],
                                      **{c: table.column(c).to_numpy() for c in ("high", "low", "close", "volume")})


def read_day_rows(path: Path | None) -> dict[str, tuple]:
    if path is None:
        return {}
    table = _csv(path, DAY_COLUMNS)
    cols = [table.column(c).to_pylist() for c in ("ticker", "open", "high", "low", "close", "volume")]
    return {t: (o, h, lo, c, v) for t, o, h, lo, c, v in zip(*cols, strict=True) if t}


class Reference:
    """Each symbol's kind and holder on a day (Massive's ticker list; ``tickers.py`` for a reused ticker), the listed
    splits, and the movers store's split labels."""

    def __init__(self):
        self.listings = tickers.listings()
        self.reused = {s for s, rows in self.listings.items()
                       if len({tickers._cik(r.get("cik")) for r in rows if r.get("cik")}) > 1}
        self._plain: dict[str, str] = {}
        self._candidates: dict[str, list] = {}
        from market_reads import splits
        frame, _note = splits._all()
        self.splits: dict[str, list] = {}
        rows = []
        import lb_io
        for t, d, f, to in frame[["ticker", "execution_date", "split_from", "split_to"]].itertuples(index=False):
            when = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
            self.splits.setdefault(str(t), []).append(lb_io.Split(str(t), when, float(f), float(to)))
            rows.append(f"{t}|{when}|{f}|{to}")
        self.split_rows = sorted(rows)
        self.fingerprint = hashlib.sha256("\n".join(self.split_rows).encode()).hexdigest()
        self._lb_io = lb_io

    def kind(self, symbol: str, day: str) -> tuple[str | None, str | None]:
        """``(kind, holder_cik)``: kind is ``CS`` / ``ADRC`` / ``unknown`` for the table, another Massive type (left
        out), and the holder only for a ticker two companies used."""
        rows = self.listings.get(symbol)
        if not rows:
            return "unknown", None
        if symbol not in self.reused:
            if symbol not in self._plain:
                active = [r for r in rows if r.get("active")]
                self._plain[symbol] = (active or rows)[-1].get("type") or "unknown"
            kind = self._plain[symbol]
            return ("unknown" if kind == "unknown" else kind), None
        if symbol not in self._candidates:
            self._candidates[symbol] = tickers._candidates(symbol)
        alive = [c for c in self._candidates[symbol] if tickers.holds(c, day)]
        if len(alive) != 1:
            cik = tickers.resolve(symbol, day)["cik"]
            alive = [c for c in self._candidates[symbol] if c["cik"] == cik]
        if len(alive) != 1:
            return "unknown", None
        return alive[0]["type"] or "unknown", alive[0]["cik"]

    def split_factor(self, symbol: str, after: str, through: str, prices: bool) -> float:
        listed = self.splits.get(symbol)
        if not listed:
            return 1.0
        return self._lb_io.split_factor(listed, date.fromisoformat(after), date.fromisoformat(through), prices=prices)


def movers_sessions() -> dict[str, float]:
    """``{session_date: built_ts}`` of the day movers store (a rebuilt movers session can change a split label)."""
    from day_movers import store
    db = store.read_only()
    if db is None:
        return {}
    try:
        return {d: float(ts) for d, ts in db.execute("SELECT session_date, built_ts FROM sessions")}
    finally:
        db.close()


def movers_labels(day: str) -> dict[str, str]:
    """The movers store's split label for the day's suspects (``day_movers.query.split_label``: its own rule)."""
    from day_movers import query, store
    db = store.read_only()
    if db is None:
        return {}
    try:
        rows = db.execute("SELECT symbol, split_listed, split_suspect, prev_volume, volume FROM movers"
                          " WHERE session_date = ? AND (split_suspect = 1 OR split_listed = 1)", (day,))
        out = {}
        for symbol, listed, suspect, prev_volume, volume in rows:
            label = query.split_label({"split_listed": listed, "split_suspect": suspect,
                                       "prev_volume": prev_volume, "volume": volume})
            if label:
                out[symbol] = label
        return out
    finally:
        db.close()


def sessions_on_disk(end: str | None) -> list[tuple[str, Path, Path | None]]:
    """``(day, minute file, day file)`` for every session with a minute file, oldest first."""
    days = {p.name[:10]: p for p in inventory.day_files(DAYS, None, end)}
    return [(p.name[:10], p, days.get(p.name[:10])) for p in inventory.day_files(MINUTES, None, end)]


def _fresh(entry: dict | None, minute: Path, day_file: Path | None, movers_ts: float | None) -> bool:
    return bool(entry) and entry.get("minute_file") == rs.source_identity(minute) and \
        entry.get("day_file") == rs.source_identity(day_file) and entry.get("movers_built_ts") == movers_ts


def _splits_changed_from(manifest: dict, ref: Reference) -> str | None:
    """The earliest execution date among splits added or removed since the last build (None when none)."""
    known = manifest.get("splits_fingerprint")
    if known is None or known == ref.fingerprint:
        return None
    path = rs.root() / "splits.json"
    if not path.is_file():
        return "0000-00-00"                  # which splits changed is not known: every day again
    changed = set(json.loads(path.read_text(encoding="utf-8"))).symmetric_difference(ref.split_rows)
    return min((row.split("|")[1] for row in changed), default=None)


def plan(manifest: dict, ref: Reference, start: str | None, end: str | None, rebuild_from: str | None,
         movers: dict[str, float]) -> tuple[list[tuple[str, Path, Path | None]], str | None]:
    """The sessions to build now (from the first missing or stale one through ``end``) and the first table day."""
    built = manifest.get("days", {})
    first_day = manifest.get("first_day") or start
    if manifest.get("builder") != rs.BUILDER:
        built, first_day = {}, start
    sessions = [s for s in sessions_on_disk(end) if first_day is None or s[0] >= first_day]
    if start and first_day and start != first_day:
        raise SystemExit(f"the table starts {first_day}; --start {start} would leave a hole in the baselines "
                         "(rebuild into an empty NOVA_RVOL_DIR to start elsewhere)")
    split_day = _splits_changed_from(manifest, ref) if built else None
    for i, (day, minute, day_file) in enumerate(sessions):
        stale = (day not in built or not _fresh(built.get(day), minute, day_file, movers.get(day))
                 or (rebuild_from and day >= rebuild_from) or (split_day and day >= split_day))
        if stale:
            return sessions[i:], sessions[0][0] if sessions else first_day
    return [], sessions[0][0] if sessions else first_day


def seed_state(state: rvol_state.State, ref: Reference, manifest: dict, first: str) -> int:
    """Replay the built sessions in the ``BASE_MAX_AGE_DAYS`` before ``first`` into ``state``; how many."""
    since = (date.fromisoformat(first) - timedelta(days=rs.BASE_MAX_AGE_DAYS + 1)).isoformat()
    days = [d for d in rs.built_days(manifest, since) if d < first]
    for day in days:
        frame = pq.read_table(rs.days_path(day), columns=["symbol", "epoch", "basis", "day_close",
                                                          "volume"]).to_pandas()
        minutes = pq.read_table(rs.minutes_path(day), columns=["symbol", "m", "cum"])
        cum = minutes.column("cum").to_numpy()
        zeros = np.zeros(len(cum))
        bars = rvol_state.Bars.from_arrow(minutes.column("symbol"), minutes.column("m").to_numpy(),
                                          high=zeros, low=zeros, close=zeros, volume=cum)
        holders = {s: ref.kind(s, day)[1] for s in frame["symbol"] if s in ref.reused}
        rvol_state.seed(state, day, bars, frame, holders)
    return len(days)


def build(start: str | None = None, end: str | None = None, rebuild_from: str | None = None,
          max_days: int | None = None, say=print, polite: bool = True) -> dict:
    """Build every session the plan names (see the module docstring); returns counts. ``polite`` (the default)
    drops this process to below-normal priority and pyarrow to two threads, beside the desk."""
    if polite:
        inventory.below_normal()
        pa.set_cpu_count(2)
        pa.set_io_thread_count(2)
    manifest = rs.load_manifest()
    ref = Reference()
    movers = movers_sessions()
    todo, first_day = plan(manifest, ref, start, end, rebuild_from, movers)
    if manifest.get("builder") != rs.BUILDER:
        manifest = rs.new_manifest()
    if not todo:
        say("relative-volume table is up to date")
        return {"built": 0}
    state = rvol_state.State()
    seeded = seed_state(state, ref, manifest, todo[0][0]) if todo[0][0] != first_day else 0
    for day in [d for d in manifest["days"] if d >= todo[0][0]]:
        manifest["days"].pop(day)
    manifest.update(first_day=first_day, splits_fingerprint=ref.fingerprint, builder=rs.BUILDER)
    (rs.root()).mkdir(parents=True, exist_ok=True)
    (rs.root() / "splits.json").write_text(json.dumps(ref.split_rows), encoding="utf-8")
    say(f"building {len(todo)} session(s) {todo[0][0]} .. {todo[-1][0]} into {rs.root()} (replayed {seeded})")
    built = 0
    for day, minute_path, day_path in todo:
        if day not in movers:
            say(f"{day}: the movers store has no session for it (research/movers/build_movers.py): stopping")
            break
        if rs.stop_path().exists():
            say(f"{rs.stop_path()} is there: stopping before {day}")
            break
        t0 = time.monotonic()
        bars = read_minutes(minute_path, day)
        day_rows = read_day_rows(day_path)
        kinds, holders = {}, {}
        for symbol in set(bars.names) | set(day_rows):
            kinds[symbol], holders[symbol] = ref.kind(symbol, day)
        session = rvol_state.Session(day, bars, day_rows, kinds, holders, movers_labels(day))
        minutes, days, band_rows, counts = rvol_state.build_session(state, session, ref.split_factor)
        rs.write_day(day, minutes, days, band_rows)
        seconds = round(time.monotonic() - t0, 2)
        manifest["days"][day] = {"minute_file": rs.source_identity(minute_path),
                                 "day_file": rs.source_identity(day_path), "movers_built_ts": movers.get(day),
                                 "stock_days": counts["stock_days"], "bars": counts["bars"],
                                 "built_ts": time.time(), "seconds": seconds}
        rs.save_manifest(manifest)
        built += 1
        say(f"{day}  {counts['stock_days']:,} stock-days  {counts['bars']:,} bars  {seconds:.1f} s"
            + (f"  resets {counts['resets']}" if counts["resets"] else ""))
        if max_days and built >= max_days:
            break
    return {"built": built, "first": todo[0][0], "root": str(rs.root())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", help="a new table's first session (default: the first minute file on disk)")
    parser.add_argument("--end", help="the last session to build (default: the newest on disk)")
    parser.add_argument("--rebuild-from", dest="rebuild_from", help="build this session and every later one again")
    parser.add_argument("--max-days", dest="max_days", type=int, help="stop after this many sessions")
    parser.add_argument("--status", action="store_true", help="what is built")
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(rs.status(), indent=1))
        return 0
    build(args.start, args.end, args.rebuild_from, args.max_days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
