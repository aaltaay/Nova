"""What came next after a mix of the Trader's signals all held (``signal_test``): the entries are each in-play
stock-day's first minute in the window where every condition held (``signals.entries_sql``), scored exactly as
``rvol_outcomes`` scores its triggers -- the same entry price, lines, horizons, summary and control (``_score``,
``_controls``, ``summarize``), so a signal answer and a relative-volume answer read alike.

The control: per entry, one stock-day of the same date and filters that was in play by the entry minute and where
the conditions had not all held by then (all held before the window counts as having held) -- a seeded hash, scored
from the same clock the same way. Same day, same minute, same in-play universe: it asks whether the mix told
anything that being in play at that minute did not.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from market_reads import rvol, rvol_outcomes, signals, slots
from market_reads import rvol_store as rs
from market_reads import signal_registry as reg

GROUPS = ("year", "hour", "none")
PARTLY = ("board", "board_state", "catalyst", "catalyst_state", "hod_today", "hod_alerts", "halted", "halts_today",
          "halts_n", "halts", "why", "why_state", "in_play", "pillars", "pillars_n", "pillar_catalyst", "float",
          "float_shares", "rotation", "pillar_float")


def test(*, when: list[dict[str, Any]], filters: dict[str, Any], window_from: str = "04:00",
         window_to: str = "16:00", fresh: bool = False, up_pct: float = 20.0, down_pct: float = 20.0,
         horizon: str = "close", days: int | None = None, group_by: str = "year", control: bool = True,
         seed: int = 1, to_file: Path | None = None) -> dict[str, Any]:
    """``{entries, summary, control, meta}`` (``rvol_outcomes.outcomes``' shape)."""
    conditions = reg.check(when)
    filters = signals.check_filters(filters)
    if horizon not in rvol_outcomes.HORIZONS:
        raise ValueError(f"horizon must be one of {', '.join(rvol_outcomes.HORIZONS)}")
    n_days = int(days or 0)
    if horizon == "days" and not 1 <= n_days <= rvol_outcomes.MAX_DAYS:
        raise ValueError(f"days must be 1-{rvol_outcomes.MAX_DAYS} with horizon='days'")
    if not (0 < float(up_pct) and 0 < float(down_pct) < 100):
        raise ValueError("up_pct above 0 and down_pct between 0 and 100 (percent points)")
    if group_by not in GROUPS:
        raise ValueError(f"group_by must be one of {', '.join(GROUPS)}")
    w0, w1 = rvol.minute_of(window_from, "window_from"), rvol.minute_of(window_to, "window_to")
    if not w0 < w1 <= rs.RTH_CLOSE_M:
        raise ValueError("window_from before window_to, which is 16:00 at the latest")
    tape = signals.uses_tape(conditions)
    groups, _manifest, skipped = signals.chunks(filters, tape)
    rvol_manifest = rs.load_manifest(required=True)
    sql = signals.entries_sql(conditions, w0, w1, filters, tape)
    scored, controls, next_id, held_before = [], [], 0, 0
    con = rvol.connect()
    try:
        with slots.heavy("signal test"):
            for days_list in groups:
                frame = signals.run(days_list, sql, tape)
                if not len(frame):
                    continue
                frame["date"] = pd.to_datetime(frame["date"]).dt.date
                crossed = frame.assign(trigger_m=frame["trigger_m"].where(~frame["held_before"], -1))
                crossed = crossed[crossed["trigger_m"].notna()]
                e = frame[frame["trigger_m"].notna()]
                if fresh:
                    held_before += int(e["held_before"].sum())
                    e = e[~e["held_before"]]
                e = e[e["price"].notna() & (e["price"] > 0)].reset_index(drop=True)
                if not len(e):
                    continue
                e["trigger_m"] = e["trigger_m"].astype(np.int64)
                e["entry_m"] = e["trigger_m"] + 1
                e["id"] = np.arange(next_id, next_id + len(e))
                next_id += len(e)
                e["value"] = np.nan
                part = rvol_outcomes._score(con, e, days_list, rvol_manifest, float(up_pct), float(down_pct), horizon,
                                            n_days)
                part["is_control"] = False
                scored.append(part)
                if control:
                    pool = frame[["date", "symbol", "in_play_m", "epoch", "basis"]].rename(
                        columns={"in_play_m": "first_m"})
                    c = rvol_outcomes._controls(e, pool, seed, crossed[["date", "symbol", "trigger_m"]])
                    if len(c):
                        c["id"] = np.arange(next_id, next_id + len(c))
                        next_id += len(c)
                        con.register("c", c[["id", "date", "symbol", "entry_m"]])
                        mfiles = rvol.posix(rs.minutes_path(d) for d in sorted(set(map(str, c["date"]))))
                        prices = con.execute(rvol_outcomes._price_sql(int(c["entry_m"].max())),
                                             {"mfiles": mfiles}).df()
                        c = c.merge(prices, on="id", how="inner")
                        cs = rvol_outcomes._score(con, c, days_list, rvol_manifest, float(up_pct), float(down_pct),
                                                  horizon, n_days)
                        cs["is_control"] = True
                        controls.append(cs)
    finally:
        con.close()
    frame = pd.concat(scored, ignore_index=True) if scored else pd.DataFrame(columns=["outcome", "value", "date",
                                                                                      "entry_m"])
    frame["group"] = rvol_outcomes._groups(frame, group_by, None) if len(frame) else pd.Series(dtype=object)
    ctl = pd.concat(controls, ignore_index=True) if controls else None
    if ctl is not None:
        ctl["group"] = rvol_outcomes._groups(ctl, group_by, None)
    if to_file is not None:
        rvol_outcomes._write_rows(pd.concat([frame, ctl], ignore_index=True) if ctl is not None else frame, to_file)
    partly = sorted({c["signal"] for c in conditions if c["signal"] in PARTLY or c["signal"] in reg.TAPE_COLUMNS})
    return {
        "entries": int(len(frame)), "summary": rvol_outcomes.summarize(frame) if len(frame) else [],
        "control": (rvol_outcomes.summarize(ctl) if ctl is not None and len(ctl) else []) if control else None,
        "meta": {"when": conditions, "window": f"{window_from}-{window_to}", "fresh": fresh, "filters": filters,
                 "up_pct": float(up_pct), "down_pct": float(down_pct), "horizon": horizon, "days": n_days or None,
                 "group_by": group_by, "seed": seed if control else None,
                 "sessions": sum(len(g) for g in groups),
                 "left_out": {"held_before_window": held_before,
                              **{k: int((frame["outcome"] == k).sum()) if len(frame) else 0
                                 for k in rvol_outcomes.LEFT_OUT}},
                 "coverage": {"partly_covered_signals": [reg.BY_COLUMN[s].to_dict() | {"signal": s} for s in partly],
                              "sessions_without_tape": skipped if tape else None},
                 "rules": {**rvol_outcomes._rules(horizon, n_days),
                           "entry": "the first minute in the window, at or after the stock-day's in_play_m, where "
                                    "every condition held at its end; P is that minute's price (the close of the "
                                    "last bar starting at or before it), and only bars starting after it are read",
                           "control": "per entry, one stock-day of the same date and filters, in play by the entry "
                                      "minute, where the conditions had not all held by then (all held before the "
                                      "window counts as having held) -- a seeded hash, scored the same way"},
                 "units": "p_* shares of entries (0-1); *_pct percent points of the entry price"}}
