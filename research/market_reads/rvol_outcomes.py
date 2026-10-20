"""What came next (#1100): from each entry -- every stock-day at a clock time (``rvol.scan``) or the first minute it
crossed a relative-volume line (``rvol.triggers``) -- did a bar's high reach ``+up_pct`` or a bar's low reach
``-down_pct`` first, and by how much did it run either way.

No look-ahead: the entry price ``P`` is the close of the last bar starting before the entry clock (``at``, or the
end of the trigger bar), and only bars starting at or after that clock are read. Both lines inside one minute bar is
``same_bar`` (the order is not in the data and is never guessed); with ``horizon='days'`` both inside one later
session is ``same_day``. Later sessions are read on the entry day's share basis (``basis``); a reset (another company
on the ticker, a likely unlisted split) inside the horizon leaves the entry out (``horizon_reset``).

The control (trigger entries): for each trigger, one stock-day from the same date that passes the same kinds, price,
split and baseline filters, has a bar before the entry clock, and had not crossed the line by then -- picked by a
seeded hash -- scored from the same clock the same way. Same day, same minute, same universe: the comparison asks
whether crossing the line told anything the clock and the universe did not.
"""
from __future__ import annotations

import zlib
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from market_reads import rvol, slots
from market_reads import rvol_store as rs

HORIZONS = {"close": rs.RTH_CLOSE_M, "session": rs.SESSION_END_M, "days": rs.SESSION_END_M}
GROUPS = ("rvol", "year", "hour", "none")
DEFAULT_BUCKETS = (0, 1, 2, 3, 5, 10, 20, 50, 100, 1000)
MAX_DAYS = 20
LINE_EPS = 1e-9                 # day_movers' DAY_MOVERS_LINE_EPS: a price exactly on the line is on it
OUTCOMES = ("up", "down", "same_bar", "same_day", "neither")
ROW_COLUMNS = ("date", "symbol", "entry_et", "price", "value", "group", "outcome", "up_et", "down_et",
               "max_up_pct", "max_down_pct", "end_pct", "is_control")


def _forward_sql(hz: int) -> str:
    return f"""
SELECT e.id, min(x.m) FILTER (WHERE x.high >= e.up_px) AS up_m, min(x.m) FILTER (WHERE x.low <= e.dn_px) AS dn_m,
       max(x.high) AS max_high, min(x.low) AS min_low, arg_max(x.close, x.m) AS end_close
FROM e JOIN read_parquet($mfiles) x ON x.date = e.date AND x.symbol = e.symbol
WHERE x.m >= e.entry_m AND x.m < {hz} GROUP BY e.id"""


PRICE_SQL = """
SELECT c.id, arg_max(x.close, x.m) AS price FROM c JOIN read_parquet($mfiles) x ON x.date = c.date AND x.symbol = c.symbol
WHERE x.m < c.entry_m GROUP BY c.id"""


def _ahead_sql(days: int) -> str:
    return f"""
WITH n AS (SELECT date, symbol, hi, lo, last_close, basis, epoch FROM read_parquet($afiles)),
j AS (SELECT e.id, n.hi * n.basis / e.basis AS hi_e, n.lo * n.basis / e.basis AS lo_e,
             n.last_close * n.basis / e.basis AS close_e, n.epoch <> e.epoch AS reset,
             row_number() OVER (PARTITION BY e.id ORDER BY n.date) AS k
      FROM e JOIN n ON n.symbol = e.symbol AND n.date > e.date AND n.date <= e.date + INTERVAL {days * 2 + 14} DAYS)
SELECT * FROM j WHERE k <= {days}"""


def _hash(*parts) -> int:
    return zlib.crc32("|".join(str(p) for p in parts).encode())


def _controls(entries: pd.DataFrame, pool: pd.DataFrame, seed: int, crossed: pd.DataFrame) -> pd.DataFrame:
    """One control stock-day per trigger (see the module docstring); a trigger with no eligible stock gets none.
    ``crossed`` is every stock-day that met the trigger, with the minute it did (-1: over the line before the
    window opened)."""
    out = []
    own = crossed.set_index(["date", "symbol"])["trigger_m"]
    for day, trig in entries.groupby("date", sort=True):
        p = pool[pool["date"] == day].reset_index(drop=True)
        if not len(p):
            continue
        n = len(p)
        rank = np.array([_hash(seed, day, s) for s in p["symbol"]], dtype=np.int64) % (2 ** 31)
        first = p["first_m"].to_numpy(dtype=np.int64)
        crossed = np.array([own.get((day, s), np.inf) for s in p["symbol"]], dtype=np.float64)
        sym_index = {s: i for i, s in enumerate(p["symbol"])}
        t = trig["trigger_m"].to_numpy(dtype=np.int64)
        me = np.array([sym_index.get(s, -1) for s in trig["symbol"]], dtype=np.int64)
        offset = np.array([_hash(seed, day, s, "control") for s in trig["symbol"]], dtype=np.int64) % (2 ** 31)
        eligible = (first[None, :] <= t[:, None]) & (crossed[None, :] > t[:, None]) & \
                   (np.arange(n)[None, :] != me[:, None])
        key = np.where(eligible, (rank[None, :] - offset[:, None]) % (2 ** 31), np.iinfo(np.int64).max)
        pick = key.argmin(axis=1)
        found = key[np.arange(len(t)), pick] != np.iinfo(np.int64).max
        chosen = p.iloc[pick[found]].reset_index(drop=True)
        src = trig[found].reset_index(drop=True)
        out.append(pd.DataFrame({"date": day, "symbol": chosen["symbol"], "entry_m": src["entry_m"],
                                 "epoch": chosen["epoch"], "basis": chosen["basis"], "value": src["value"],
                                 "source_id": src["id"]}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(
        columns=["date", "symbol", "entry_m", "epoch", "basis", "value", "source_id"])


def _score(con, e: pd.DataFrame, days_list: list[str], manifest: dict, up: float, down: float, horizon: str,
           n_days: int) -> pd.DataFrame:
    """Outcome columns for entries ``e`` (``id, date, symbol, entry_m, price, epoch, basis``) of one chunk."""
    e = e.copy()
    e["up_px"] = e["price"] * (1 + up / 100.0) * (1 - LINE_EPS)
    e["dn_px"] = e["price"] * (1 - down / 100.0) * (1 + LINE_EPS)
    con.register("e", e[["id", "date", "symbol", "entry_m", "up_px", "dn_px", "epoch", "basis"]])
    mfiles = rvol.posix(rs.minutes_path(d) for d in sorted(set(map(str, e["date"]))))
    f = con.execute(_forward_sql(HORIZONS[horizon]), {"mfiles": mfiles}).df()
    e = e.merge(f, on="id", how="left")
    up_m, dn_m = e["up_m"].to_numpy(dtype=np.float64), e["dn_m"].to_numpy(dtype=np.float64)
    outcome = np.where(np.isnan(up_m) & np.isnan(dn_m), "neither",
                       np.where(up_m == dn_m, "same_bar",
                                np.where(np.isnan(dn_m) | (up_m < dn_m), "up", "down"))).astype(object)
    hi, lo = e["max_high"].to_numpy(dtype=np.float64), e["min_low"].to_numpy(dtype=np.float64)
    end = e["end_close"].fillna(e["price"]).to_numpy(dtype=np.float64)
    reset = np.zeros(len(e), dtype=bool)
    if horizon == "days":
        last = date.fromisoformat(days_list[-1]) + timedelta(days=n_days * 2 + 14)
        ahead = [d for d in rs.built_days(manifest, days_list[0], last.isoformat()) if d > days_list[0]]
        a = con.execute(_ahead_sql(n_days), {"afiles": rvol.posix(rs.days_path(d) for d in ahead)}).df() \
            if ahead else pd.DataFrame(columns=["id", "hi_e", "lo_e", "close_e", "reset", "k"])
        if len(a):
            a = a.merge(e[["id", "up_px", "dn_px"]], on="id")
            a["up_hit"] = a["hi_e"] >= a["up_px"]
            a["dn_hit"] = a["lo_e"] <= a["dn_px"]
            g = a.groupby("id")
            per = pd.DataFrame({
                "up_k": a[a["up_hit"]].groupby("id")["k"].min(), "dn_k": a[a["dn_hit"]].groupby("id")["k"].min(),
                "reset_any": g["reset"].any(), "hi_max": g["hi_e"].max(), "lo_min": g["lo_e"].min(),
                "close_last": a.sort_values("k").groupby("id")["close_e"].last()})
            per = per.reindex(e["id"])
            up_k, dn_k = per["up_k"].to_numpy(dtype=np.float64), per["dn_k"].to_numpy(dtype=np.float64)
            later = np.where(np.isnan(up_k) & np.isnan(dn_k), "neither",
                             np.where(up_k == dn_k, "same_day",
                                      np.where(np.isnan(dn_k) | (up_k < dn_k), "up", "down"))).astype(object)
            outcome = np.where(outcome == "neither", later, outcome)
            reset = per["reset_any"].fillna(False).to_numpy(dtype=bool)
            hi = np.fmax(hi, per["hi_max"].to_numpy(dtype=np.float64))
            lo = np.fmin(lo, per["lo_min"].to_numpy(dtype=np.float64))
            end = np.where(np.isnan(per["close_last"].to_numpy(dtype=np.float64)), end,
                           per["close_last"].to_numpy(dtype=np.float64))
    price = e["price"].to_numpy(dtype=np.float64)
    e["outcome"] = np.where(reset, "horizon_reset", outcome)
    e["max_up_pct"] = (np.fmax(hi, price) / price - 1) * 100
    e["max_down_pct"] = (np.fmin(lo, price) / price - 1) * 100
    e["end_pct"] = (end / price - 1) * 100
    e["minutes_to_up"] = np.where(np.isnan(up_m), np.nan, up_m - e["entry_m"] + 1)
    e["minutes_to_down"] = np.where(np.isnan(dn_m), np.nan, dn_m - e["entry_m"] + 1)
    return e


def _groups(frame: pd.DataFrame, group_by: str, buckets) -> pd.Series:
    if group_by == "none":
        return pd.Series("all", index=frame.index)
    if group_by == "year":
        return frame["date"].map(lambda d: str(d)[:4])
    if group_by == "hour":
        return frame["entry_m"].map(lambda m: f"{int(m) // 60:02d}:00")
    edges = list(buckets or DEFAULT_BUCKETS)
    labels = [f"{a:g}-{b:g}" for a, b in zip(edges[:-1], edges[1:], strict=False)] + [f"{edges[-1]:g}+"]
    where = np.searchsorted(edges, frame["value"].to_numpy(dtype=np.float64), side="right") - 1
    named = np.array(labels + ["no baseline"], dtype=object)
    where = np.where(frame["value"].isna() | (where < 0), len(labels), where)
    return pd.Series(named[where], index=frame.index)


def summarize(frame: pd.DataFrame, order: list[str] | None = None) -> list[dict[str, Any]]:
    """One row per group (in ``order``) plus ``all``: counts, shares and the medians of what came next."""
    out = []
    scored = frame[frame["outcome"] != "horizon_reset"]
    names = [g for g in (order or sorted(scored["group"].unique())) if g != "all"]
    for name, part in [*((g, scored[scored["group"] == g]) for g in names), ("all", scored)]:
        n = len(part)
        if not n:
            continue
        count = {k: int((part["outcome"] == k).sum()) for k in OUTCOMES}
        resolved = count["up"] + count["down"]

        def med(column, part=part):
            values = part[column].dropna()
            return float(values.median()) if len(values) else None
        out.append({"group": name, "entries": n, **count, "p_up": count["up"] / n, "p_down": count["down"] / n,
                    "p_up_resolved": count["up"] / resolved if resolved else None,
                    "median_max_up_pct": med("max_up_pct"), "median_max_down_pct": med("max_down_pct"),
                    "median_end_pct": med("end_pct"), "mean_end_pct": float(part["end_pct"].mean()),
                    "median_minutes_to_up": med("minutes_to_up"), "median_minutes_to_down": med("minutes_to_down")})
    return out


def _left_out(con, groups: list[list[str]], filters, kinds, splits: str, measure: str, min_sessions: int) -> dict:
    """Stock-days of the asked kinds and prices the split rule or the baseline rule left out."""
    base = rvol.universe_sql(filters, kinds, "include", None, 0)
    split = "split = 'likely_split'" if splits == "exclude_likely" else \
        "coalesce(split, '') NOT IN ('likely_split', 'suspect')" if splits == "only_suspects" else "false"
    column = "day_avg_sessions" if measure == "daily_rate" else "base_sessions"
    split_n = base_n = 0
    for days in groups:
        a, b = con.execute(f"SELECT count(*) FILTER (WHERE {split}), count(*) FILTER (WHERE NOT ({split}) AND "
                           f"{column} < {int(min_sessions)}) FROM read_parquet($dfiles) WHERE {base}",
                           {"dfiles": rvol.posix(rs.days_path(d) for d in days)}).fetchone()
        split_n, base_n = split_n + int(a or 0), base_n + int(b or 0)
    return {"split": split_n, "base_sessions": base_n}


def outcomes(*, filters: dict[str, Any], at: str | None = None, trigger: dict[str, Any] | None = None,
             up_pct: float = 50.0, down_pct: float = 50.0, horizon: str = "close", days: int | None = None,
             group_by: str | None = None, buckets=None, measure: str = "cumulative", kinds=None,
             splits: str = "exclude_likely", min_base_sessions: int = rs.BASE_SESSIONS, control: bool = True,
             seed: int = 1, to_file: Path | None = None) -> dict[str, Any]:
    """``{entries, summary, control, meta}`` (see the module docstring); ``to_file`` receives every scored entry."""
    if (at is None) == (trigger is None):
        raise ValueError("give at (every stock-day at a clock time) or trigger (rvol_triggers' arguments), not both")
    if horizon not in HORIZONS:
        raise ValueError(f"horizon must be one of {', '.join(HORIZONS)}")
    n_days = int(days or 0)
    if horizon == "days" and not 1 <= n_days <= MAX_DAYS:
        raise ValueError(f"days must be 1-{MAX_DAYS} with horizon='days'")
    if not (0 < float(up_pct) and 0 < float(down_pct) < 100):
        raise ValueError("up_pct above 0 and down_pct between 0 and 100 (percent points)")
    is_trigger = trigger is not None
    group_by = group_by or ("rvol" if at else "none")
    if group_by not in GROUPS:
        raise ValueError(f"group_by must be one of {', '.join(GROUPS)}")
    end = HORIZONS[horizon]
    if at is not None and rvol.minute_of(at, "at") >= end:
        raise ValueError(f"at {at} leaves no bar inside horizon '{horizon}' (it ends {rvol.hhmm(end)})")
    if is_trigger:
        trigger = dict(trigger)
        measure = trigger.pop("measure", measure)
        window = (trigger.pop("window_from", "04:00"), trigger.pop("window_to", rvol.hhmm(min(end, rs.RTH_CLOSE_M))))
        rvol_min = trigger.pop("rvol_min", None)
        fresh = bool(trigger.pop("fresh", False))
        if rvol_min is None or trigger:
            raise ValueError("trigger holds rvol_min and optionally measure, window_from, window_to, fresh "
                             f"(filters go in filters){'; unknown ' + str(sorted(trigger)) if trigger else ''}")
        if rvol.minute_of(window[1], "window_to") > end:
            raise ValueError(f"window_to {window[1]} runs past horizon '{horizon}' (it ends {rvol.hhmm(end)})")
        groups, filters, sql = rvol.trigger_frames(rvol_min, measure, window, filters, kinds, splits,
                                                   min_base_sessions)
        chunk_iter = rvol.run_chunks(groups, sql)
    else:
        filters, groups, tables = rvol.scan_tables(at, filters, measure, kinds, splits, min_base_sessions)
        chunk_iter = tables()
    manifest = rs.load_manifest(required=True)
    value_column = rvol.MEASURES[measure]
    scored, controls, no_price, next_id = [], [], 0, 0
    con = rvol.connect()
    try:
        with slots.heavy("rvol outcomes"):
            for chunk_days, table in chunk_iter:
                e = table.to_pandas()
                if not len(e):
                    continue
                e["date"] = pd.to_datetime(e["date"]).dt.date
                crossed = None
                if is_trigger:                  # over the line before the window counts as crossed from the start
                    crossed = e.assign(trigger_m=e["trigger_m"].where(~e["above_before"], -1))
                    if fresh:
                        e = e[~e["above_before"]].reset_index(drop=True)
                    if not len(e):
                        continue
                e["entry_m"] = e["entry_m"] if is_trigger else rvol.minute_of(at)
                no_price += int(e["price"].isna().sum())
                e = e[e["price"].notna() & (e["price"] > 0)].reset_index(drop=True)
                e["id"] = np.arange(next_id, next_id + len(e))
                next_id += len(e)
                e["value"] = e[value_column]
                part = _score(con, e, chunk_days, manifest, float(up_pct), float(down_pct), horizon, n_days)
                part["is_control"] = False
                scored.append(part)
                if is_trigger and control:
                    universe = rvol.universe_sql(filters, kinds, splits, rvol.sessions_column(measure),
                                                 min_base_sessions)
                    pool = con.execute(f"SELECT date, symbol, first_m, epoch, basis FROM read_parquet($dfiles) "
                                       f"WHERE first_m IS NOT NULL AND {universe}",
                                       {"dfiles": rvol.posix(rs.days_path(d) for d in chunk_days)}).df()
                    pool["date"] = pd.to_datetime(pool["date"]).dt.date
                    c = _controls(e, pool, seed, crossed)
                    if len(c):
                        c["id"] = np.arange(next_id, next_id + len(c))
                        next_id += len(c)
                        con.register("c", c[["id", "date", "symbol", "entry_m"]])
                        mfiles = rvol.posix(rs.minutes_path(d) for d in sorted(set(map(str, c["date"]))))
                        prices = con.execute(PRICE_SQL, {"mfiles": mfiles}).df()
                        c = c.merge(prices, on="id", how="inner")
                        cs = _score(con, c, chunk_days, manifest, float(up_pct), float(down_pct), horizon, n_days)
                        cs["is_control"] = True
                        controls.append(cs)
            left = _left_out(con, groups, filters, kinds, splits, measure, min_base_sessions)
    finally:
        con.close()
    frame = pd.concat(scored, ignore_index=True) if scored else pd.DataFrame(columns=["outcome", "value", "date",
                                                                                      "entry_m"])
    frame["group"] = _groups(frame, group_by, buckets) if len(frame) else pd.Series(dtype=object)
    ctl = pd.concat(controls, ignore_index=True) if controls else None
    if ctl is not None:
        ctl["group"] = _groups(ctl, group_by, buckets)
    order = None
    if group_by == "rvol":
        edges = list(buckets or DEFAULT_BUCKETS)
        order = [f"{a:g}-{b:g}" for a, b in zip(edges[:-1], edges[1:], strict=False)] + [f"{edges[-1]:g}+",
                                                                                        "no baseline"]
        order = [g for g in order if g in set(frame["group"])]
    if to_file is not None:
        _write_rows(pd.concat([frame, ctl], ignore_index=True) if ctl is not None else frame, to_file)
    return {
        "entries": int(len(frame)), "summary": summarize(frame, order) if len(frame) else [],
        "control": summarize(ctl, order) if ctl is not None and len(ctl) else (
            [] if is_trigger and control else None),
        "meta": {"mode": "at" if at else "trigger", "at": at, "trigger": {"rvol_min": rvol_min, "measure": measure,
                                                                            "window": f"{window[0]}-{window[1]}", "fresh": fresh}
                 if is_trigger else None,
                 "up_pct": float(up_pct), "down_pct": float(down_pct), "horizon": horizon,
                 "days": n_days or None, "group_by": group_by, "measure": measure, "filters": filters,
                 "kinds": list(kinds or rvol.DEFAULT_KINDS), "splits": splits, "min_base_sessions": min_base_sessions,
                 "seed": seed if is_trigger and control else None,
                 "left_out": {"no_price": no_price, **left,
                              "horizon_reset": int((frame["outcome"] == "horizon_reset").sum()) if len(frame) else 0},
                 "rules": _rules(horizon, n_days), "units": "p_* shares of entries (0-1); *_pct percent points of the "
                                                            "entry price; minutes to the end of the bar that hit"}}


def _rules(horizon: str, n_days: int) -> dict[str, str]:
    end = {"close": "bars starting before 16:00", "session": "bars starting before 20:00",
           "days": f"the rest of the session, then the symbol's next {n_days} sessions' high / low (04:00-20:00) on "
                   "the entry day's share basis"}[horizon]
    return {"entry": "the close of the last bar starting before the entry clock (at, or the end of the trigger bar); "
                     "only bars starting at or after the clock are read",
            "horizon": end, "lines": f"a bar's high >= P x (1 + up_pct/100), a low <= P x (1 - down_pct/100) (within "
                                     f"{LINE_EPS:g}, the movers store's tolerance)",
            "same_bar": "both lines inside one minute bar: the order is not in the data; counted apart, never guessed",
            "same_day": "both lines inside one later session (horizon days)",
            "end_pct": "the last close inside the horizon vs P",
            "control": "per trigger, one stock-day of the same date, kinds, price, split and baseline filters with a "
                       "bar before the entry clock that had not crossed the line by then (seeded hash), scored the "
                       "same way",
            "p_up_resolved": "up / (up + down): ignores same_bar, same_day and neither"}


def _write_rows(frame: pd.DataFrame, out: Path) -> None:
    rows = pd.DataFrame({
        "date": frame["date"].astype(str), "symbol": frame["symbol"], "entry_et": frame["entry_m"].map(rvol.hhmm),
        "price": frame["price"], "value": frame["value"], "group": frame["group"], "outcome": frame["outcome"],
        "up_et": frame["up_m"].map(rvol.hhmm), "down_et": frame["dn_m"].map(rvol.hhmm),
        "max_up_pct": frame["max_up_pct"], "max_down_pct": frame["max_down_pct"], "end_pct": frame["end_pct"],
        "is_control": frame["is_control"]})
    rows.to_parquet(out, index=False) if out.suffix == ".parquet" else rows.to_csv(out, index=False)
